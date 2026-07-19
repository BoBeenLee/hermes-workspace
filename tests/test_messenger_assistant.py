import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
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

    def test_recovery_reuses_kmsg_cache_without_reading_or_prompting_for_secrets(self):
        client = module.KakaoClient.__new__(module.KakaoClient)
        completed = subprocess.CompletedProcess([], 0)
        with mock.patch.dict(os.environ, {"KMSG_BIN": "/safe/kmsg"}, clear=False):
            with mock.patch.object(module.subprocess, "run", return_value=completed) as run:
                ok, reason = client.stored_login()

        self.assertTrue(ok)
        self.assertEqual(reason, "submitted")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["/safe/kmsg", "auth", "login", "--auto"])
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("input", kwargs)

    def test_send_backend_accepts_kmsg_chats_envelope(self):
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps({"chats": [], "count": 0}),
            stderr="",
        )
        with mock.patch.dict(os.environ, {"KMSG_BIN": "/safe/kmsg"}, clear=False):
            with mock.patch.object(module.subprocess, "run", return_value=completed):
                self.assertTrue(module.KakaoClient.send_backend_ready())

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

            @staticmethod
            def send_backend_ready():
                return True

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()

        assistant._authentication_completed("42")

        assistant.discord.send.assert_called_once()
        self.assertIn("읽기·발신 로그인을 확인", assistant.discord.send.call_args.args[0])
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
            def list_chats():
                return {
                    "chats": [
                        {
                            "chat_id": "direct-1",
                            "display_name": "친구",
                            "member_count": 1,
                        }
                    ]
                }

            @staticmethod
            def direct_chat_ids():
                return {"direct-1"}

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
            def list_chats():
                return {
                    "chats": [
                        {
                            "chat_id": "group-1",
                            "display_name": "세 명 방",
                            "member_count": 2,
                        }
                    ]
                }

            @staticmethod
            def direct_chat_ids():
                return set()

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["baseline_at"] = "2026-07-19T11:59:00+00:00"
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()
        assistant._invalidate_pending_for_room = mock.Mock()

        assistant._poll_kakao()

        self.assertNotIn("group-1", assistant.state["room_buffers"])


if __name__ == "__main__":
    unittest.main()
