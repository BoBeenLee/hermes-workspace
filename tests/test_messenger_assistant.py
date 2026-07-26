import contextlib
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/hermes/messenger_assistant.py"
SPEC = importlib.util.spec_from_file_location("messenger_assistant", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

INSTALLER_PATH = Path(__file__).resolve().parents[1] / "scripts/hermes/install_messenger_assistant.py"
INSTALLER_SPEC = importlib.util.spec_from_file_location("install_messenger_assistant", INSTALLER_PATH)
assert INSTALLER_SPEC and INSTALLER_SPEC.loader
installer = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(installer)


class MessengerAssistantPolicyTests(unittest.TestCase):
    def test_kakao_poller_uses_persistent_thirty_second_fixed_interval(self):
        payload = installer.kakao_poller_payload(
            Path("/profile/scripts/messenger_assistant.py"),
            Path("/profile/messenger-assistant/config.json"),
            Path("/profile/messenger-assistant"),
        )

        self.assertTrue(payload["RunAtLoad"])
        self.assertTrue(payload["KeepAlive"])
        self.assertNotIn("--discord-listen", payload["ProgramArguments"])
        interval_index = payload["ProgramArguments"].index("--poll-interval-seconds")
        self.assertEqual(payload["ProgramArguments"][interval_index + 1], "30")

    def test_fixed_poll_deadline_preserves_start_interval_and_skips_overrun(self):
        self.assertEqual(module.next_poll_deadline(100.0, 140.0, 30), 160.0)
        self.assertEqual(module.next_poll_deadline(100.0, 161.0, 30), 190.0)

    def test_legacy_cron_record_finds_job_id_and_state(self):
        listed = mock.Mock(
            stdout="""
  643add69262e [active]
    Name:      jarvis-messenger-assistant
    Schedule:  every 2m
"""
        )

        with mock.patch.object(installer, "run", return_value=listed):
            record = installer.legacy_cron_record()

        self.assertEqual(record, ("643add69262e", "active"))

    def test_default_state_is_fail_closed(self):
        state = module.default_state()
        self.assertFalse(state["enabled"])
        self.assertFalse(state["automatic_paused"])
        self.assertEqual(state["pending"], {})
        self.assertEqual(state["dialogue_state"], {})

    def test_start_does_not_rebuffer_pending_older_than_new_baseline(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["pending"]["old-card"] = {
            "status": "pending",
            "room_id": "123",
            "room_name": "친구",
            "entity_ids": ["old-message"],
            "latest_at": "2026-07-20T04:00:53+00:00",
        }
        assistant.discord = mock.Mock()
        assistant._room_is_sendable = mock.Mock(return_value=True)

        with mock.patch.object(
            module,
            "now_utc",
            return_value=dt.datetime(2026, 7, 26, 7, 21, 49, tzinfo=dt.timezone.utc),
        ):
            assistant._start()

        self.assertEqual(assistant.state["baseline_at"], "2026-07-26T07:21:49+00:00")
        self.assertEqual(assistant.state["pending"]["old-card"]["status"], "invalidated")
        self.assertEqual(assistant.state["room_buffers"], {})

    def test_chat_id_allowlist_requires_nonempty_numeric_ids(self):
        self.assertEqual(module.parse_allowed_chat_ids(["128426307555607"]), {"128426307555607"})
        for invalid in (None, [], ["room-1"], [""]):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                module.parse_allowed_chat_ids(invalid)
        self.assertEqual(module.parse_allowed_chat_ids(None, allow_empty=True), set())
        self.assertEqual(module.parse_allowed_chat_ids([], allow_empty=True), set())

    def test_gateway_identity_supports_json_pid_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir)
            (profile / "gateway.pid").write_text(
                json.dumps({"pid": 55932, "kind": "hermes-gateway"}),
                encoding="utf-8",
            )
            completed = mock.Mock(stdout="Sun Jul 19 23:38:40 2026\n")
            with mock.patch.object(module.subprocess, "run", return_value=completed):
                identity = module.gateway_identity(profile)

        self.assertEqual(identity, "55932:Sun Jul 19 23:38:40 2026")

    def test_discord_text_is_split_under_limit(self):
        chunks = module.split_discord("a" * 4001, limit=1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))
        self.assertEqual("".join(chunks), "a" * 4001)

    def test_fallback_model_forces_approval(self):
        reason = module.automatic_reply_block_reason(
            {
                "reply": "안녕!",
                "confidence": 1,
                "flags": {},
            },
            {"model": "openai/gpt-oss-120b", "provider": "groq"},
        )
        self.assertIn("fallback", reason)

    def test_confidence_below_point_seven_requires_approval(self):
        reason = module.automatic_reply_block_reason(
            {"reply": "답장", "confidence": 0.69, "flags": {}},
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertIn("0.69", reason)

    def test_non_finite_confidence_requires_approval(self):
        reason = module.automatic_reply_block_reason(
            {"reply": "답장", "confidence": "nan", "flags": {}},
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertIn("0.00", reason)

    def test_confidence_point_seven_allows_every_flag(self):
        flags = {name: True for name in module.POLICY_FLAG_NAMES}
        reason = module.automatic_reply_block_reason(
            {"reply": "확인했어", "confidence": 0.70, "flags": flags},
            {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER},
        )
        self.assertEqual(reason, "")
        audit = module.classification_audit(
            {"intent": "other", "reply_kind": "answer", "confidence": 0.70, "flags": flags}
        )
        self.assertIn("money_contract", audit)
        self.assertIn("auth_secret", audit)

    def test_classifier_contract_covers_weather_status_and_clarification(self):
        prompt = module.classification_prompt("친구", [], [], [])
        self.assertIn('"intent":"weather|assistant_status|other"', prompt)
        self.assertIn('"reply_kind":"answer|clarification"', prompt)
        self.assertIn('"weather_location":""', prompt)
        self.assertIn("0.70", prompt)

    def test_intent_router_prompt_excludes_recent_context_and_memory(self):
        prompt = module.intent_routing_prompt(
            "친구",
            [{"entity_id": "new-1", "text": "비빔밥..?"}],
            {},
        )
        self.assertIn("비빔밥", prompt)
        self.assertNotIn("recent_context", prompt)
        self.assertNotIn("long_term_memory", prompt)

    def test_weather_lookup_recognizes_any_current_location_question(self):
        self.assertTrue(module.is_weather_lookup("하남 오늘 날씨"))
        self.assertTrue(module.is_weather_lookup("서울 현재 날씨 알려줘"))
        self.assertFalse(module.is_weather_lookup("하남 맛집"))

    def test_open_meteo_resolves_unambiguous_seoul_and_validates_forecast(self):
        observed = module.now_utc().astimezone(module.KST).replace(second=0, microsecond=0)
        terminal = mock.Mock()
        terminal.fetch_json.side_effect = [
            {
                "results": [
                    {
                        "name": "서울특별시",
                        "admin1": "서울특별시",
                        "country": "대한민국",
                        "latitude": 37.566,
                        "longitude": 126.9784,
                        "population": 10349312,
                    },
                    {"name": "Séoulétié", "latitude": 8.0, "longitude": 13.0, "population": 882},
                ]
            },
            {
                "latitude": 37.55,
                "longitude": 127.0,
                "utc_offset_seconds": 32400,
                "current": {
                    "time": observed.replace(tzinfo=None).isoformat(timespec="minutes"),
                    "temperature_2m": 28.5,
                    "apparent_temperature": 33.0,
                    "relative_humidity_2m": 72,
                    "precipitation": 0,
                    "weather_code": 2,
                },
                "daily": {
                    "temperature_2m_max": [31],
                    "temperature_2m_min": [24],
                    "precipitation_probability_max": [60],
                },
            },
        ]
        weather = module.OpenMeteoWeather(terminal)

        reply, evidence = weather.resolve("Seoul")

        self.assertIn("서울특별시 현재 날씨는 구름 조금, 28.5°C", reply)
        self.assertIn("최대 강수확률은 60%", reply)
        self.assertEqual(evidence["source_name"], "Open-Meteo")
        self.assertIn("name=Seoul", terminal.fetch_json.call_args_list[0].args[0])
        self.assertIn(module.OPEN_METEO_FORECAST_HOST, terminal.fetch_json.call_args_list[1].args[0])

    def test_open_meteo_rejects_ambiguous_place(self):
        terminal = mock.Mock()
        terminal.fetch_json.return_value = {
            "results": [
                {"name": "광주광역시", "latitude": 35.1, "longitude": 126.8, "population": 1400000},
                {"name": "광주시", "latitude": 37.4, "longitude": 127.2, "population": 81000},
            ]
        }
        with self.assertRaisesRegex(RuntimeError, "여러 개"):
            module.OpenMeteoWeather(terminal).resolve("Gwangju")

    def test_open_meteo_rejects_stale_forecast(self):
        stale = (module.now_utc().astimezone(module.KST) - dt.timedelta(hours=2)).replace(tzinfo=None)
        place = {"name": "서울", "latitude": 37.566, "longitude": 126.9784}
        forecast = {
            "latitude": 37.55,
            "longitude": 127.0,
            "utc_offset_seconds": 32400,
            "current": {"time": stale.isoformat(timespec="minutes")},
            "daily": {},
        }
        with self.assertRaisesRegex(RuntimeError, "현재 시각"):
            module.OpenMeteoWeather._format(place, forecast, "Seoul", "geo", "forecast")

    def test_read_only_terminal_requires_exact_recorded_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir)
            database = profile / "state.db"
            url = "https://geocoding-api.open-meteo.com/v1/search?name=Seoul"
            command = f"/usr/bin/curl --fail --silent --show-error --max-time 20 '{url}'"
            calls = [
                {
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps(
                            {
                                "command": command,
                                "background": False,
                                "timeout": 30,
                                "pty": False,
                                "notify_on_complete": False,
                            }
                        ),
                    }
                }
            ]
            content = json.dumps({"output": json.dumps({"results": []}), "exit_code": 0, "error": None})
            with contextlib.closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
                    "content TEXT, tool_calls TEXT, tool_name TEXT)"
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, tool_calls) VALUES(?,?,?)",
                    ("terminal-session", "assistant", json.dumps(calls)),
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, content, tool_name) VALUES(?,?,?,?)",
                    ("terminal-session", "tool", content, "terminal"),
                )
                connection.commit()
            usage = {
                "model": module.PRIMARY_MODEL,
                "provider": module.PRIMARY_PROVIDER,
                "session_id": "terminal-session",
            }
            terminal = module.JarvisReadOnlyTerminal(Path("/tmp/hermes"), "jarvis", profile)
            with mock.patch.object(module, "run_hermes_json", return_value=({"ok": True}, usage)) as run:
                result = terminal.fetch_json(url)

        self.assertEqual(result, {"results": []})
        self.assertEqual(run.call_args.kwargs["toolsets"], "terminal")

    @staticmethod
    def _assistant_for_events(events):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.memory = module.default_memory()
        assistant.config = {"profile": "jarvis"}
        assistant.allowed_chat_ids = {"room-1"}
        assistant.hermes_bin = Path("/tmp/hermes")
        assistant.kakao = mock.Mock()
        assistant.kakao.preview.return_value = {"observed": [{"events": events}]}
        assistant.weather = mock.Mock()
        assistant.discord = mock.Mock()
        assistant._send_automatic = mock.Mock()
        assistant._create_approval_card = mock.Mock()
        return assistant

    def test_missing_weather_location_auto_asks_in_kakaotalk(self):
        event = {
            "entity_id": "message-1",
            "timestamp": module.iso_now(),
            "sender_name": "친구",
            "is_from_me": False,
            "message_type": "text",
            "snippet": "오늘 날씨 어때?",
        }
        assistant = self._assistant_for_events([event])
        result = {
            "intent": "weather",
            "reply_kind": "clarification",
            "reply": "",
            "summary": "날씨 질문",
            "reason": "지역 누락",
            "confidence": 0.80,
            "weather_location": "",
            "flags": {},
            "memory_updates": [
                {"key": "weather_requires_location", "value": "true", "confidence": 1, "secret_or_auth": False}
            ],
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}
        with mock.patch.object(module, "run_hermes_json", return_value=(result, usage)):
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["message-1"], "last_at": event["timestamp"]},
            )

        assistant.weather.resolve.assert_not_called()
        assistant._create_approval_card.assert_not_called()
        self.assertEqual(assistant._send_automatic.call_args.args[3], module.WEATHER_LOCATION_QUESTION)
        self.assertEqual(assistant.memory["contacts"], {})

    def test_weather_followup_location_resolves_and_auto_sends(self):
        earlier = {
            "entity_id": "message-1",
            "timestamp": (module.now_utc() - dt.timedelta(minutes=2)).isoformat(),
            "sender_name": "친구",
            "is_from_me": False,
            "message_type": "text",
            "snippet": "오늘 날씨 어때?",
        }
        question = {
            "entity_id": "message-2",
            "timestamp": (module.now_utc() - dt.timedelta(minutes=1)).isoformat(),
            "sender_name": "나",
            "is_from_me": True,
            "message_type": "text",
            "snippet": f"{module.PREFIX} {module.WEATHER_LOCATION_QUESTION}",
        }
        answer = {
            "entity_id": "message-3",
            "timestamp": module.iso_now(),
            "sender_name": "친구",
            "is_from_me": False,
            "message_type": "text",
            "snippet": "서울",
        }
        assistant = self._assistant_for_events([earlier, question, answer])
        assistant.state["dialogue_state"]["room-1"] = {
            "pending_intent": "weather_location",
            "source_entity_id": "message-1",
            "created_at": (module.now_utc() - dt.timedelta(minutes=1)).isoformat(),
            "expires_at": (module.now_utc() + dt.timedelta(minutes=14)).isoformat(),
        }
        assistant.weather.resolve.return_value = (
            "서울특별시 현재 날씨는 맑음, 25°C(체감 26°C)야.",
            {"location": "서울특별시", "source_name": "Open-Meteo", "observed_at": module.iso_now()},
        )
        result = {
            "intent": "weather",
            "reply_kind": "answer",
            "reply": "",
            "summary": "서울 날씨",
            "reason": "문맥에서 지역 확인",
            "confidence": 0.80,
            "weather_location": "Seoul",
            "flags": {},
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}
        with mock.patch.object(module, "run_hermes_json", return_value=(result, usage)):
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["message-3"], "last_at": answer["timestamp"]},
            )

        assistant.weather.resolve.assert_called_once_with("Seoul")
        self.assertIn("서울특별시 현재 날씨는", assistant._send_automatic.call_args.args[3])
        self.assertIn("출처=Open-Meteo", assistant._send_automatic.call_args.args[5])
        self.assertNotIn("room-1", assistant.state["dialogue_state"])

    def test_weather_resolution_failure_creates_approval(self):
        event = {
            "entity_id": "message-1",
            "timestamp": module.iso_now(),
            "sender_name": "친구",
            "is_from_me": False,
            "message_type": "text",
            "snippet": "광주 오늘 날씨",
        }
        assistant = self._assistant_for_events([event])
        assistant.weather.resolve.side_effect = RuntimeError("날씨 지역 후보가 여러 개")
        result = {
            "intent": "weather",
            "reply_kind": "answer",
            "reply": "",
            "summary": "광주 날씨",
            "confidence": 0.95,
            "weather_location": "Gwangju",
            "flags": {},
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}
        with mock.patch.object(module, "run_hermes_json", return_value=(result, usage)):
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["message-1"], "last_at": event["timestamp"]},
            )

        assistant._send_automatic.assert_not_called()
        self.assertIn("지역 불명확", assistant._create_approval_card.call_args.args[5])

    def test_bibimbap_turn_cannot_be_routed_to_weather_from_old_memory(self):
        event = {
            "entity_id": "bibimbap-message",
            "timestamp": module.iso_now(),
            "sender_name": "나",
            "is_from_me": True,
            "message_type": "text",
            "snippet": "비빔밥..?",
        }
        assistant = self._assistant_for_events([event])
        assistant.memory = {
            "version": 1,
            "contacts": {
                "room-1": {
                    "name": "친구",
                    "facts": {
                        "weather_location": {
                            "value": "Hanam",
                            "confidence": 1.0,
                            "confirmed_at": module.iso_now(),
                        }
                    },
                }
            },
        }
        assistant.weather.resolve.return_value = (
            "하남 현재 날씨는 맑음이야.",
            {"location": "하남", "source_name": "Open-Meteo", "observed_at": module.iso_now()},
        )
        wrong = {
            "intent": "weather",
            "reply_kind": "answer",
            "reply": "하남 날씨를 확인할게.",
            "summary": "하남 날씨",
            "reason": "과거 기억에서 하남을 찾음",
            "confidence": 0.72,
            "weather_location": "Hanam",
            "flags": {},
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}

        with mock.patch.object(module, "run_hermes_json", return_value=(wrong, usage)):
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["bibimbap-message"], "last_at": event["timestamp"]},
            )

        assistant.weather.resolve.assert_not_called()
        assistant._send_automatic.assert_not_called()
        self.assertIn("날씨 근거", assistant._create_approval_card.call_args.args[5])

    def test_other_turn_routes_first_then_drafts_with_locked_intent(self):
        event = {
            "entity_id": "bibimbap-message",
            "timestamp": module.iso_now(),
            "sender_name": "나",
            "is_from_me": True,
            "message_type": "text",
            "snippet": "비빔밥..?",
        }
        assistant = self._assistant_for_events([event])
        route = {"intent": "other", "weather_location": "", "confidence": 0.9, "reason": "현재 턴"}
        draft = {
            "reply_kind": "answer",
            "reply": "비빔밥 좋지!",
            "summary": "비빔밥 선택",
            "reason": "현재 턴 응답",
            "confidence": 0.9,
            "flags": {},
            "memory_updates": [
                {
                    "kind": "preference",
                    "key": "좋아하는 음식",
                    "value": "비빔밥",
                    "confidence": 0.9,
                    "secret_or_auth": False,
                    "source_entity_ids": ["bibimbap-message"],
                }
            ],
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}

        with mock.patch.object(
            module,
            "run_hermes_json",
            side_effect=[(route, usage), (draft, usage)],
        ) as run:
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["bibimbap-message"], "last_at": event["timestamp"]},
            )

        self.assertEqual(run.call_count, 2)
        self.assertIn("Classify only the current", run.call_args_list[0].args[2])
        self.assertIn("locked intent other", run.call_args_list[1].args[2])
        self.assertEqual(assistant._send_automatic.call_args.args[3], "비빔밥 좋지!")

    def test_weather_word_does_not_override_router_other_intent(self):
        policy = module.ConversationPolicy()

        decision = policy.route_intent(
            [{"entity_id": "message-1", "text": "날씨 말고 비빔밥 먹을까?"}],
            {},
            {"intent": "other"},
        )

        self.assertEqual(decision, {"intent": "other", "block_reason": ""})

    def test_locked_other_draft_cannot_smuggle_weather_reply(self):
        event = {
            "entity_id": "bibimbap-message",
            "timestamp": module.iso_now(),
            "sender_name": "나",
            "is_from_me": True,
            "message_type": "text",
            "snippet": "비빔밥..?",
        }
        assistant = self._assistant_for_events([event])
        route = {"intent": "other", "weather_location": "", "confidence": 0.9, "reason": "현재 턴"}
        draft = {
            "reply_kind": "answer",
            "reply": "하남 날씨는 맑아.",
            "summary": "하남 날씨",
            "reason": "과거 문맥 오염",
            "confidence": 0.9,
            "flags": {},
            "memory_updates": [
                {
                    "kind": "preference",
                    "key": "좋아하는 음식",
                    "value": "비빔밥",
                    "confidence": 0.9,
                    "secret_or_auth": False,
                    "source_entity_ids": ["bibimbap-message"],
                }
            ],
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}

        with mock.patch.object(
            module,
            "run_hermes_json",
            side_effect=[(route, usage), (draft, usage)],
        ):
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["bibimbap-message"], "last_at": event["timestamp"]},
            )

        assistant.weather.resolve.assert_not_called()
        assistant._send_automatic.assert_not_called()
        self.assertIn("잠긴 현재 의도", assistant._create_approval_card.call_args.args[5])
        self.assertEqual(assistant.memory["contacts"], {})

    def test_assistant_status_is_friendly_and_hides_operations(self):
        event = {
            "entity_id": "message-1",
            "timestamp": module.iso_now(),
            "sender_name": "친구",
            "is_from_me": False,
            "message_type": "text",
            "snippet": "너의 상태는 어때?",
        }
        assistant = self._assistant_for_events([event])
        result = {
            "intent": "assistant_status",
            "reply_kind": "answer",
            "reply": "PID 123에서 MCP 폴링 중",
            "summary": "상태 질문",
            "confidence": 0.80,
            "weather_location": "",
            "flags": {},
            "memory_updates": [
                {"key": "last_query", "value": "assistant status", "confidence": 1, "secret_or_auth": False}
            ],
        }
        usage = {"model": module.PRIMARY_MODEL, "provider": module.PRIMARY_PROVIDER}
        with mock.patch.object(module, "run_hermes_json", return_value=(result, usage)):
            assistant._process_room_buffer(
                "room-1",
                {"room_name": "친구", "entity_ids": ["message-1"], "last_at": event["timestamp"]},
            )

        reply = assistant._send_automatic.call_args.args[3]
        self.assertEqual(reply, module.ASSISTANT_STATUS_REPLY)
        self.assertNotIn("PID", reply)
        self.assertNotIn("MCP", reply)
        self.assertEqual(assistant.memory["contacts"], {})

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

    def test_typed_memory_requires_allowed_kind_and_current_turn_source(self):
        valid = {
            "kind": "preference",
            "key": "좋아하는 음식",
            "value": "비빔밥",
            "confidence": 0.9,
            "secret_or_auth": False,
            "source_entity_ids": ["message-1"],
        }
        self.assertIsNotNone(module.sanitize_memory_update(valid, {"message-1"}))
        self.assertIsNone(module.sanitize_memory_update(valid, {"different-message"}))
        self.assertIsNone(
            module.sanitize_memory_update(
                {**valid, "kind": "weather", "key": "weather_location"},
                {"message-1"},
            )
        )
        self.assertIsNone(
            module.sanitize_memory_update(
                {
                    **valid,
                    "kind": "relationship",
                    "key": "watch_request_from_user",
                    "value": "User asked if AI watched the linked video.",
                },
                {"message-1"},
            )
        )

    def test_prune_migrates_legacy_memory_and_expires_dialogue_state(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"room-1"}
        assistant.state = module.default_state()
        assistant.state["dialogue_state"]["room-1"] = {
            "pending_intent": "weather_location",
            "expires_at": (module.now_utc() - dt.timedelta(seconds=1)).isoformat(),
        }
        assistant.memory = {
            "version": 1,
            "contacts": {
                "room-1": {
                    "name": "친구",
                    "facts": {
                        "weather_location": {
                            "value": "Hanam",
                            "confirmed_at": module.iso_now(),
                        }
                    },
                }
            },
        }

        assistant._prune_state()

        self.assertEqual(assistant.state["dialogue_state"], {})
        self.assertEqual(assistant.memory["contacts"], {})

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
        state["rate"]["rooms"]["r1"] = [module.iso_now()] * (module.ROOM_AUTO_REPLY_LIMIT - 1)
        allowed, reason = module.rate_allowed(state, "r1")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

        state["rate"]["rooms"]["r1"].append(module.iso_now())
        allowed, reason = module.rate_allowed(state, "r1")
        self.assertFalse(allowed)
        self.assertIn("채팅방", reason)
        self.assertIn("300회", reason)

        state = module.default_state()
        state["rate"]["global"] = [module.iso_now()] * module.GLOBAL_AUTO_REPLY_LIMIT
        allowed, reason = module.rate_allowed(state, "r2")
        self.assertFalse(allowed)
        self.assertIn("전체", reason)
        self.assertIn("100회", reason)

    def test_kakao_operations_are_routed_through_jarvis_agent_interface(self):
        client = module.JarvisKakaoAgent.__new__(module.JarvisKakaoAgent)
        client._call_tool = mock.Mock(return_value={"ok": True})

        client.auth_status()
        client.list_since("from", "until")
        client.preview("친구", "123")
        client.send("친구", "답장", dry_run=False, chat_id="chat-1")

        self.assertEqual(
            [call.args[0] for call in client._call_tool.call_args_list],
            ["auth_status", "list_new_messages_since", "preview_messages", "send_message"],
        )
        send_arguments = client._call_tool.call_args_list[-1].args[1]
        self.assertEqual(send_arguments["chat_id"], "chat-1")

    def test_jarvis_kakao_agent_uses_only_kakao_toolset_and_verified_session_result(self):
        client = module.JarvisKakaoAgent(Path("/tmp/hermes"), "jarvis", Path("/tmp/profile"))
        usage = {
            "model": module.PRIMARY_MODEL,
            "provider": module.PRIMARY_PROVIDER,
            "session_id": "session-1",
        }
        with mock.patch.object(module, "run_hermes_json", return_value=({"ok": True}, usage)) as run, mock.patch.object(
            module,
            "hermes_session_tool_payload",
            return_value={"ok": True, "auth_state": "ok"},
        ) as session_result:
            result = client.auth_status()

        self.assertTrue(result["ok"])
        self.assertEqual(result["hermes_session_id"], "session-1")
        self.assertEqual(run.call_args.kwargs["toolsets"], module.KAKAO_TOOLSET)
        self.assertIn("kakaotalk_mac.auth_status exactly once", run.call_args.args[2])
        session_result.assert_called_once_with(
            Path("/tmp/profile"),
            "session-1",
            module.KAKAO_TOOL_PREFIX + "auth_status",
            {"user_id": "", "kakaocli_bin": ""},
        )

    def test_kakao_tool_prompt_requires_empty_arguments_to_stay_empty(self):
        arguments = {"target": "이보빈", "skill_dir": "", "script_path": ""}
        prompt = module.jarvis_kakao_tool_prompt(
            "preview_messages",
            arguments,
        )

        self.assertIn("empty string", prompt)
        self.assertIn("Do not omit", prompt)
        self.assertIn("infer or substitute filesystem paths", prompt)
        exact_json = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        self.assertLess(prompt.index(exact_json), prompt.index("Call kakaotalk_mac.preview_messages"))

    def test_jarvis_session_result_counts_only_expected_send_message_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir)
            database = profile / "state.db"
            expected_tool = module.KAKAO_TOOL_PREFIX + "send_message"
            arguments = {"target": "친구", "message": "답장", "dry_run": True}
            fetch_tool = "web_fetch"
            calls = [
                {"function": {"name": fetch_tool, "arguments": json.dumps({"url": "https://example.com"})}},
                {"function": {"name": expected_tool, "arguments": json.dumps(arguments, ensure_ascii=False)}},
            ]
            tool_content = '<untrusted_tool_result source="mcp">\n' + json.dumps(
                {"result": json.dumps({"ok": True, "chat_id_validated": True})}
            ) + "\n</untrusted_tool_result>"
            with contextlib.closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
                    "content TEXT, tool_calls TEXT, tool_name TEXT)"
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, tool_calls) VALUES(?,?,?)",
                    ("session-1", "assistant", json.dumps(calls, ensure_ascii=False)),
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, content, tool_name) VALUES(?,?,?,?)",
                    ("session-1", "tool", json.dumps({"ok": True}), fetch_tool),
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, content, tool_name) VALUES(?,?,?,?)",
                    ("session-1", "tool", tool_content, expected_tool),
                )
                connection.commit()

            result = module.hermes_session_tool_payload(
                profile,
                "session-1",
                expected_tool,
                arguments,
            )

        self.assertEqual(result, {"ok": True, "chat_id_validated": True})

    def test_jarvis_session_result_reports_send_message_call_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir)
            database = profile / "state.db"
            expected_tool = module.KAKAO_TOOL_PREFIX + "send_message"
            fetch_tool = "web_fetch"
            calls = [
                {"function": {"name": fetch_tool, "arguments": json.dumps({"url": "https://example.com"})}}
            ]
            with contextlib.closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
                    "content TEXT, tool_calls TEXT, tool_name TEXT)"
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, tool_calls) VALUES(?,?,?)",
                    ("session-1", "assistant", json.dumps(calls)),
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, content, tool_name) VALUES(?,?,?,?)",
                    ("session-1", "tool", json.dumps({"ok": True}), fetch_tool),
                )
                connection.commit()

            with self.assertRaisesRegex(
                RuntimeError,
                "send_message 호출 수 0회, 결과 수 0회",
            ):
                module.hermes_session_tool_payload(
                    profile,
                    "session-1",
                    expected_tool,
                    {"target": "친구", "message": "답장", "dry_run": True},
                )

    def test_jarvis_session_result_reports_duplicate_send_message_calls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir)
            database = profile / "state.db"
            expected_tool = module.KAKAO_TOOL_PREFIX + "send_message"
            arguments = {"target": "친구", "message": "답장", "dry_run": True}
            call = {"function": {"name": expected_tool, "arguments": json.dumps(arguments)}}
            with contextlib.closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
                    "content TEXT, tool_calls TEXT, tool_name TEXT)"
                )
                connection.execute(
                    "INSERT INTO messages(session_id, role, tool_calls) VALUES(?,?,?)",
                    ("session-1", "assistant", json.dumps([call, call])),
                )
                connection.executemany(
                    "INSERT INTO messages(session_id, role, content, tool_name) VALUES(?,?,?,?)",
                    [
                        ("session-1", "tool", json.dumps({"ok": True}), expected_tool),
                        ("session-1", "tool", json.dumps({"ok": True}), expected_tool),
                    ],
                )
                connection.commit()

            with self.assertRaisesRegex(
                RuntimeError,
                "send_message 호출 수 2회, 결과 수 2회",
            ):
                module.hermes_session_tool_payload(
                    profile,
                    "session-1",
                    expected_tool,
                    arguments,
                )

    def test_direct_room_requires_adapter_direct_evidence_over_mcp(self):
        client = module.JarvisKakaoAgent.__new__(module.JarvisKakaoAgent)
        client._call_tool = mock.Mock(
            return_value={
                "matches": [
                    {
                        "chat_id": "123",
                        "sources": ["visible_chats", "NTUser.directChatId"],
                        "direct_chat_kind": "human",
                    }
                ]
            }
        )

        self.assertTrue(client.is_direct_chat("123", "친구"))
        client._call_tool.assert_called_once_with(
            "find_chat",
            {
                "query": "친구",
                "limit": 20,
                "scan_limit": 100,
                "kakaocli_bin": "",
                "user_id": "",
            },
        )

    def test_direct_room_rejects_non_human_adapter_classification(self):
        client = module.JarvisKakaoAgent.__new__(module.JarvisKakaoAgent)
        client._call_tool = mock.Mock(
            return_value={
                "matches": [
                    {
                        "chat_id": "4928063170323458",
                        "sources": ["visible_chats", "NTUser.directChatId"],
                        "direct_chat_kind": "non_human",
                        "direct_chat_reasons": [
                            "user_type:1",
                            "verification_type:BUSINESS",
                            "alimtalk",
                        ],
                    }
                ]
            }
        )

        self.assertFalse(client.is_direct_chat("4928063170323458", "비씨카드"))

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
        assistant.allowed_chat_ids = {"direct-1"}
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
        assistant.allowed_chat_ids = {"group-1"}
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()
        assistant._invalidate_pending_for_room = mock.Mock()

        assistant._poll_kakao()

        self.assertNotIn("group-1", assistant.state["room_buffers"])

    def test_poll_ignores_non_allowlisted_direct_rooms_including_from_me(self):
        class FakeKakao:
            @staticmethod
            def list_since(_since, _until):
                return {
                    "rooms": [
                        {
                            "chat_id": "128426307555607",
                            "display_name": "이보빈",
                            "new_messages": [
                                {
                                    "entity_id": "allowed-message",
                                    "timestamp": "2026-07-19T12:00:00+00:00",
                                    "is_from_me": True,
                                    "snippet": "오늘 날씨 어때?",
                                }
                            ],
                        },
                        {
                            "chat_id": "999",
                            "display_name": "다른 사람",
                            "new_messages": [
                                {
                                    "entity_id": "blocked-message",
                                    "timestamp": "2026-07-19T12:00:01+00:00",
                                    "is_from_me": True,
                                    "snippet": "너의 상태는?",
                                }
                            ],
                        },
                    ]
                }

            @staticmethod
            def is_direct_chat(_chat_id, _display_name):
                return True

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["baseline_at"] = "2026-07-19T11:59:00+00:00"
        assistant.allowed_chat_ids = {"128426307555607"}
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()
        assistant._invalidate_pending_for_room = mock.Mock()

        assistant._poll_kakao()

        self.assertEqual(set(assistant.state["room_buffers"]), {"128426307555607"})
        self.assertNotIn("999", assistant.state["rooms"])

    def test_poll_all_direct_scope_buffers_only_adapter_verified_direct_rooms(self):
        class FakeKakao:
            @staticmethod
            def list_since(_since, _until):
                return {
                    "rooms": [
                        {
                            "chat_id": "direct-2",
                            "display_name": "새 친구",
                            "new_messages": [
                                {
                                    "entity_id": "direct-message",
                                    "timestamp": "2026-07-19T12:00:00+00:00",
                                    "is_from_me": False,
                                    "snippet": "안녕",
                                }
                            ],
                        },
                        {
                            "chat_id": "group-2",
                            "display_name": "단체방",
                            "new_messages": [
                                {
                                    "entity_id": "group-message",
                                    "timestamp": "2026-07-19T12:00:01+00:00",
                                    "is_from_me": False,
                                    "snippet": "안녕",
                                }
                            ],
                        },
                    ]
                }

            @staticmethod
            def is_direct_chat(chat_id, _display_name):
                return chat_id == "direct-2"

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["baseline_at"] = "2026-07-19T11:59:00+00:00"
        assistant.allow_all_direct_chats = True
        assistant.allowed_chat_ids = set()
        assistant.kakao = FakeKakao()
        assistant.discord = mock.Mock()
        assistant._invalidate_pending_for_room = mock.Mock()

        assistant._poll_kakao()

        self.assertEqual(set(assistant.state["room_buffers"]), {"direct-2"})
        self.assertTrue(assistant.state["rooms"]["direct-2"]["is_direct"])
        self.assertFalse(assistant._room_is_sendable("group-2"))

    def test_all_direct_scope_rejects_stale_direct_cache_without_current_policy_version(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allow_all_direct_chats = True
        assistant.allowed_chat_ids = set()
        assistant.state = module.default_state()
        assistant.state["rooms"]["4928063170323458"] = {
            "name": "비씨카드",
            "is_direct": True,
            "direct_evidence": "NTUser.directChatId via Hermes MCP",
        }

        self.assertFalse(assistant._room_is_sendable("4928063170323458"))

    def test_ready_buffer_waits_exactly_five_seconds_after_latest_message(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["room_buffers"] = {
            "123": {
                "room_name": "친구",
                "entity_ids": ["message-1"],
                "first_at": "2026-07-19T12:00:00+00:00",
                "last_at": "2026-07-19T12:00:00+00:00",
            }
        }
        assistant.discord = mock.Mock()
        assistant._process_room_buffer = mock.Mock()

        with mock.patch.object(
            module,
            "now_utc",
            return_value=dt.datetime(2026, 7, 19, 12, 0, 4, tzinfo=dt.timezone.utc),
        ):
            assistant._process_ready_buffers()
        assistant._process_room_buffer.assert_not_called()
        self.assertIn("123", assistant.state["room_buffers"])

        with mock.patch.object(
            module,
            "now_utc",
            return_value=dt.datetime(2026, 7, 19, 12, 0, 5, tzinfo=dt.timezone.utc),
        ):
            assistant._process_ready_buffers()
        assistant._process_room_buffer.assert_called_once()
        self.assertNotIn("123", assistant.state["room_buffers"])

    def test_processing_failure_keeps_buffer_for_next_cron_retry(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant.state["room_buffers"] = {
            "128426307555607": {
                "room_name": "이보빈",
                "entity_ids": ["message-1"],
                "first_at": "2026-07-19T14:46:12+00:00",
                "last_at": "2026-07-19T14:46:12+00:00",
            }
        }
        assistant.discord = mock.Mock()
        assistant._process_room_buffer = mock.Mock(
            side_effect=RuntimeError("Jarvis가 MCP 호출 인자 skill_dir를 변경했습니다")
        )

        with mock.patch.object(module, "now_utc", return_value=dt.datetime(2026, 7, 19, 15, 0, tzinfo=dt.timezone.utc)):
            assistant._process_ready_buffers()

        self.assertIn("128426307555607", assistant.state["room_buffers"])
        self.assertEqual(assistant.state["stats"]["failed"], 1)
        assistant.discord.send.assert_called_once()

        assistant._process_room_buffer = mock.Mock(return_value=None)
        with mock.patch.object(module, "now_utc", return_value=dt.datetime(2026, 7, 19, 15, 2, tzinfo=dt.timezone.utc)):
            assistant._process_ready_buffers()

        self.assertNotIn("128426307555607", assistant.state["room_buffers"])

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
        assistant.allowed_chat_ids = {"123"}
        assistant.kakao = FakeKakao()
        assistant._verify_sent = mock.Mock(side_effect=[False, True])

        self.assertTrue(assistant._send_verified("친구", "123", "답장"))
        self.assertEqual(
            assistant.kakao.calls,
            [
                ("친구", "답장", False, "123"),
            ],
        )

    def test_verified_send_does_not_treat_old_identical_message_as_current_send(self):
        message = f"{module.PREFIX} 응, 지금 정상적으로 작동 중이야 🙂"

        class FakeKakao:
            def __init__(self):
                self.send_calls = 0

            def preview(self, _target, _chat_id):
                events = [
                    {
                        "entity_id": "old-send",
                        "timestamp": "2026-07-19T12:00:00+00:00",
                        "is_from_me": True,
                        "snippet": message,
                    }
                ]
                if self.send_calls:
                    events.append(
                        {
                            "entity_id": "current-send",
                            "timestamp": "2026-07-19T13:00:01+00:00",
                            "is_from_me": True,
                            "snippet": message,
                        }
                    )
                return {"observed": [{"events": events}]}

            def send(self, _target, _message, *, dry_run, chat_id=None):
                self.send_calls += 1
                return {"ok": True, "message_sent": True, "dry_run": dry_run, "chat_id": chat_id}

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"123"}
        assistant.kakao = FakeKakao()

        with mock.patch.object(
            module,
            "now_utc",
            return_value=dt.datetime(2026, 7, 19, 13, 0, tzinfo=dt.timezone.utc),
        ):
            self.assertTrue(assistant._send_verified("친구", "123", message))

        self.assertEqual(assistant.kakao.send_calls, 1)

    def test_verified_send_preserves_idempotency_after_trigger_time(self):
        message = f"{module.PREFIX} 동일 요청 답변"

        class FakeKakao:
            send_calls = 0

            @staticmethod
            def preview(_target, _chat_id):
                return {
                    "observed": [
                        {
                            "events": [
                                {
                                    "entity_id": "current-send",
                                    "timestamp": "2026-07-19T13:00:01+00:00",
                                    "is_from_me": True,
                                    "snippet": message,
                                }
                            ]
                        }
                    ]
                }

            @staticmethod
            def send(_target, _message, *, dry_run, chat_id=None):
                FakeKakao.send_calls += 1
                return {"ok": True, "dry_run": dry_run, "chat_id": chat_id}

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"123"}
        assistant.kakao = FakeKakao()

        self.assertTrue(
            assistant._send_verified(
                "친구",
                "123",
                message,
                not_before="2026-07-19T13:00:00+00:00",
            )
        )
        self.assertEqual(FakeKakao.send_calls, 0)

    def test_automatic_send_uses_latest_incoming_timestamp_as_verification_boundary(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.state = module.default_state()
        assistant._send_verified = mock.Mock(return_value=True)
        assistant._touch_room_stats = mock.Mock()
        assistant.discord = mock.Mock()
        assistant.discord.send.return_value = {"id": "audit-1"}
        latest = "2026-07-19T13:00:05+00:00"

        assistant._send_automatic(
            "123",
            "친구",
            [
                {"timestamp": "2026-07-19T13:00:00+00:00", "text": "첫 메시지"},
                {"timestamp": latest, "text": "마지막 메시지"},
            ],
            "답장",
            "요약",
            "감사",
        )

        assistant._send_verified.assert_called_once_with(
            "친구",
            "123",
            f"{module.PREFIX} 답장",
            not_before=module.parse_time(latest),
        )

    def test_verified_send_fails_closed_with_jarvis_mcp_reason_and_no_fallback(self):
        class FakeKakao:
            calls = 0

            @staticmethod
            def send(_target, _message, *, dry_run, chat_id=None):
                FakeKakao.calls += 1
                return {"ok": False, "error": "kmsg_chats_timeout"}

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"123"}
        assistant.kakao = FakeKakao()
        assistant._verify_sent = mock.Mock(return_value=False)

        with self.assertRaisesRegex(RuntimeError, "kmsg_chats_timeout"):
            assistant._send_verified("친구", "123", "답장")
        self.assertEqual(FakeKakao.calls, 1)

    def test_verified_send_distinguishes_send_failure_from_destination_scan(self):
        class FakeKakao:
            calls = 0

            @staticmethod
            def send(_target, _message, *, dry_run, chat_id=None):
                FakeKakao.calls += 1
                assert dry_run is False
                return {
                    "ok": False,
                    "operation": "send_message",
                    "dry_run": False,
                    "phase": "resolve_destination",
                    "scan_limit": 20,
                }

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"123"}
        assistant.kakao = FakeKakao()
        assistant._verify_sent = mock.Mock(return_value=False)

        with self.assertRaisesRegex(RuntimeError, "stage=message_send.*reason=command_failed"):
            assistant._send_verified("친구", "123", "답장")
        self.assertEqual(FakeKakao.calls, 1)

    def test_verified_send_distinguishes_read_back_mismatch(self):
        class FakeKakao:
            @staticmethod
            def send(_target, _message, *, dry_run, chat_id=None):
                assert dry_run is False
                return {
                    "ok": True,
                    "operation": "send_message",
                    "dry_run": False,
                    "phase": "resolve_destination",
                    "scan_limit": 20,
                }

        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"123"}
        assistant.kakao = FakeKakao()
        assistant._verify_sent = mock.Mock(return_value=False)

        with self.assertRaisesRegex(RuntimeError, "stage=delivery_verify.*reason=read_back_mismatch"):
            assistant._send_verified("친구", "123", "답장")

    def test_kakao_failure_detail_preserves_resolution_stage_and_reason(self):
        detail = module.kakao_failure_detail(
            {
                "error": "kmsg_destination_not_found",
                "failure_stage": "destination_match",
                "failure_reason": "target_not_in_recent_chats",
                "message": "No target matched the recent 20 chats.",
            }
        )

        self.assertIn("kmsg_destination_not_found", detail)
        self.assertIn("stage=destination_match", detail)
        self.assertIn("reason=target_not_in_recent_chats", detail)
        self.assertIn("recent 20 chats", detail)

    def test_kakao_failure_detail_preserves_installed_mcp_scan_diagnostics(self):
        detail = module.kakao_failure_detail(
            {
                "error": "destination_scan_timeout",
                "phase": "resolve_destination",
                "scan_limit": 20,
                "elapsed_ms": 30001,
                "candidate_count": 0,
                "message": "Recent KakaoTalk destination scan timed out.",
            }
        )

        self.assertIn("destination_scan_timeout", detail)
        self.assertIn("stage=resolve_destination", detail)
        self.assertIn("scan_limit=20", detail)
        self.assertIn("elapsed_ms=30001", detail)
        self.assertIn("candidate_count=0", detail)

    def test_verified_send_rejects_non_allowlisted_room_before_any_mcp_call(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allowed_chat_ids = {"128426307555607"}
        assistant.kakao = mock.Mock()
        assistant._verify_sent = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "1:1 방 정책 거부"):
            assistant._send_verified("다른 사람", "999", "답장")

        assistant._verify_sent.assert_not_called()
        assistant.kakao.send.assert_not_called()

    def test_verified_send_all_direct_scope_requires_cached_adapter_evidence(self):
        assistant = module.MessengerAssistant.__new__(module.MessengerAssistant)
        assistant.allow_all_direct_chats = True
        assistant.allowed_chat_ids = set()
        assistant.state = module.default_state()
        assistant.kakao = mock.Mock()
        assistant._verify_sent = mock.Mock(return_value=True)

        with self.assertRaisesRegex(RuntimeError, "1:1 방 정책 거부"):
            assistant._send_verified("검증 전 방", "999", "답장")

        assistant.state["rooms"]["999"] = {
            "name": "검증된 친구",
            "is_direct": True,
            "direct_policy_version": module.DIRECT_CHAT_POLICY_VERSION,
        }
        self.assertTrue(assistant._send_verified("검증된 친구", "999", "답장"))


if __name__ == "__main__":
    unittest.main()
