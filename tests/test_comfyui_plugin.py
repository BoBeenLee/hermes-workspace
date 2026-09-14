"""Tests for the local-ComfyUI image_gen provider.

``agent.*`` lives in the hermes-agent install, not in this repo, so the few
symbols the plugin imports are stubbed here with the real signatures. That keeps
the whole provider importable and lets generate() be exercised end to end
against a fake ComfyUI rather than only its helpers.
"""

import json
import sys
import types
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

VALID_ASPECT_RATIOS = ("landscape", "square", "portrait")


def _install_agent_stubs():
    agent = sys.modules.setdefault("agent", types.ModuleType("agent"))
    agent.__path__ = []  # noqa: SLF001 - make it a package so submodules import

    provider = types.ModuleType("agent.image_gen_provider")
    provider.DEFAULT_ASPECT_RATIO = "landscape"
    provider.VALID_ASPECT_RATIOS = VALID_ASPECT_RATIOS

    class ImageGenProvider:
        def capabilities(self):
            return {"modalities": ["text"], "max_reference_images": 0}

    def resolve_aspect_ratio(value):
        v = value.strip().lower() if isinstance(value, str) else ""
        return v if v in VALID_ASPECT_RATIOS else "landscape"

    def success_response(*, image, model, prompt, aspect_ratio, provider, modality="text", extra=None):
        payload = {"success": True, "image": image, "model": model, "prompt": prompt,
                   "aspect_ratio": aspect_ratio, "modality": modality, "provider": provider}
        for key, value in (extra or {}).items():
            payload.setdefault(key, value)
        return payload

    def error_response(*, error, error_type="provider_error", provider="", model="",
                       prompt="", aspect_ratio="landscape"):
        return {"success": False, "image": None, "error": error, "error_type": error_type,
                "model": model, "prompt": prompt, "aspect_ratio": aspect_ratio, "provider": provider}

    provider.ImageGenProvider = ImageGenProvider
    provider.resolve_aspect_ratio = resolve_aspect_ratio
    provider.success_response = success_response
    provider.error_response = error_response
    sys.modules["agent.image_gen_provider"] = provider

    media = types.ModuleType("agent.provider_media")
    media.cache_dir = lambda kind: Path("/tmp/does-not-exist")  # overridden per test
    sys.modules["agent.provider_media"] = media
    agent.provider_media = media
    return media


def _install_requests_stub():
    """The plugin needs ``requests`` at import time; every test injects its own
    fake in its place, so a bare module is enough and the suite stays runnable
    on a checkout with nothing installed."""
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.ModuleType("requests")


_MEDIA = _install_agent_stubs()
_install_requests_stub()
sys.path.insert(0, str(REPO))

from plugins.comfyui import comfy  # noqa: E402
import plugins.comfyui as plugin  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text or json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class FakeComfy:
    """A ComfyUI that accepts one graph and finishes immediately."""

    def __init__(self, queue=(0, 0), history=None):
        self.queue_running, self.queue_pending = queue
        self.submitted = None
        self.history = history

    def get(self, url, **kwargs):
        if url.endswith("/queue"):
            return FakeResponse({"queue_running": [0] * self.queue_running,
                                 "queue_pending": [0] * self.queue_pending})
        if "/history/" in url:
            return FakeResponse({"pid-1": self.history} if self.history else {})
        if url.endswith("/system_stats"):
            return FakeResponse({"system": {}})
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, **kwargs):
        assert url.endswith("/prompt"), url
        self.submitted = kwargs["json"]["prompt"]
        return FakeResponse({"prompt_id": "pid-1"})


def done_entry(filename="img_00001_.png", subfolder="hermes"):
    return {"status": {"status_str": "success", "completed": True},
            "outputs": {"9": {"images": [{"filename": filename, "subfolder": subfolder,
                                          "type": "output"}]}}}


class GateTest(unittest.TestCase):
    def test_busy_queue_refuses(self):
        fake = FakeComfy(queue=(1, 2))
        with unittest.mock.patch.object(comfy, "requests", fake):
            reason = comfy.ComfyUI().gate()
        self.assertIsNotNone(reason)
        self.assertIn("3", reason)

    def test_low_memory_refuses(self):
        fake = FakeComfy()
        with unittest.mock.patch.object(comfy, "requests", fake), \
             unittest.mock.patch.object(comfy, "mem_available_gb", return_value=8.0):
            reason = comfy.ComfyUI().gate(min_free_gb=24.0)
        self.assertIsNotNone(reason)
        self.assertIn("8GB", reason)

    def test_clear_box_passes(self):
        fake = FakeComfy()
        with unittest.mock.patch.object(comfy, "requests", fake), \
             unittest.mock.patch.object(comfy, "mem_available_gb", return_value=90.0):
            self.assertIsNone(comfy.ComfyUI().gate())

    def test_unreachable_refuses_rather_than_raises(self):
        broken = unittest.mock.Mock()
        broken.get.side_effect = OSError("connection refused")
        with unittest.mock.patch.object(comfy, "requests", broken):
            reason = comfy.ComfyUI().gate()
        self.assertIsNotNone(reason)

    def test_missing_meminfo_does_not_block(self):
        """Off Linux there is no floor to check; that must not become a refusal."""
        fake = FakeComfy()
        with unittest.mock.patch.object(comfy, "requests", fake), \
             unittest.mock.patch.object(comfy, "mem_available_gb", return_value=None):
            self.assertIsNone(comfy.ComfyUI().gate())


class WorkflowTest(unittest.TestCase):
    def test_shipped_graph_has_the_nodes_the_provider_patches(self):
        graph = comfy.load_workflow(plugin.WORKFLOW)
        for node in (plugin.PROMPT_NODE, plugin.LATENT_NODE, plugin.SAMPLER_NODE, plugin.SAVE_NODE):
            self.assertIn(node, graph)
        self.assertEqual(graph[plugin.SAMPLER_NODE]["inputs"]["steps"], 8)

    def test_patch_rejects_an_unknown_node(self):
        with self.assertRaises(comfy.ComfyError):
            comfy.patch({"1": {"inputs": {}}}, {"99": {"text": "x"}})

    def test_patch_does_not_mutate_the_template(self):
        graph = {"1": {"inputs": {"text": "before"}}}
        comfy.patch(graph, {"1": {"text": "after"}})
        self.assertEqual(graph["1"]["inputs"]["text"], "before")

    def test_wrapped_graph_is_unwrapped(self):
        with unittest.mock.patch("builtins.open",
                                 unittest.mock.mock_open(read_data='{"prompt": {"1": {}}}')):
            self.assertEqual(comfy.load_workflow(Path("x.json")), {"1": {}})

    def test_output_paths_compose_against_the_local_output_root(self):
        client = comfy.ComfyUI(output_root="/out")
        paths = client.output_paths(done_entry(), "9")
        self.assertEqual(paths, [Path("/out/hermes/img_00001_.png")])

    def test_output_paths_raise_when_the_node_produced_nothing(self):
        client = comfy.ComfyUI(output_root="/out")
        with self.assertRaises(comfy.ComfyError):
            client.output_paths({"outputs": {"9": {}}}, "9")


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = unittest.mock.patch.dict("os.environ", {}, clear=False)
        self.tmp.start()
        self.addCleanup(self.tmp.stop)
        import tempfile

        self.workdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.workdir, ignore_errors=True))
        self.rendered = self.workdir / "out" / "hermes" / "img_00001_.png"
        self.rendered.parent.mkdir(parents=True)
        self.rendered.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 128)
        self.dest = self.workdir / "dest"
        _MEDIA.cache_dir = lambda kind: self.dest

    def _run(self, prompt="a cat", aspect="square", fake=None, timeout=None):
        fake = fake or FakeComfy(history=done_entry())
        provider = plugin.ComfyUIImageGenProvider()
        # The real 380s budget would make the timeout case take 380s to assert.
        with unittest.mock.patch.object(comfy, "requests", fake), \
             unittest.mock.patch.object(comfy, "mem_available_gb", return_value=90.0), \
             unittest.mock.patch.object(plugin, "POLL_TIMEOUT_S", timeout or 0.05), \
             unittest.mock.patch.object(comfy.time, "sleep", lambda _s: None), \
             unittest.mock.patch.dict(
                 "os.environ", {"COMFYUI_OUTPUT_ROOT": str(self.workdir / "out")}):
            return provider.generate(prompt, aspect), fake

    def test_happy_path_patches_prompt_size_and_seed(self):
        result, fake = self._run("a cat on a roof", "portrait")
        self.assertTrue(result["success"], result)
        graph = fake.submitted
        self.assertEqual(graph[plugin.PROMPT_NODE]["inputs"]["text"], "a cat on a roof")
        self.assertEqual((graph[plugin.LATENT_NODE]["inputs"]["width"],
                          graph[plugin.LATENT_NODE]["inputs"]["height"]),
                         plugin.SIZES["portrait"])
        self.assertNotEqual(graph[plugin.SAMPLER_NODE]["inputs"]["seed"], 0)

    def test_result_file_is_copied_out_of_the_comfyui_tree(self):
        result, _ = self._run()
        handed = Path(result["image"])
        self.assertTrue(handed.is_file())
        self.assertEqual(handed.parent, self.dest)
        self.assertNotEqual(handed, self.rendered)

    def test_outbox_env_overrides_the_cache_destination(self):
        outbox = self.workdir / "outbox"
        with unittest.mock.patch.dict("os.environ", {"COMFYUI_OUTBOX_DIR": str(outbox)}):
            result, _ = self._run()
        self.assertEqual(Path(result["image"]).parent, outbox)

    def test_every_aspect_costs_the_same_pixels(self):
        """The point of the size table: portrait must not be 1.8x the work of square."""
        budgets = {w * h for w, h in plugin.SIZES.values()}
        self.assertLess(max(budgets) / min(budgets), 1.05)
        for width, height in plugin.SIZES.values():
            self.assertEqual((width % 8, height % 8), (0, 0))

    def test_style_keyword_adds_the_lora_and_its_trigger(self):
        result, fake = self._run("수묵 느낌으로 산을 그려줘")
        self.assertTrue(result["success"], result)
        graph = fake.submitted
        self.assertIn(plugin.LORA_NODE, graph)
        self.assertEqual(graph[plugin.SAMPLER_NODE]["inputs"]["model"], [plugin.LORA_NODE, 0])
        self.assertEqual(graph[plugin.LORA_NODE]["inputs"]["model"], ["10", 0])
        self.assertTrue(graph[plugin.PROMPT_NODE]["inputs"]["text"]
                        .startswith("monochrome ink wash style,"))

    def test_plain_prompt_leaves_the_lora_out(self):
        _, fake = self._run("a cat")
        self.assertNotIn(plugin.LORA_NODE, fake.submitted)
        self.assertEqual(fake.submitted[plugin.SAMPLER_NODE]["inputs"]["model"], ["10", 0])

    def test_busy_queue_returns_an_error_not_a_render(self):
        result, fake = self._run(fake=FakeComfy(queue=(1, 0), history=done_entry()))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "unavailable")
        self.assertIsNone(fake.submitted)

    def test_edit_request_is_refused_rather_than_silently_dropped(self):
        provider = plugin.ComfyUIImageGenProvider()
        result = provider.generate("a cat", "square", image_url="http://x/y.png")
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "invalid_request")

    def test_timeout_reports_the_prompt_id_so_the_job_is_not_lost(self):
        result, _ = self._run(fake=FakeComfy(history=None))
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "timeout")
        self.assertIn("pid-1", result["error"])

    def test_node_error_surfaces_the_node_type(self):
        failed = {"status": {"status_str": "error", "completed": False,
                             "messages": [["execution_error",
                                           {"node_type": "KSampler",
                                            "exception_message": "latent has 4 channels"}]]},
                  "outputs": {}}
        result, _ = self._run(fake=FakeComfy(history=failed))
        self.assertFalse(result["success"])
        self.assertIn("KSampler", result["error"])


class AsyncTest(unittest.TestCase):
    """The KakaoTalk path: hold the turn briefly, then hand the job to a child."""

    def setUp(self):
        import tempfile

        self.workdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.workdir, ignore_errors=True))
        self.outbox = self.workdir / "outbox"
        rendered = self.workdir / "out" / "hermes" / "img_00001_.png"
        rendered.parent.mkdir(parents=True)
        rendered.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        self.env = {"COMFYUI_OUTBOX_DIR": str(self.outbox),
                    "COMFYUI_CHAT_ID": "12345",
                    "COMFYUI_SEND_BIN": "/x/kakao_ai_chat.py",
                    "COMFYUI_OUTPUT_ROOT": str(self.workdir / "out")}

    def _run(self, fake, env=None, spawn_ok=True):
        provider = plugin.ComfyUIImageGenProvider()
        spawned = []

        def fake_popen(argv, **kwargs):
            spawned.append((argv, kwargs))
            if not spawn_ok:
                raise OSError("no fork for you")
            return unittest.mock.Mock()

        with unittest.mock.patch.object(comfy, "requests", fake), \
             unittest.mock.patch.object(comfy, "mem_available_gb", return_value=90.0), \
             unittest.mock.patch.object(comfy.time, "sleep", lambda _s: None), \
             unittest.mock.patch.object(plugin, "ASYNC_WINDOW_S", 0.05), \
             unittest.mock.patch.object(plugin.subprocess, "Popen", fake_popen), \
             unittest.mock.patch.dict("os.environ", env if env is not None else self.env):
            return provider.generate("a cat", "square"), spawned

    def test_unfinished_job_is_handed_to_a_detached_child(self):
        result, spawned = self._run(FakeComfy(history=None))
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["prompt_id"], "pid-1")
        self.assertIsNone(result["image"])
        self.assertEqual(len(spawned), 1)
        argv, kwargs = spawned[0]
        self.assertIn("--prompt-id", argv)
        self.assertEqual(argv[argv.index("--chat-id") + 1], "12345")
        self.assertEqual(argv[argv.index("--outbox") + 1], str(self.outbox))
        # Must outlive the hermes turn that started it.
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["stdout"], plugin.subprocess.DEVNULL)

    def test_a_fast_job_still_answers_in_the_same_turn(self):
        result, spawned = self._run(FakeComfy(history=done_entry()))
        self.assertTrue(result["success"])
        self.assertNotIn("status", result)
        self.assertEqual(Path(result["image"]).parent, self.outbox)
        self.assertEqual(spawned, [])

    def test_gateway_has_no_async_env_and_waits(self):
        """Without the daemon's three variables this must stay synchronous."""
        result, spawned = self._run(FakeComfy(history=done_entry()),
                                    env={"COMFYUI_OUTPUT_ROOT": self.env["COMFYUI_OUTPUT_ROOT"]})
        self.assertTrue(result["success"])
        self.assertEqual(spawned, [])

    def test_a_partial_env_does_not_half_enable_the_async_path(self):
        """All three or none: a child with no send target would render into silence."""
        self.assertIsNotNone(_target_with(self.env))
        for missing in ("COMFYUI_SEND_BIN", "COMFYUI_CHAT_ID", "COMFYUI_OUTBOX_DIR"):
            env = {k: v for k, v in self.env.items() if k != missing}
            self.assertIsNone(_target_with(env), missing)

    def test_a_nonnumeric_chat_id_is_rejected_not_crashed_on(self):
        self.assertIsNone(_target_with(dict(self.env, COMFYUI_CHAT_ID="not-a-number")))

    def test_spawn_failure_degrades_to_a_plain_timeout_error(self):
        """A child that never started must not leave the room expecting a photo."""
        result, _ = self._run(FakeComfy(history=None), spawn_ok=False)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "timeout")


def _target_with(env):
    with unittest.mock.patch.dict("os.environ", env, clear=True):
        return plugin._async_target()


class HandOverTest(unittest.TestCase):
    def test_oversized_png_is_reencoded_as_jpeg(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        import tempfile

        workdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(workdir, ignore_errors=True))
        source = workdir / "big.png"
        Image.new("RGB", (64, 64), (200, 30, 30)).save(source)
        _MEDIA.cache_dir = lambda kind: workdir / "dest"
        handed = comfy.hand_over(source, workdir / "dest", max_bytes=1)
        self.assertEqual(handed.suffix, ".jpg")
        self.assertTrue(handed.is_file())


if __name__ == "__main__":
    unittest.main()
