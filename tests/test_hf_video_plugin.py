"""Tests for the hf_video plugin.

``agent.*`` lives in the hermes-agent install, not in this repo, so the symbols
the plugin imports are stubbed with their real signatures. ``requests`` is a
hermes-agent dependency, so it is stubbed too and every test drives the code
through a scripted fake -- no network, no token, no GPU quota spent.
"""

import json
import os
import stat
import sys
import tempfile
import time
import types
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _install_agent_stub():
    """``agent.video_gen_provider``: the ABC plus the response/media helpers.

    Signatures mirror the real module (checked against the DGX install): only
    ``name`` and ``generate`` are abstract, and ``success_response`` merges
    ``extra`` without overriding the standard keys.
    """
    agent = sys.modules.setdefault("agent", types.ModuleType("agent"))
    agent.__path__ = []  # noqa: SLF001 - make it a package so submodules import

    module = types.ModuleType("agent.video_gen_provider")
    module.DEFAULT_ASPECT_RATIO = "16:9"
    module.DEFAULT_RESOLUTION = "720p"

    class VideoGenProvider:
        @property
        def display_name(self):
            return self.name

        def is_available(self):
            return True

        def list_models(self):
            return []

    def success_response(*, video, model, prompt, modality="text", aspect_ratio="",
                         duration=0, provider, extra=None):
        payload = {
            "success": True, "video": video, "model": model, "prompt": prompt,
            "modality": modality, "aspect_ratio": aspect_ratio,
            "duration": int(duration) if duration else 0, "provider": provider,
        }
        for key, value in (extra or {}).items():
            payload.setdefault(key, value)
        return payload

    def error_response(*, error, error_type="provider_error", provider="", model="",
                       prompt="", aspect_ratio=""):
        return {
            "success": False, "video": None, "error": error, "error_type": error_type,
            "model": model, "prompt": prompt, "aspect_ratio": aspect_ratio, "provider": provider,
        }

    module.VideoGenProvider = VideoGenProvider
    module.success_response = success_response
    module.error_response = error_response
    module.save_url_video = lambda url, **kw: Path("/tmp/cache/videos/hfspace_test.mp4")
    sys.modules["agent.video_gen_provider"] = module
    agent.video_gen_provider = module
    return module


def _install_requests_stub():
    """Prefer the real package, stub only what is missing.

    Every test patches ``space.requests`` with its own fake, so the module-level
    import just has to succeed -- and leaving the real one in place is what makes
    the live drift check runnable. Additive because ``test_comfyui_plugin``
    registers a bare ``requests`` and discover imports it first, so "create it
    only if absent" would leave this suite without ``RequestException``."""
    try:
        import requests as real  # noqa: PLC0415

        if hasattr(real, "RequestException"):
            return real
    except Exception:  # noqa: BLE001 - not installed on a bare checkout
        pass
    module = sys.modules.get("requests") or types.ModuleType("requests")
    if not hasattr(module, "RequestException"):
        class RequestException(Exception):
            pass

        module.RequestException = RequestException
    sys.modules["requests"] = module
    return module


_AGENT = _install_agent_stub()
_REQUESTS = _install_requests_stub()
sys.path.insert(0, str(REPO))

from plugins.hf_video import space  # noqa: E402
import plugins.hf_video as plugin  # noqa: E402

PROMPT = "a paper boat drifting down a rain puddle"
LTX23_URL = "https://lightricks-ltx-2-3.hf.space/gradio_api/file=/tmp/gradio/a/out.mp4"
DISTILLED_URL = "https://lightricks-ltx-video-distilled.hf.space/gradio_api/file=/tmp/b/out.mp4"


class _Resp:
    """One scripted HTTP response. Doubles as the SSE stream context manager."""

    def __init__(self, status=200, payload=None, text=None, lines=()):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self._lines = list(lines)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def iter_lines(self, decode_unicode=False):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeHTTP:
    """Scripted ``requests`` replacement recording every call it serves."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.posts = []
        self.gets = []
        self.RequestException = _REQUESTS.RequestException

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        return self._next()

    def get(self, url, headers=None, stream=False, timeout=None):
        self.gets.append({"url": url, "headers": headers or {}})
        return self._next()

    def _next(self):
        if not self.queue:
            raise AssertionError("fake HTTP ran out of scripted responses")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _accepted(event_id="evt-1"):
    return _Resp(200, payload={"event_id": event_id})


def _completed(url, wrapped=False):
    node = {"video": {"url": url}, "subtitles": None} if wrapped else {"url": url, "path": "/tmp/x"}
    return _Resp(200, lines=["event: complete", f"data: {json.dumps([node, 42])}"])


def _errored():
    return _Resp(200, lines=["event: heartbeat", "data: null", "event: error", "data: null"])


def _down():
    return _Resp(503, text="Your space is in error, check its status on hf.co")


class RegistrationTest(unittest.TestCase):
    """register() must put exactly one provider in the video_gen registry."""

    def test_registers_one_video_provider(self):
        ctx = unittest.mock.Mock()
        plugin.register(ctx)

        ctx.register_video_gen_provider.assert_called_once()
        provider = ctx.register_video_gen_provider.call_args[0][0]
        self.assertEqual(provider.name, "hfspace")
        # A new tool would land in a toolset nobody passes; the slot is the point.
        ctx.register_tool.assert_not_called()

    def test_is_available_touches_no_network(self):
        # The picker calls is_available() on every repaint, so a probe here would
        # put an HTTP round-trip in the UI.
        fake = _FakeHTTP()
        with unittest.mock.patch.object(space, "requests", fake):
            self.assertTrue(plugin.HFSpaceVideoGenProvider().is_available())
        self.assertEqual((fake.posts, fake.gets), ([], []))


class ArgumentOrderTest(unittest.TestCase):
    """The positional array is the whole contract, so build() and the recorded
    parameter order must not drift apart."""

    def test_every_space_builds_as_many_args_as_it_records(self):
        for item in space.SPACES:
            args = item.build(prompt=PROMPT, duration=3, width=1280, height=704,
                              seed=None, negative_prompt=None)
            self.assertEqual(len(args), len(item.params), item.subdomain)

    def test_ltx23_array_matches_recorded_positions(self):
        args = space.SPACES[0].build(prompt=PROMPT, duration=3, width=1280, height=704,
                                     seed=None, negative_prompt=None)
        by_name = dict(zip(space.SPACES[0].params, args))
        self.assertEqual(by_name["prompt"], PROMPT)
        self.assertEqual(by_name["duration"], 3.0)
        self.assertEqual(by_name["height"], 704)
        self.assertEqual(by_name["width"], 1280)
        self.assertIsNone(by_name["input_image"])
        self.assertFalse(by_name["enhance_prompt"])
        self.assertTrue(by_name["randomize_seed"])

    def test_explicit_seed_turns_randomize_off(self):
        args = space.SPACES[0].build(prompt=PROMPT, duration=3, width=640, height=640,
                                     seed=7, negative_prompt=None)
        by_name = dict(zip(space.SPACES[0].params, args))
        self.assertEqual(by_name["seed"], 7)
        self.assertFalse(by_name["randomize_seed"])


class ExtractUrlTest(unittest.TestCase):
    def test_reads_both_payload_shapes(self):
        flat = [{"url": LTX23_URL}, 42]
        wrapped = [{"video": {"url": DISTILLED_URL}, "subtitles": None}, 7]
        self.assertEqual(space._extract_url(flat), LTX23_URL)
        self.assertEqual(space._extract_url(wrapped), DISTILLED_URL)

    def test_missing_url_is_an_error(self):
        with self.assertRaises(space.SpaceError):
            space._extract_url([{"subtitles": None}, 7])


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.provider = plugin.HFSpaceVideoGenProvider()

    def _run(self, fake, **kwargs):
        with unittest.mock.patch.object(space, "requests", fake), \
             unittest.mock.patch.object(plugin, "_token", lambda: "hf_test"):
            return self.provider.generate(PROMPT, **kwargs)

    def test_success_returns_saved_path_and_delivery_note(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        result = self._run(fake)

        self.assertTrue(result["success"])
        self.assertEqual(result["video"], "/tmp/cache/videos/hfspace_test.mp4")
        self.assertEqual(result["model"], "ltx-2-3")
        self.assertEqual((result["width"], result["height"]), (1280, 704))
        self.assertEqual(result["duration"], plugin.DEFAULT_DURATION_S)
        # The gateway does not auto-attach videos, so the result has to say so.
        self.assertIn("note", result)
        self.assertEqual(fake.posts[0]["headers"]["Authorization"], "Bearer hf_test")

    def test_quota_does_not_fall_back_to_another_space(self):
        # A refusal arrives in ~2s because no GPU is ever scheduled; the fake is
        # instant, so it lands inside QUOTA_FAST_FAIL_S.
        fake = _FakeHTTP(_accepted(), _errored())
        result = self._run(fake)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "quota")
        # The allowance is per identity, not per Space: one POST, no retry.
        self.assertEqual(len(fake.posts), 1)

    def test_late_failure_is_not_read_as_quota(self):
        fake = _FakeHTTP(_accepted(), _errored())
        with unittest.mock.patch.object(space, "QUOTA_FAST_FAIL_S", 0.0):
            result = self._run(fake)
        self.assertEqual(result["error_type"], "api_error")

    def test_down_space_falls_back_to_the_next_one(self):
        fake = _FakeHTTP(_down(), _accepted(), _completed(DISTILLED_URL, wrapped=True))
        result = self._run(fake)

        self.assertTrue(result["success"])
        self.assertEqual(result["model"], "ltx-video-distilled")
        self.assertEqual(len(fake.posts), 2)

    def test_all_spaces_down_is_unavailable(self):
        fake = _FakeHTTP(*[_down() for _ in space.SPACES])
        result = self._run(fake)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "unavailable")

    def test_model_argument_picks_the_space(self):
        fake = _FakeHTTP(_accepted(), _completed(DISTILLED_URL, wrapped=True))
        result = self._run(fake, model="ltx-video-distilled")

        self.assertEqual(result["model"], "ltx-video-distilled")
        self.assertIn("lightricks-ltx-video-distilled", fake.posts[0]["url"])

    def test_unknown_model_falls_back_to_the_default(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        self.assertEqual(self._run(fake, model="sora-9")["model"], "ltx-2-3")

    def test_image_input_is_refused_not_ignored(self):
        fake = _FakeHTTP()
        result = self._run(fake, image_url="https://example.com/a.png")

        self.assertEqual(result["error_type"], "invalid_request")
        self.assertEqual(fake.posts, [])

    def test_blank_prompt_is_refused(self):
        with unittest.mock.patch.object(space, "requests", _FakeHTTP()):
            self.assertEqual(
                self.provider.generate("   ")["error_type"], "invalid_request")

    def test_duration_is_clamped_to_the_advertised_range(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        result = self._run(fake, duration=99)
        self.assertEqual(result["duration"], 10)
        self.assertEqual(fake.posts[0]["json"]["data"][2], 10.0)

    def test_portrait_480p_uses_its_own_dimensions(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        result = self._run(fake, aspect_ratio="9:16", resolution="480p")
        self.assertEqual((result["width"], result["height"]), (480, 832))

    def test_unadvertised_aspect_ratio_falls_back_to_the_default(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        result = self._run(fake, aspect_ratio="21:9")
        self.assertEqual(result["aspect_ratio"], "16:9")

    def test_no_token_means_no_authorization_header(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        with unittest.mock.patch.object(space, "requests", fake), \
             unittest.mock.patch.object(plugin, "_token", lambda: ""):
            result = self.provider.generate(PROMPT)
        self.assertTrue(result["success"])
        self.assertNotIn("Authorization", fake.posts[0]["headers"])
        self.assertFalse(result["authenticated"])

    def test_download_failure_is_reported_not_retried(self):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))

        def boom(url, **kw):
            raise OSError("disk full")

        with unittest.mock.patch.object(space, "requests", fake), \
             unittest.mock.patch.object(plugin, "_token", lambda: ""), \
             unittest.mock.patch.object(plugin, "save_url_video", boom):
            result = self.provider.generate(PROMPT)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "api_error")
        # The Space url expires, so there is nothing left to retry against.
        self.assertEqual(len(fake.posts), 1)


class HandOverTest(unittest.TestCase):
    """Where the finished clip lands.

    The KakaoTalk daemon attaches only paths inside its own outbox. Before this
    existed, a real turn generated a clip, referenced it, and the daemon logged
    `첨부 거부: 허용 폴더 밖이다` -- a spent GPU allowance and no video.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "cache" / "videos"
        self.cache.mkdir(parents=True)
        self.outbox = Path(self.tmp.name) / "outbox"

    def _saver(self):
        """A save_url_video stand-in that writes a real file, so move/chmod run."""
        def save(url, **kw):
            dest = self.cache / "hfspace_20260916_000000_deadbeef.mp4"
            dest.write_bytes(b"\x00" * 64)
            dest.chmod(0o600)  # what the real helper writes
            return dest
        return save

    def _generate(self, env):
        fake = _FakeHTTP(_accepted(), _completed(LTX23_URL))
        with unittest.mock.patch.object(space, "requests", fake), \
             unittest.mock.patch.object(plugin, "_token", lambda: ""), \
             unittest.mock.patch.object(plugin, "save_url_video", self._saver()), \
             unittest.mock.patch.dict(os.environ, env, clear=False):
            return plugin.HFSpaceVideoGenProvider().generate(PROMPT)

    def test_outbox_env_moves_the_clip_into_the_fence(self):
        result = self._generate({plugin.OUTBOX_ENV: str(self.outbox)})

        self.assertTrue(result["success"])
        self.assertEqual(Path(result["video"]).parent, self.outbox)
        self.assertTrue(Path(result["video"]).is_file())
        # Nothing left behind in the cache to prune later.
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_handed_over_clip_is_group_and_world_readable(self):
        # save_url_video writes 0600 and the send path is not guaranteed to be
        # this uid; every file already in that outbox is 0644.
        result = self._generate({plugin.OUTBOX_ENV: str(self.outbox)})
        mode = stat.S_IMODE(Path(result["video"]).stat().st_mode)
        self.assertEqual(mode, 0o644)

    def test_without_the_env_the_clip_stays_in_the_cache(self):
        os.environ.pop(plugin.OUTBOX_ENV, None)
        result = self._generate({})

        self.assertEqual(Path(result["video"]).parent, self.cache)

    def test_prune_only_touches_old_clips_with_our_prefix(self):
        self.outbox.mkdir(parents=True)
        old = self.outbox / "hfspace_old.mp4"
        fresh = self.outbox / "hfspace_fresh.mp4"
        other = self.outbox / "comfyui_old.png"
        for path in (old, fresh, other):
            path.write_bytes(b"x")
        stale = time.time() - 8 * 86400
        os.utime(old, (stale, stale))
        os.utime(other, (stale, stale))

        plugin._prune(self.outbox)

        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        # Another plugin's handed-over files are not ours to delete.
        self.assertTrue(other.exists())


class CapabilitiesTest(unittest.TestCase):
    def test_advertised_options_all_have_dimensions(self):
        caps = plugin.HFSpaceVideoGenProvider().capabilities()
        for aspect in caps["aspect_ratios"]:
            for res in caps["resolutions"]:
                self.assertIn((aspect, res), plugin.DIMS)

    def test_no_capability_the_provider_cannot_honor(self):
        caps = plugin.HFSpaceVideoGenProvider().capabilities()
        # LTX-2.3 always emits audio and offers no switch; the default Space
        # takes no negative prompt. Advertising either would add a dead param.
        self.assertFalse(caps["supports_audio"])
        self.assertFalse(caps["supports_negative_prompt"])
        self.assertTrue(caps["supports_seed"])

    def test_every_space_is_listed_as_a_model(self):
        listed = {row["id"] for row in plugin.HFSpaceVideoGenProvider().list_models()}
        self.assertEqual(listed, {item.model_id for item in space.SPACES})


class LiveParamOrderTest(unittest.TestCase):
    """The one network check: has either Space reordered its inputs?

    Skipped by default -- it hits the Hub, though it spends no GPU quota.
    """

    @unittest.skipUnless(os.environ.get("HF_VIDEO_LIVE"), "set HF_VIDEO_LIVE=1 to hit the Hub")
    def test_recorded_order_still_matches_live_info(self):
        import requests as real_requests  # noqa: PLC0415 - the stub is installed above

        if not hasattr(real_requests, "Session"):
            self.skipTest("requests is stubbed in this process")
        with unittest.mock.patch.object(space, "requests", real_requests):
            lines = space.check_param_order()
        for line in lines:
            print(line)
        self.assertFalse([ln for ln in lines if ln.startswith("DRIFT")], lines)


if __name__ == "__main__":
    unittest.main()
