"""Minimal ComfyUI REST client plus the preflight gate, for a ComfyUI on the same host.

Same host is the whole reason this is short: the rendered file is on our own
filesystem, so there is no ``/view`` download step and no byte copy over HTTP.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8188"
DEFAULT_OUTPUT_ROOT = "~/src/ComfyUI/output"

# Images only. Video keeps its own, much higher floor (the number
# ops/remote-comfyui's batch runner uses) because a video job's peak is an order
# of magnitude above a 0.5 MP sample. Reusing 80 here would refuse every image
# while llama-local is up, which is the normal state of this box.
DEFAULT_MIN_FREE_GB = 24.0


class ComfyError(RuntimeError):
    """A ComfyUI call failed. ``prompt_id`` is set once the job was accepted."""

    def __init__(self, message: str, prompt_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.prompt_id = prompt_id


def mem_available_gb() -> Optional[float]:
    """MemAvailable from /proc/meminfo, or None off Linux.

    Deliberately not ComfyUI's ``/system_stats`` ``vram_free``: on GB10 that
    undercounts by ~35 GB (unified memory), which turns the floor into a
    spurious refusal on a healthy box.
    """
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024.0 * 1024.0)
    except OSError:
        return None
    return None


class ComfyUI:
    def __init__(self, base_url: Optional[str] = None, output_root: Optional[str] = None) -> None:
        self.base_url = (base_url or os.environ.get("COMFYUI_URL") or DEFAULT_URL).rstrip("/")
        root = output_root or os.environ.get("COMFYUI_OUTPUT_ROOT") or DEFAULT_OUTPUT_ROOT
        self.output_root = Path(os.path.expanduser(root))

    # -- health / gate ----------------------------------------------------

    def is_available(self) -> bool:
        try:
            return requests.get(f"{self.base_url}/system_stats", timeout=5).status_code == 200
        except Exception:
            return False

    def queue_depth(self) -> int:
        q = requests.get(f"{self.base_url}/queue", timeout=10).json()
        return len(q.get("queue_running") or []) + len(q.get("queue_pending") or [])

    def gate(self, min_free_gb: float = DEFAULT_MIN_FREE_GB) -> Optional[str]:
        """Refusal reason, or None to proceed.

        Two conditions, and both are load-bearing. A non-empty queue is the
        safety one -- stacking heavy jobs on this box is what hung the host --
        and it doubles as the speed one, because a second job of a different
        family evicts an 18 GB model stack and turns a 15s render into a 300s one.
        """
        try:
            depth = self.queue_depth()
        except Exception as exc:
            return f"ComfyUI에 닿지 않는다 ({exc})"
        if depth:
            return f"ComfyUI 큐에 잡이 {depth}개 돌고 있다. 끝나면 다시 시켜라"
        free = mem_available_gb()
        if free is not None and free < min_free_gb:
            return f"메모리가 {free:.0f}GB 뿐이라 ({min_free_gb:.0f}GB 필요) 지금은 못 돌린다"
        return None

    # -- run --------------------------------------------------------------

    def submit(self, graph: dict) -> str:
        resp = requests.post(f"{self.base_url}/prompt", json={"prompt": graph}, timeout=30)
        if resp.status_code != 200:
            raise ComfyError(f"/prompt {resp.status_code}: {resp.text[:400]}")
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise ComfyError(f"/prompt gave no prompt_id: {resp.text[:200]}")
        return prompt_id

    def history(self, prompt_id: str) -> Optional[dict]:
        """The finished entry, or None while it is still queued or running."""
        resp = requests.get(f"{self.base_url}/history/{prompt_id}", timeout=15)
        resp.raise_for_status()
        return (resp.json() or {}).get(prompt_id)

    def poll(self, prompt_id: str, timeout: float, interval: float = 3.0) -> Optional[dict]:
        """Entry when it finishes, None when ``timeout`` passes first.

        None is not failure: the job is still running server-side and the caller
        may hand ``prompt_id`` to a deliverer. Only a broken graph raises.
        """
        deadline = time.monotonic() + timeout
        while True:
            entry = self.history(prompt_id)
            if entry is not None:
                status = (entry.get("status") or {})
                if status.get("status_str") == "error" or status.get("completed") is False:
                    raise ComfyError(_error_text(entry), prompt_id=prompt_id)
                return entry
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)

    def output_paths(self, entry: dict, node_id: str) -> list[Path]:
        """Local paths for a finished node's outputs.

        ComfyUI files every saved artifact under ``images`` -- stills and core
        ``SaveVideo`` mp4s alike, the latter flagged by a sibling ``animated``.
        ``gifs`` is only ever VideoHelperSuite, which no workflow here saves with.
        ``audio`` is the one exception: ``SaveAudio*`` files under its own key.
        """
        out = (entry.get("outputs") or {}).get(node_id) or {}
        items = (out.get("images") or out.get("gifs") or out.get("video")
                 or out.get("audio") or [])
        if not items:
            raise ComfyError(
                f"node {node_id} produced nothing; nodes with output: "
                f"{sorted((entry.get('outputs') or {}).keys())}"
            )
        return [self.output_root / item.get("subfolder", "") / item["filename"] for item in items]


def _error_text(entry: dict) -> str:
    """Pull the first real node error out of a failed history entry."""
    for message in (entry.get("status") or {}).get("messages") or []:
        if isinstance(message, list) and len(message) > 1 and message[0] == "execution_error":
            detail = message[1] or {}
            return (f"{detail.get('node_type', '?')}: "
                    f"{str(detail.get('exception_message') or '')[:300]}")
    return json.dumps(entry.get("status") or {}, ensure_ascii=False)[:300]


# -- workflow helpers -----------------------------------------------------


def load_workflow(path: Path) -> dict:
    """Load a bare API graph. ``{"prompt": {...}}`` wrappers are unwrapped."""
    with open(path) as handle:
        graph = json.load(handle)
    return graph.get("prompt", graph)


def patch(graph: dict, patches: dict[str, dict[str, Any]]) -> dict:
    """Deep-copy and apply ``{node_id: {input_name: value}}``.

    Unknown node ids raise rather than pass: ComfyUI accepts a graph with a
    typo'd input silently and only dies at execution, minutes later.
    """
    out = copy.deepcopy(graph)
    for node_id, values in patches.items():
        if node_id not in out:
            raise ComfyError(f"node {node_id!r} not in workflow (have {sorted(out)})")
        out[node_id]["inputs"].update(values)
    return out


def random_seed() -> int:
    return random.randint(0, 2**32 - 1)


# -- handing the file over ------------------------------------------------


def hand_over(rendered: Path, dest_dir: Path, max_bytes: int) -> Path:
    """Copy a render out of ComfyUI's tree, shrinking it if a consumer would refuse it.

    ComfyUI only writes PNG. At 0.5 MP that is comfortably small, but the same
    path carries an upscaled render later and KakaoTalk drops an oversized
    attachment without a word, so the guard sits here rather than being
    discovered as a silent no-send.

    Lives in this module, not the provider, so the detached deliverer can reuse
    it without importing ``agent.*``.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"comfyui_{int(time.time() * 1000)}{rendered.suffix}"
    shutil.copy2(rendered, dest)
    if dest.stat().st_size <= max_bytes:
        return dest
    try:
        from PIL import Image

        jpeg = dest.with_suffix(".jpg")
        with Image.open(dest) as image:
            image.convert("RGB").save(jpeg, "JPEG", quality=90)
        dest.unlink(missing_ok=True)
        return jpeg
    except Exception:  # noqa: BLE001 - an oversized PNG still beats no image
        return dest


def prune(directory: Path, days: int = 7) -> None:
    """Drop handed-over files older than ``days``; nothing ever reads them back."""
    cutoff = time.time() - days * 86400
    try:
        for path in directory.glob("comfyui_*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


# -- handing a slow job to a detached child --------------------------------
#
# Shared by both tools and shaped by KakaoTalk: its tick is single-threaded, so a
# turn that waits on a render silences every other room. The gateway and the CLI
# set none of these variables and keep the synchronous path.

DELIVERER = Path(__file__).resolve().parent / "deliver.py"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # KakaoTalk's attach_max_bytes; the tightest consumer.


def destination_dir(kind: str = "images") -> Path:
    """Where the finished file is handed over.

    ``COMFYUI_OUTBOX_DIR`` exists for the KakaoTalk daemon, whose send path only
    accepts paths inside its own fenced outbox. Unset (gateway, CLI) lands in the
    hermes cache, which the media-delivery policy trusts unconditionally.
    """
    outbox = os.environ.get("COMFYUI_OUTBOX_DIR")
    if outbox:
        return Path(os.path.expanduser(outbox))
    from agent import provider_media

    return provider_media.cache_dir(kind)


def max_bytes() -> int:
    try:
        return int(os.environ.get("COMFYUI_MAX_BYTES") or DEFAULT_MAX_BYTES)
    except ValueError:
        return DEFAULT_MAX_BYTES


def async_target() -> Optional[tuple]:
    """(outbox, chat_id, send_bin) when this turn must not block, else None."""
    outbox = os.environ.get("COMFYUI_OUTBOX_DIR")
    chat_id = os.environ.get("COMFYUI_CHAT_ID")
    send_bin = os.environ.get("COMFYUI_SEND_BIN")
    if not (outbox and chat_id and send_bin):
        return None
    try:
        return Path(os.path.expanduser(outbox)), int(chat_id), send_bin
    except ValueError:
        return None


def caption_for(prompt: str, limit: int = 60) -> str:
    """Caption that names the request it answers, unless the result is a 댓글.

    A bare "다 됐어" arriving minutes later is orphaned -- by then the room has
    moved on and nothing ties it to what was asked. When the daemon threads the
    delivery (KAKAO_THREAD_ID), KakaoTalk already draws the question above the
    answer and the quote just repeats the line the reader is looking at. Without
    a thread, quoting is the only tie left: KakaoTalk's own reply form (a type=26
    row carrying src_logId) is unreachable through Iris.
    """
    if os.environ.get("KAKAO_THREAD_ID"):
        return "다 됐어"
    # The caller's own words when it passed them: what reaches the tool is the
    # model's expanded English rewrite, which nobody asked for by that name.
    text = " ".join((os.environ.get("COMFYUI_REQUEST") or prompt or "").split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return f'다 됐어 - "{text}"' if text else "다 됐어"


def spawn_deliverer(prompt_id: str, target: tuple, client: "ComfyUI", *, node: str,
                    caption: str = "다 됐어", fence: str = "image", noun: str = "그림",
                    timeout: float = 900.0) -> bool:
    """Detach a child to finish the job and send it. True when it started.

    ``start_new_session`` and closed stdio are the point: this must survive the
    hermes process exiting at the end of the turn. One child per submit, and
    prompt_ids are unique per submit, so no de-dup key is needed.
    """
    outbox, chat_id, send_bin = target
    try:
        subprocess.Popen(  # noqa: S603 - argv only, every value is ours
            [sys.executable, str(DELIVERER),
             "--prompt-id", prompt_id, "--node", node,
             "--chat-id", str(chat_id), "--send-bin", send_bin,
             "--outbox", str(outbox), "--url", client.base_url,
             "--output-root", str(client.output_root),
             "--max-bytes", str(max_bytes()), "--timeout", str(timeout),
             "--fence", fence, "--noun", noun, "--caption", caption],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("comfyui: could not spawn the deliverer (%s)", exc)
        return False
