"""Gradio REST client for the Hugging Face Space video demos (ZeroGPU free tier).

Every Gradio Space on the Hub is also an API endpoint: POST the positional
argument array, then read the result off a server-sent-event stream. That is the
whole protocol, so ``gradio_client`` is neither needed nor installed here.

The argument array is positional and unnamed, which means **the order is the
contract**. ``https://<sub>.hf.space/gradio_api/info`` is the source of truth for
it; each Space below records the order it was written against, and
``check_param_order()`` re-checks that against the live Space without spending
any GPU quota. Importing this package needs ``agent.*`` and ``requests``, so
run it where both exist -- on the hermes host:

    cd ~/.hermes/hermes-agent && PYTHONPATH=~/.hermes/plugins venv/bin/python -c \
        'from hf_video import space
         for line in space.check_param_order(): print(line)'
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import requests

# How long a failure has to arrive within to be read as "quota", not "broken".
#
# ZeroGPU does not say why it refused. An exhausted daily allowance and a crashed
# Space both come back as `event: error` with `data: null` and no message. What
# separates them is the clock: a real 3-second render on these Spaces takes ~45s
# wall (measured from the DGX), while a quota refusal lands in ~2s because no GPU
# is ever scheduled. Anything under this bound is the refusal.
QUOTA_FAST_FAIL_S = 8.0

# The GET holds the SSE stream open for the whole render, and a busy queue adds
# to it. Kept inside video_generate's own deadline so we fail with a sentence.
POLL_TIMEOUT_S = 300.0

_POST_TIMEOUT_S = 30.0

# Only the distilled Space takes one, and it was trained expecting this phrasing.
_DEFAULT_NEGATIVE = "worst quality, inconsistent motion, blurry, jittery, distorted"


class SpaceError(RuntimeError):
    """The Space answered, and the answer was not a video."""


class QuotaExhausted(SpaceError):
    """The account's -- or, unauthenticated, the IP's -- daily ZeroGPU allowance is gone.

    Not retryable on another Space: the allowance is per identity, not per Space.
    """


class SpaceDown(SpaceError):
    """This Space is unreachable or erroring. Another Space may still work."""


class Space(NamedTuple):
    model_id: str
    subdomain: str
    endpoint: str
    params: Tuple[str, ...]  # recorded /gradio_api/info order; see module docstring
    build: Callable[..., List[Any]]
    display: str
    strengths: str


def _ltx23_args(
    *, prompt: str, duration: float, width: int, height: int, seed: Optional[int],
    negative_prompt: Optional[str],
) -> List[Any]:
    # enhance_prompt=False on purpose: it runs a prompt-rewriting model inside the
    # Space, which buys some polish and charges it to the same GPU allowance.
    return [None, prompt, float(duration), False, int(seed or 0), seed is None, height, width]


def _distilled_args(
    *, prompt: str, duration: float, width: int, height: int, seed: Optional[int],
    negative_prompt: Optional[str],
) -> List[Any]:
    return [
        prompt, negative_prompt or _DEFAULT_NEGATIVE, None, None, height, width,
        "text-to-video", float(duration), 9, int(seed or 0), seed is None, 1, True,
    ]


# Order is also the fallback order. The first entry is the default model.
SPACES: Tuple[Space, ...] = (
    Space(
        model_id="ltx-2-3",
        subdomain="lightricks-ltx-2-3",
        endpoint="generate_video",
        params=("input_image", "prompt", "duration", "enhance_prompt", "seed",
                "randomize_seed", "height", "width"),
        build=_ltx23_args,
        display="LTX-2.3 (HF ZeroGPU)",
        strengths="1280x704 24fps, 오디오까지 같이 생성. 3초에 약 45초",
    ),
    Space(
        model_id="ltx-video-distilled",
        subdomain="lightricks-ltx-video-distilled",
        endpoint="text_to_video",
        params=("prompt", "negative_prompt", "input_image_filepath", "input_video_filepath",
                "height_ui", "width_ui", "mode", "duration_ui", "ui_frames_to_use", "seed_ui",
                "randomize_seed", "ui_guidance_scale", "improve_texture_flag"),
        build=_distilled_args,
        display="LTX-Video distilled (HF ZeroGPU)",
        strengths="더 빠르고 GPU 쿼터를 덜 먹는다. 오디오 없음",
    ),
)


def by_model_id(model_id: Optional[str]) -> Space:
    """The requested Space, or the default when the id is unset or unknown."""
    for space in SPACES:
        if model_id and space.model_id == model_id:
            return space
    return SPACES[0]


def _extract_url(payload: Any) -> str:
    """Pull the mp4 url out of a ``complete`` payload.

    Two shapes in the wild: the file dict at the top level (LTX-2.3), or wrapped
    under a ``video`` key alongside ``subtitles`` (distilled). Both end in a
    ``url``, so one reader covers them.
    """
    node = payload[0] if isinstance(payload, list) and payload else payload
    if isinstance(node, dict):
        if isinstance(node.get("video"), dict):
            node = node["video"]
        url = node.get("url")
        if url:
            return str(url)
    raise SpaceError(f"결과에서 mp4 url 을 못 찾았다: {str(payload)[:200]}")


def call(
    space: Space,
    *,
    prompt: str,
    duration: float,
    width: int,
    height: int,
    seed: Optional[int] = None,
    negative_prompt: Optional[str] = None,
    token: str = "",
    timeout: float = POLL_TIMEOUT_S,
) -> str:
    """Render one clip and return its (ephemeral) url. Raises the errors above."""
    base = f"https://{space.subdomain}.hf.space/gradio_api/call/{space.endpoint}"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if token:
        # Without this the call draws on the host IP's unauthenticated allowance,
        # which is 2 GPU-minutes a day and shared with anything else on that IP.
        headers["Authorization"] = f"Bearer {token}"

    args = space.build(
        prompt=prompt, duration=duration, width=width, height=height,
        seed=seed, negative_prompt=negative_prompt)

    started = time.monotonic()
    try:
        post = requests.post(base, json={"data": args}, headers=headers, timeout=_POST_TIMEOUT_S)
    except requests.RequestException as exc:
        raise SpaceDown(f"{space.subdomain} 에 못 붙었다: {exc}") from exc

    body = post.text or ""
    if post.status_code in (502, 503, 504) or "space is in error" in body.lower():
        raise SpaceDown(f"{space.subdomain} 가 죽어 있다 (HTTP {post.status_code})")
    if post.status_code >= 400:
        raise SpaceError(f"{space.subdomain} 가 거절했다 (HTTP {post.status_code}): {body[:200]}")
    try:
        event_id = (post.json() or {}).get("event_id")
    except ValueError as exc:
        raise SpaceError(f"{space.subdomain} 응답이 JSON 이 아니다: {body[:200]}") from exc
    if not event_id:
        raise SpaceError(f"{space.subdomain} 가 event_id 를 안 줬다: {body[:200]}")

    try:
        stream = requests.get(f"{base}/{event_id}", headers=headers, stream=True, timeout=timeout)
    except requests.RequestException as exc:
        raise SpaceError(f"결과 스트림이 끊겼다: {exc}") from exc

    with stream:
        event = ""
        for raw in stream.iter_lines(decode_unicode=True):
            if not raw:
                continue
            line = raw.strip()
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
                continue
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if event == "error":
                waited = time.monotonic() - started
                if waited < QUOTA_FAST_FAIL_S:
                    raise QuotaExhausted(
                        "HF ZeroGPU 무료 쿼터를 다 썼다. 첫 사용 시각에서 24시간 뒤에 리셋된다"
                        + ("" if token else
                           " (지금은 토큰 없이 호출해서 이 서버 IP 몫 2분만 쓰고 있다)"))
                raise SpaceError(f"{space.subdomain} 가 렌더 중에 실패했다 ({waited:.0f}초)")
            if event == "complete":
                return _extract_url(json.loads(data))
    raise SpaceError(f"{space.subdomain} 스트림이 결과 없이 끝났다")


def check_param_order() -> List[str]:
    """Compare each Space's recorded argument order against its live ``/info``.

    The positional array is the whole contract and nothing warns when a Space
    author reorders their inputs -- the call just silently renders the wrong
    thing. This is the check that catches it, and it costs no GPU quota.
    """
    lines: List[str] = []
    for space in SPACES:
        url = f"https://{space.subdomain}.hf.space/gradio_api/info"
        try:
            info = requests.get(url, timeout=30).json()
            live = tuple(
                p.get("parameter_name")
                for p in info["named_endpoints"][f"/{space.endpoint}"]["parameters"])
        except Exception as exc:  # noqa: BLE001 - a down Space is a skip, not a failure
            lines.append(f"SKIP  {space.subdomain}: {exc}")
            continue
        if live != space.params:
            lines.append(f"DRIFT {space.subdomain}\n  recorded={space.params}\n  live={live}")
        else:
            lines.append(f"OK    {space.subdomain} ({len(live)} args)")
    return lines


if __name__ == "__main__":
    for _line in check_param_order():
        print(_line)
