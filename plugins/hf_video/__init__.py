"""Hugging Face ZeroGPU Spaces as the ``video_generate`` backend.

This is the only free hosted video generation left that has a real API: Veo is
paid-tier-only, Cloudflare Workers AI and ModelScope's free inference have no
video models at all, and BigModel's free ``cogvideox-flash`` is retired (its
docs still list it, the API answers ``1211 model does not exist``).

What you get is not a quota in requests but **GPU-seconds a day**: 2 minutes
unauthenticated, 5 with a free account's token, 40 on PRO. A 3-second clip costs
roughly 45 seconds of that. So duration, not request count, is the dial that
empties it -- which is why the default here is 3 seconds and not the Space's own
10-second maximum.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.video_gen_provider import (
    DEFAULT_ASPECT_RATIO, DEFAULT_RESOLUTION, VideoGenProvider, error_response,
    save_url_video, success_response)

# Relative: a user plugin under ~/.hermes/plugins is imported under a
# loader-chosen package name, not `plugins.hf_video` -- that path only resolves
# for bundled plugins.
from . import space

logger = logging.getLogger(__name__)

TOKEN_ENV = "HF_TOKEN"

# Three seconds. The Space allows 1-10 (measured off its own slider), but the
# allowance is GPU-seconds, so a 10-second default would turn a day's budget into
# one clip. Callers who want longer pass `duration`.
DEFAULT_DURATION_S = 3

# Only the combinations we actually advertise in capabilities(), so there is no
# rounding arithmetic to get wrong. Every value is a multiple of 32 (what LTX
# wants), and 1280x704 is the pair that was measured end to end.
DIMS: Dict[tuple, tuple] = {
    ("16:9", "720p"): (1280, 704),
    ("9:16", "720p"): (704, 1280),
    ("1:1", "720p"): (960, 960),
    ("16:9", "480p"): (832, 480),
    ("9:16", "480p"): (480, 832),
    ("1:1", "480p"): (640, 640),
}
ASPECTS = ["16:9", "9:16", "1:1"]
RESOLUTIONS = ["480p", "720p"]

# The core does not attach videos by itself: `video_generate` is absent from the
# gateway's auto-append allowlist, and the JSON path extraction there is
# hardcoded to `image_generate`. So the model has to reference the path, and this
# is the only channel we have to tell it so.
DELIVERY_NOTE = (
    "영상 파일은 위 video 경로에 있다. 사용자에게 보이려면 그 절대경로를 현재 플랫폼의 파일 전달 "
    "방식으로 첨부해라 (카카오톡이면 `[[file: 경로]]` 한 줄). 경로만 글로 적으면 전달되지 않는다.")

# Where a finished clip is handed over.
#
# The KakaoTalk daemon attaches only paths inside its own fenced outbox --
# `resolve_attachment()` rejects everything else and logs `첨부 거부`. Measured: a
# clip left in the hermes cache was generated, referenced by the model, and then
# silently dropped, costing a turn and a slice of the daily GPU allowance for
# nothing. The daemon injects this variable on every turn (it is named for the
# image plugin that needed it first), so its presence is also how we learn the
# caller is KakaoTalk.
OUTBOX_ENV = "COMFYUI_OUTBOX_DIR"

# No size guard here on purpose. KakaoTalk drops an oversized attachment without a
# word, but 10 seconds -- the advertised maximum -- is well under 5 MB at these
# resolutions, so the guard would be a branch that never fires. Add one if a
# higher-resolution Space is ever put in the ring.


def _token() -> str:
    """Config-aware ``HF_TOKEN`` lookup.

    A bare ``os.getenv`` misses keys that arrive through the config layer, which
    is how gateway sessions and delegate children get theirs. Falls back to the
    environment when the config module is not importable.
    """
    val = None
    try:
        from hermes_cli.config import get_env_value

        val = get_env_value(TOKEN_ENV)
    except Exception:  # noqa: BLE001 - config layer is optional here
        val = None
    if val is None:
        val = os.getenv(TOKEN_ENV, "")
    return (val or "").strip()


def _prune(directory: Path, days: int = 7) -> None:
    """Drop handed-over clips older than ``days``; nothing ever reads them back."""
    cutoff = time.time() - days * 86400
    try:
        for path in directory.glob("hfspace_*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


def _hand_over(saved: Path) -> Path:
    """Move the clip into the caller's fenced outbox when there is one."""
    outbox = os.environ.get(OUTBOX_ENV)
    if not outbox:
        return saved
    dest_dir = Path(outbox).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / saved.name
    shutil.move(str(saved), str(dest))
    # save_url_video writes 0600. The send path is not guaranteed to run as this
    # uid, and every file already in that outbox is 0644.
    dest.chmod(0o644)
    _prune(dest_dir)
    return dest


class HFSpaceVideoGenProvider(VideoGenProvider):
    """Text-to-video on somebody else's free GPU."""

    @property
    def name(self) -> str:
        return "hfspace"

    @property
    def display_name(self) -> str:
        return "HF ZeroGPU (free)"

    def is_available(self) -> bool:
        # Must stay local: the picker calls this on every paint. There is also
        # nothing to check -- the Spaces work without a token, and a Space that
        # is down surfaces as a one-line error from generate() instead, which is
        # more useful than the tool quietly disappearing.
        return True

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text"],
            "aspect_ratios": list(ASPECTS),
            "resolutions": list(RESOLUTIONS),
            "min_duration": 1,
            "max_duration": 10,
            # LTX-2.3 always returns an audio track and offers no switch, so there
            # is no parameter to advertise -- a boolean the provider cannot honor
            # is worse than none. It is called out in list_models() instead.
            "supports_audio": False,
            # Only the fallback Space takes one; advertising it would be a lie for
            # the default model.
            "supports_negative_prompt": False,
            "supports_seed": True,
            "supports_upscale": False,
            "max_reference_images": 0,
        }

    def list_models(self) -> List[Dict[str, Any]]:
        return [{
            "id": item.model_id,
            "display": item.display,
            "speed": "Slow" if item.model_id == "ltx-2-3" else "Fast",
            "strengths": item.strengths,
            "price": "free",
        } for item in space.SPACES]

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "free",
            "tag": "HF ZeroGPU Spaces. HF_TOKEN 없이도 돌지만 하루 2분 -> 5분으로 늘어난다",
            "env_vars": [TOKEN_ENV],
        }

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        duration: Optional[int] = None,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        resolution: str = DEFAULT_RESOLUTION,
        negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None,
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        chosen = space.by_model_id(model)
        aspect = aspect_ratio if aspect_ratio in ASPECTS else DEFAULT_ASPECT_RATIO
        res = resolution if resolution in RESOLUTIONS else DEFAULT_RESOLUTION

        def fail(error: str, error_type: str, model_id: str = "") -> Dict[str, Any]:
            return error_response(
                error=error, error_type=error_type, provider=self.name,
                model=model_id or chosen.model_id, prompt=prompt, aspect_ratio=aspect)

        if not prompt or not prompt.strip():
            return fail("prompt is required", "invalid_request")
        if image_url or reference_image_urls:
            return fail("이 백엔드는 텍스트→영상만 한다 (이미지·레퍼런스 미지원)", "invalid_request")

        width, height = DIMS[(aspect, res)]
        secs = max(1, min(10, int(duration or DEFAULT_DURATION_S)))
        token = _token()

        # Try the requested Space first, then the others -- but only when the
        # failure was the Space itself. A quota refusal is per identity, so
        # rolling onto another Space just burns wall-clock for the same error.
        ring = (chosen,) + tuple(item for item in space.SPACES if item != chosen)
        last_down: Optional[Exception] = None
        for item in ring:
            try:
                url = space.call(
                    item, prompt=prompt.strip(), duration=secs, width=width, height=height,
                    seed=seed, negative_prompt=negative_prompt, token=token)
            except space.QuotaExhausted as exc:
                return fail(str(exc), "quota", item.model_id)
            except space.SpaceDown as exc:
                logger.debug("hf_video: %s is down, trying next", item.subdomain, exc_info=True)
                last_down = exc
                continue
            except space.SpaceError as exc:
                return fail(str(exc), "api_error", item.model_id)
            except Exception as exc:  # noqa: BLE001 - one uniform shape for the dispatcher
                logger.debug("hf_video generation failed", exc_info=True)
                return fail(f"HF Space 호출 실패: {exc}", "api_error", item.model_id)

            try:
                # The Space's url expires, so there is nothing to fall back to
                # once the download fails -- this is a hard error, not a retry.
                saved = _hand_over(save_url_video(url, prefix="hfspace"))
            except Exception as exc:  # noqa: BLE001
                logger.debug("hf_video download failed", exc_info=True)
                return fail(f"영상은 만들어졌는데 받아오지 못했다: {exc}", "api_error", item.model_id)

            return success_response(
                video=str(saved), model=item.model_id, prompt=prompt, aspect_ratio=aspect,
                duration=secs, provider=self.name,
                extra={"width": width, "height": height, "resolution": res,
                       "space": item.subdomain, "authenticated": bool(token),
                       "note": DELIVERY_NOTE})

        return fail(f"쓸 수 있는 Space 가 없다: {last_down}", "unavailable")


def register(ctx) -> None:
    """Plugin entry point - wire the provider into the video_gen registry."""
    ctx.register_video_gen_provider(HFSpaceVideoGenProvider())
