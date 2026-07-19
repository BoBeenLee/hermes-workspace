import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/hermes/messenger_assistant.py"
SPEC = importlib.util.spec_from_file_location("messenger_assistant", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class MessengerAssistantPolicyTests(unittest.TestCase):
    def test_default_state_is_fail_closed(self):
        state = module.default_state()
        self.assertFalse(state["enabled"])
        self.assertFalse(state["automatic_paused"])
        self.assertEqual(state["pending"], {})

    def test_discord_text_is_split_under_limit(self):
        chunks = module.split_discord("a" * 4001, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))
        self.assertEqual("".join(chunks), "a" * 4001)

    def test_fallback_model_forces_approval(self):
        reason = module.hard_approval_reason(
            [{"text": "안녕", "message_type": "text", "has_media": False}],
            {
                "decision": "auto",
                "reply": "안녕!",
                "confidence": 1,
                "flags": {},
            },
            {"model": "openai/gpt-oss-120b", "provider": "groq"},
        )
        self.assertIn("fallback", reason)

    def test_link_forces_approval(self):
        reason = module.hard_approval_reason(
            [{"text": "https://example.com 봐줘", "message_type": "text", "has_media": False}],
            {"decision": "auto", "reply": "봤어", "confidence": 1, "flags": {}},
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertIn("링크", reason)

    def test_emergency_forces_approval(self):
        reason = module.hard_approval_reason(
            [{"text": "지금 119 불러야 해", "message_type": "text", "has_media": False}],
            {"decision": "auto", "reply": "알겠어", "confidence": 1, "flags": {}},
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertTrue(reason)

    def test_used_memory_forces_approval(self):
        reason = module.hard_approval_reason(
            [{"text": "뭐 좋아해?", "message_type": "text", "has_media": False}],
            {
                "decision": "auto",
                "reply": "매운 음식 좋아해",
                "confidence": 1,
                "flags": {"used_memory": True},
            },
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertIn("used_memory", reason)

    def test_high_confidence_low_risk_may_auto(self):
        reason = module.hard_approval_reason(
            [{"text": "안녕", "message_type": "text", "has_media": False}],
            {
                "decision": "auto",
                "reply": "안녕 😊",
                "confidence": 0.99,
                "flags": {},
            },
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertEqual(reason, "")

    def test_hanam_current_weather_query_is_recognized_without_accepting_generic_text(self):
        self.assertTrue(module.is_hanam_weather_lookup("하남 오늘 날씨"))
        self.assertTrue(module.is_hanam_weather_lookup("하남시 현재 날씨 알려줘"))
        self.assertFalse(module.is_hanam_weather_lookup("서울 오늘 날씨"))
        self.assertFalse(module.is_hanam_weather_lookup("하남 맛집"))
        self.assertIn("timeout=30", module.hanam_weather_prompt(module.now_utc().astimezone(module.KST)))

    def test_hanam_weather_resolution_requires_fresh_primary_model_data(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.hermes_bin = Path("/tmp/hermes")
        assistant.profile_dir = Path("/tmp/profile")
        assistant.config = {"profile": "jarvis"}
        requested = module.now_utc().astimezone(module.KST).replace(microsecond=0)
        observed = (requested - dt.timedelta(minutes=5)).isoformat()
        result = {
            "ok": True,
            "location": "Hanam-si, Gyeonggi-do",
            "requested_at_kst": requested.isoformat(),
            "observed_at_kst": observed,
            "weather_code": 2,
            "temperature_c": 28.5,
            "apparent_temperature_c": 33.0,
            "humidity_percent": 72,
            "precipitation_mm": 0,
            "today_high_c": 31,
            "today_low_c": 24,
            "precipitation_probability_max_percent": 60,
            "source_name": "Open-Meteo",
            "source_url": module.HANAM_WEATHER_URL,
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER, "session_id": "weather-session"}

        with mock.patch.object(module, "run_hermes_json", return_value=(result, usage)) as run, mock.patch.object(
            module, "hermes_session_used_tool", return_value=True
        ) as used_tool:
            reply, evidence = assistant._resolve_hanam_weather("하남 오늘 날씨")

        self.assertIn("하남은 현재 구름 조금, 28.5°C", reply)
        self.assertIn("최대 강수확률 60%", reply)
        self.assertEqual(evidence["source_url"], module.HANAM_WEATHER_URL)
        self.assertEqual(run.call_args.kwargs["toolsets"], "terminal")
        used_tool.assert_called_once_with(Path("/tmp/profile"), "weather-session", "terminal")

    def test_stale_hanam_weather_resolution_fails_closed(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.hermes_bin = Path("/tmp/hermes")
        assistant.profile_dir = Path("/tmp/profile")
        assistant.config = {"profile": "jarvis"}
        stale = (module.now_utc().astimezone(module.KST) - dt.timedelta(hours=2)).isoformat()
        result = {
            "ok": True,
            "observed_at_kst": stale,
            "source_name": "Open-Meteo",
            "source_url": module.HANAM_WEATHER_URL,
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER, "session_id": "weather-session"}

        with mock.patch.object(module, "run_hermes_json", return_value=(result, usage)), mock.patch.object(
            module, "hermes_session_used_tool", return_value=True
        ):
            with self.assertRaisesRegex(RuntimeError, "현재 시각"):
                assistant._resolve_hanam_weather("하남 오늘 날씨")

    def test_hanam_weather_resolution_rejects_missing_terminal_tool_evidence(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.hermes_bin = Path("/tmp/hermes")
        assistant.profile_dir = Path("/tmp/profile")
        assistant.config = {"profile": "jarvis"}
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER, "session_id": "weather-session"}

        with mock.patch.object(module, "run_hermes_json", return_value=({"ok": True}, usage)), mock.patch.object(
            module, "hermes_session_used_tool", return_value=False
        ):
            with self.assertRaisesRegex(RuntimeError, "실제 날씨 조회 도구 호출"):
                assistant._resolve_hanam_weather("하남 오늘 날씨")

    def test_auth_memory_is_rejected(self):
        self.assertIsNone(
            module.sanitize_memory_update(
                {
                    "key": "비밀번호",
                    "value": "1234",
                    "confidence": 1,
                    "secret_or_auth": False,
                }
            )
        )

    def test_memory_expiry_window_is_365_days(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory.json"
            old = (module.now_utc() - dt.timedelta(days=366)).isoformat()
            fresh = (module.now_utc() - dt.timedelta(days=364)).isoformat()
            payload = {
                "version": 1,
                "contacts": {
                    "room": {
                        "name": "친구",
                        "facts": {
                            "old": {"value": "old", "confirmed_at": old},
                            "fresh": {"value": "fresh", "confirmed_at": fresh},
                        },
                    }
                },
            }
            module.atomic_write_json(path, payload)
            loaded = json.loads(path.read_text())
            cutoff = module.now_utc() - dt.timedelta(days=365)
            kept = {
                key
                for key, value in loaded["contacts"]["room"]["facts"].items()
                if module.parse_time(value["confirmed_at"]) >= cutoff
            }
            self.assertEqual(kept, {"fresh"})

    def test_room_and_global_rate_limits(self):
        state = module.default_state()
        state["rate"]["rooms"]["r1"] = [module.iso_now()] * 3
        allowed, reason = module.rate_allowed(state, "r1")
        self.assertFalse(allowed)
        self.assertIn("채팅방", reason)

        state = module.default_state()
        state["rate"]["global"] = [module.iso_now()] * 10
        allowed, reason = module.rate_allowed(state, "r2")
        self.assertFalse(allowed)
        self.assertIn("전체", reason)

    def test_kakao_operations_are_routed_to_namespaced_mcp_tools(self):
        client = module.KakaoClient.__new__(module.KakaoClient)
        client._call_tool = mock.Mock(return_value={"ok": True})

        client.auth_status()
        client.list_since("from", "until")
        client.preview("친구", "123")
        client.send("친구", "답장", dry_run=True, chat_id="chat-1")

        self.assertEqual(
            [call.args[0] for call in client._call_tool.call_args_list],
            ["auth_status", "list_new_messages_since", "preview_messages", "send_message"],
        )
        send_arguments = client._call_tool.call_args_list[-1].args[1]
        self.assertEqual(send_arguments["chat_id"], "chat-1")

    def test_direct_room_requires_adapter_direct_evidence_over_mcp(self):
        client = module.KakaoClient.__new__(module.KakaoClient)
        client._call_tool = mock.Mock(
            return_value={
                "matches": [
                    {
                        "chat_id": "123",
                        "sources": ["visible_chats", "NTUser.directChatId"],
                    }
                ]
            }
        )

        self.assertTrue(client.is_direct_chat("123", "친구"))
        client._call_tool.assert_called_once_with(
            "find_chat",
            {"query": "친구", "limit": 20, "scan_limit": 500},
        )

    def test_auth_complete_command_is_dispatched(self):
        class FakeDiscord:
            @staticmethod
            def messages_after(_cursor):
                return [
                    {
                        "id": "42",
                        "author": {"id": "allowed", "bot": False},
                        "content": "인증 완료",
                    }
                ]

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = {"last_discord_message_id": ""}
        assistant.discord = FakeDiscord()
        assistant.allowed_user_id = "allowed"
        assistant._authentication_completed = mock.Mock()

        assistant._process_discord_commands()

        assistant._authentication_completed.assert_called_once_with("42")

    def test_auth_complete_verifies_without_attempting_login(self):
        class FakeKakao:
            @staticmethod
            def auth_status():
                return {"ok": True}

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()

        assistant._authentication_completed("42")

        assistant.discord.send.assert_called_once()
        self.assertIn("MCP를 통한 카카오톡 읽기 로그인을 확인", assistant.discord.send.call_args.args[0])
        self.assertEqual(assistant.discord.send.call_args.kwargs["reply_to"], "42")

    def test_cron_poll_does_not_consume_discord_commands(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.profile_dir = Path("/tmp/profile")
        assistant.state = {"gateway_identity": "same", "enabled": False}
        assistant.discord = mock.Mock()
        assistant._process_discord_commands = mock.Mock()

        with mock.patch.object(module, "gateway_identity", return_value="same"):
            assistant._run_locked(process_discord=False, process_kakao=True)

        assistant._process_discord_commands.assert_not_called()

    def test_cron_poll_uses_message_mcp_without_redundant_auth_status(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.profile_dir = Path("/tmp/profile")
        assistant.state = {
            "gateway_identity": "same",
            "enabled": True,
            "baseline_summary_pending": False,
        }
        assistant.discord = mock.Mock()
        assistant.kakao = mock.Mock()
        assistant._poll_kakao = mock.Mock()
        assistant._process_ready_buffers = mock.Mock()

        with mock.patch.object(module, "gateway_identity", return_value="same"):
            assistant._run_locked(process_discord=False, process_kakao=True)

        assistant.kakao.auth_status.assert_not_called()
        assistant._poll_kakao.assert_called_once_with()

    def test_poll_buffers_manual_from_me_message_in_direct_room(self):
        class FakeKakao:
            @staticmethod
            def list_since(_since, _until):
                return {
                    "rooms": [
                        {
                            "chat_id": "direct-1",
                            "display_name": "친구",
                            "new_messages": [
                                {
                                    "entity_id": "message-1",
                                    "timestamp": "2026-07-19T12:00:00+00:00",
                                    "is_from_me": True,
                                    "snippet": "오늘 날씨 어때?",
                                }
                            ],
                        }
                    ]
                }

            @staticmethod
            def is_direct_chat(chat_id, _display_name):
                return chat_id == "direct-1"

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["baseline_at"] = "2026-07-19T11:59:00+00:00"
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()
        assistant._invalidate_pending_for_room = mock.Mock()

        assistant._poll_kakao()

        self.assertEqual(assistant.state["room_buffers"]["direct-1"]["entity_ids"], ["message-1"])

    def test_assistant_authored_from_me_message_is_not_a_candidate(self):
        self.assertFalse(
            module.is_candidate_message(
                {
                    "is_from_me": True,
                    "snippet": f"{module.PREFIX} 자동 답변",
                }
            )
        )
        self.assertFalse(
            module.is_candidate_message(
                {
                    "is_from_me": True,
                    "text": f"{module.PREFIX} 승인 답변",
                }
            )
        )
        self.assertTrue(module.is_candidate_message({"is_from_me": True, "text": "직접 보낸 질문"}))
        self.assertTrue(module.is_candidate_message({"is_from_me": False, "text": "상대가 보낸 질문"}))

    def test_poll_rejects_member_count_two_without_adapter_direct_evidence(self):
        class FakeKakao:
            @staticmethod
            def list_since(_since, _until):
                return {
                    "rooms": [
                        {
                            "chat_id": "group-1",
                            "display_name": "세 명 방",
                            "new_messages": [
                                {
                                    "entity_id": "message-2",
                                    "timestamp": "2026-07-19T12:00:00+00:00",
                                    "is_from_me": False,
                                }
                            ],
                        }
                    ]
                }

            @staticmethod
            def is_direct_chat(_chat_id, _display_name):
                return False

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["baseline_at"] = "2026-07-19T11:59:00+00:00"
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()
        assistant._invalidate_pending_for_room = mock.Mock()

        assistant._poll_kakao()

        self.assertNotIn("group-1", assistant.state["room_buffers"])

    def test_verified_send_uses_actual_room_id_and_never_retries_actual_send(self):
        class FakeKakao:
            def __init__(self):
                self.calls = []

            def send(self, target, message, *, dry_run, chat_id=None):
                self.calls.append((target, message, dry_run, chat_id))
                if dry_run:
                    return {"ok": True, "chat_id_validated": True}
                return {"ok": True, "message_sent": True}

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.kakao = FakeKakao()
        assistant._verify_sent = mock.Mock(side_effect=[False, True])

        self.assertTrue(assistant._send_verified("친구", "123", "답장"))
        self.assertEqual(
            assistant.kakao.calls,
            [
                ("친구", "답장", True, "123"),
                ("친구", "답장", False, "123"),
            ],
        )

    def test_verified_send_falls_back_to_cua_mcp_and_reads_back(self):
        class FakeKakao:
            @staticmethod
            def send(_target, _message, *, dry_run, chat_id=None):
                if dry_run:
                    return {"ok": True, "chat_id_validated": True}
                return {"ok": False, "message_sent": False}

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.kakao = FakeKakao()
        assistant.cua = mock.Mock()
        assistant.cua.send_to_open_room.return_value = True
        assistant._verify_sent = mock.Mock(side_effect=[False, False, True])

        self.assertTrue(assistant._send_verified("친구", "123", "답장"))
        assistant.cua.send_to_open_room.assert_called_once_with("친구", "답장")
        self.assertEqual(assistant._verify_sent.call_count, 3)

    def test_cua_fallback_requires_exact_open_room_and_types_relative_to_window(self):
        client = module.CuaDriverClient.__new__(module.CuaDriverClient)
        client._call_tool = mock.Mock(
            side_effect=[
                {
                    "apps": [
                        {
                            "bundle_id": client.KAKAO_BUNDLE_ID,
                            "running": True,
                            "pid": 10,
                        }
                    ]
                },
                {
                    "windows": [
                        {"title": "친구", "is_on_screen": True, "window_id": 20},
                    ]
                },
                {"screenshot_width": 1000, "screenshot_height": 800},
                {"verified": True, "characters": 2},
                {},
            ]
        )

        self.assertTrue(client.send_to_open_room("친구", "답장"))
        typed = client._call_tool.call_args_list[3]
        self.assertEqual(typed.args[0], "type_text")
        self.assertEqual(typed.args[1]["x"], 330)
        self.assertEqual(typed.args[1]["y"], 688)


if __name__ == "__main__":
    unittest.main()
