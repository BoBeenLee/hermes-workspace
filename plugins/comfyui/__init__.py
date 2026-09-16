"""ComfyUI as the ``image_generate`` backend, for a ComfyUI on the same host.

Model is Krea 2 Turbo and is not selectable. What costs time on this box is not
the eight sampling steps, it is evicting and reloading an 18 GB model stack --
so offering a second model would buy a style at the price of turning a 15 second
render into a 300 second one. Style comes from a LoRA on the same stack instead.

The same ComfyUI also makes songs, but music has no provider registry to plug
into, so it is two ordinary tools in ``music.py`` sharing this module's client,
gate and deliverer.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO, ImageGenProvider, error_response, resolve_aspect_ratio, success_response)

# Relative: a user plugin under ~/.hermes/plugins is imported under a loader-chosen
# package name, not `plugins.comfyui` -- that path only resolves for bundled plugins.
from . import comfy, music

logger = logging.getLogger(__name__)

MODEL_ID = "krea2-turbo"
WORKFLOW = Path(__file__).resolve().parent / "workflows" / "krea2-turbo-t2i.json"

# Node ids are the official Krea-2 Turbo template's, kept as-is so the graph can
# be diffed against it. Only these three inputs ever change per request.
PROMPT_NODE, LATENT_NODE, SAMPLER_NODE, SAVE_NODE = "6", "5", "3", "9"
LORA_NODE = "15"

# A fixed ~0.52 MP budget rather than a fixed short edge. hermes defines
# portrait/landscape as 16:9, so anchoring 720 to the short edge would make
# portrait 720x1280 -- 0.92 MP, which is no faster than the template's square
# 1024 and defeats the point. Equal budget means all three cost the same.
# Every value is a multiple of 8 (EmptyLatentImage's step).
SIZES = {
    "square": (720, 720),
    "portrait": (544, 960),
    "landscape": (960, 544),
}

# Local style LoRAs. Only one is downloaded; the other eight official Krea-2
# styles are not on this box. The trigger phrase is prepended to the prompt
# because that is what the LoRA was trained on -- without it you pay the compute
# and get little of the style. Keys are matched against the request text, which
# is the only channel available: image_generate's schema has no style argument
# and providers must ignore unknown kwargs.
LORAS = (
    (("수묵", "먹그림", "ink wash", "sumi"),
     "krea2_darkbrush.safetensors", 1.0, "monochrome ink wash style"),
)

POLL_TIMEOUT_S = 380.0  # Inside the 420s tool deadline, so we fail with a sentence.

# How long the async path holds the turn open before handing the job to a deliverer.
#
# Zero, and that is not a placeholder. The intuition -- "wait a little so quick
# renders finish in one turn" -- is wrong here, and measurably so. Same prompt,
# same room, KakaoTalk's 180s budget:
#
#   wait for the render (it took 9s)   -> 196s total, over budget, turn killed
#   hand it off immediately            ->  84s total
#   no tool at all, just a refusal     ->  89s
#
# The render was never the cost. What costs is what the model does *after* the
# tool returns: an image in hand means composing a real answer with the path and
# the expiry caveat, ~110s of round-trips on this host's model. A "queued" result
# means one short sentence. Waiting buys a marginally nicer turn and pays for it
# with the whole budget.
#
# Raise it via COMFYUI_ASYNC_WINDOW_S on a host whose model is fast enough that
# finishing in one turn is affordable.
ASYNC_WINDOW_S = 0.0
DELIVER_TIMEOUT_S = 900.0


def _async_window() -> float:
    """``COMFYUI_ASYNC_WINDOW_S`` overrides the window. The right value depends on
    what the caller's LLM leaves over, not on the render, so it is tunable per host."""
    try:
        return float(os.environ.get("COMFYUI_ASYNC_WINDOW_S") or ASYNC_WINDOW_S)
    except ValueError:
        return ASYNC_WINDOW_S



def _style_for(prompt: str) -> Optional[tuple]:
    """(lora_name, strength, trigger) when the request asks for a style we have."""
    lowered = prompt.lower()
    for keys, lora_name, strength, trigger in LORAS:
        if any(key in lowered for key in keys):
            return lora_name, strength, trigger
    return None


class ComfyUIImageGenProvider(ImageGenProvider):
    """Krea 2 Turbo on a local ComfyUI."""

    @property
    def name(self) -> str:
        return "comfyui"

    @property
    def display_name(self) -> str:
        return "ComfyUI (local)"

    def is_available(self) -> bool:
        # Must stay local: the picker calls this on every paint, so probing
        # ComfyUI over HTTP here would put a network round-trip in the UI. A
        # server that is down surfaces as a one-line error from generate()
        # instead, which is more useful than the tool quietly disappearing.
        return WORKFLOW.is_file()

    def capabilities(self) -> Dict[str, Any]:
        return {"modalities": ["text"], "max_reference_images": 0}

    def list_models(self) -> List[Dict[str, Any]]:
        return [{
            "id": MODEL_ID,
            "display": "Krea 2 Turbo (local)",
            "speed": "Fast",
            "strengths": "8-step local text-to-image; no API cost",
            "price": "free",
        }]

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": self.display_name, "badge": "local",
            "tag": f"Krea 2 Turbo on {comfy.ComfyUI().base_url}; no API key",
            "env_vars": [],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        aspect = resolve_aspect_ratio(aspect_ratio)

        def fail(error: str, error_type: str) -> Dict[str, Any]:
            return error_response(
                error=error, error_type=error_type, provider=self.name,
                model=MODEL_ID, prompt=prompt, aspect_ratio=aspect)

        if not prompt or not prompt.strip():
            return fail("prompt is required", "invalid_request")
        if image_url or reference_image_urls:
            return fail("이 백엔드는 텍스트→이미지만 한다 (편집·레퍼런스 미지원)", "invalid_request")

        client = comfy.ComfyUI()
        refusal = client.gate()
        if refusal:
            return fail(refusal, "unavailable")

        width, height = SIZES.get(aspect, SIZES["square"])
        text = prompt.strip()
        patches: Dict[str, Dict[str, Any]] = {
            LATENT_NODE: {"width": width, "height": height},
            SAMPLER_NODE: {"seed": comfy.random_seed()},
        }
        style = _style_for(text)
        graph = comfy.load_workflow(WORKFLOW)
        if style:
            lora_name, strength, trigger = style
            text = f"{trigger}, {text}"
            graph[LORA_NODE] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"model": graph[SAMPLER_NODE]["inputs"]["model"],
                           "lora_name": lora_name, "strength_model": strength},
            }
            patches[SAMPLER_NODE]["model"] = [LORA_NODE, 0]
        patches[PROMPT_NODE] = {"text": text}

        target = comfy.async_target()
        try:
            graph = comfy.patch(graph, patches)
            prompt_id = client.submit(graph)
            window = _async_window() if target else POLL_TIMEOUT_S
            entry = client.poll(prompt_id, timeout=window)
            if entry is None:
                if target and comfy.spawn_deliverer(
                        prompt_id, target, client, node=SAVE_NODE,
                        caption=comfy.caption_for(prompt), timeout=DELIVER_TIMEOUT_S):
                    # Not an error: the job is running and a child owns delivering
                    # it. The turn ends here so the other rooms are not held.
                    return {
                        "success": True, "image": None, "status": "queued",
                        "prompt_id": prompt_id, "provider": self.name, "model": MODEL_ID,
                        "prompt": prompt, "aspect_ratio": aspect,
                        "note": ("아직 그리는 중이다. 사진은 다 되면 따로 이 방으로 간다. "
                                 "지금은 '만들고 있어' 한 줄만 답하고 턴을 끝내라. "
                                 "다시 부르지 마라 - 중복으로 두 장이 나간다."),
                    }
                return fail(
                    f"{int(window)}초 안에 안 끝났다 (prompt_id={prompt_id}). "
                    "ComfyUI 에서는 계속 돌고 있다", "timeout")
            rendered = client.output_paths(entry, SAVE_NODE)[0]
            if not rendered.is_file():
                return fail(f"ComfyUI 는 끝났다는데 파일이 없다: {rendered}", "empty_response")
            handed = comfy.hand_over(rendered, comfy.destination_dir("images"), comfy.max_bytes())
            comfy.prune(handed.parent)
        except comfy.ComfyError as exc:
            return fail(str(exc), "api_error")
        except Exception as exc:  # noqa: BLE001 - one uniform shape for the dispatcher
            logger.debug("comfyui image generation failed", exc_info=True)
            return fail(f"ComfyUI 호출 실패: {exc}", "api_error")

        return success_response(
            image=str(handed), model=MODEL_ID, prompt=prompt, aspect_ratio=aspect,
            provider=self.name,
            extra={"width": width, "height": height, "prompt_id": prompt_id,
                   "style": (style[2] if style else None)})


def _json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def register(ctx) -> None:
    """Plugin entry point: the image_gen provider, plus music as two plain tools.

    Music is not a provider because hermes has no music registry. `web` is the
    toolset rather than a new name of our own: it is already in the KakaoTalk
    daemon's fixed --toolsets string, so the tools ride every turn without the
    daemon being touched.
    """
    ctx.register_image_gen_provider(ComfyUIImageGenProvider())

    ctx.register_tool(
        name="music_generate", toolset="web", schema=music.GENERATE_SCHEMA,
        handler=lambda args, **kw: _json(music.generate(args)),
        check_fn=music.available, emoji="🎵")
    ctx.register_tool(
        name="music_status", toolset="web", schema=music.STATUS_SCHEMA,
        handler=lambda args, **kw: _json(music.status(args)),
        check_fn=music.available, emoji="🎧")
