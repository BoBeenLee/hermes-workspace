"""Where everything lives, and the four environment variables the daemon sets.

Separate from ``__init__`` so the detached worker can import it without pulling in
the plugin's registration surface -- the worker runs as ``python worker.py``, long
after the hermes process that registered anything has exited.

The ``COMFYUI_*`` names are not a mistake and not a dependency on ComfyUI. They are
the KakaoTalk daemon's names for "where may I send from", "which room", "what binary
sends" and "what did the user actually ask" (``kakao_ai_chat.py``), and the comfyui
plugin happened to be the first consumer. Reading them here costs four lines; taking
a cross-plugin import on ``hermes_plugins.comfyui`` would couple two plugins that a
user can enable independently.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

# The YuE2 checkout and its two venvs. One repository, two Python environments:
# YuE2 pins transformers 4.57.6 / torch 2.10.0, SheetSage2 pins 4.45.2, and ComfyUI
# on this box runs 5.10.2. Three-way incompatible, which is why none of this is a
# ComfyUI graph. See ops/remote-comfyui knowledge/models/yue2.md.
YUE_ROOT = Path(os.environ.get("YUE2_ROOT") or HOME / "src" / "YuE")
YUE_PYTHON = YUE_ROOT / ".venv" / "bin" / "python"
SHEETSAGE_PYTHON = YUE_ROOT / ".venv-sheetsage2" / "bin" / "python"
SHEETSAGE_INFER = YUE_ROOT / "models" / "SheetSage2" / "infer.py"
GENERATE_PY = YUE_ROOT / "examples" / "generate.py"

# ffmpeg is not installed on this host. imageio-ffmpeg bundles an aarch64 static
# build (7.0.2, with libmp3lame) inside the SheetSage2 venv, and installing that
# package is what let SheetSage2 run without `sudo apt install ffmpeg` at all.
FFMPEG = YUE_ROOT / ".venv-sheetsage2" / "bin" / "ffmpeg"

# MOSS-Music is the only thing here that can listen to a song and say what it is.
MOSS_PYTHON = HOME / "venvs" / "moss-music" / "bin" / "python"
MOSS_REPO = HOME / "src" / "MOSS-Music"
MOSS_MODEL = HOME / "models" / "MOSS-Music-8B-Instruct"
# None, not Path(""): an empty Path is PosixPath(".") and is truthy, so the
# "unset" branch downstream never runs and .with_suffix() raises on it.
_moss_override = os.environ.get("MOSS_DESCRIBE_SCRIPT")
MOSS_SCRIPT = Path(_moss_override) if _moss_override else None

STATE_DIR = Path(os.environ.get("YUE2_STATE_DIR") or HOME / ".hermes" / "yue2")
JOBS_DIR = STATE_DIR / "jobs"
WORK_DIR = STATE_DIR / "work"

YT_DLP = Path(os.environ.get("YT_DLP_BIN") or HOME / ".local" / "bin" / "yt-dlp")

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # KakaoTalk's attach_max_bytes, the tightest consumer.


def max_bytes() -> int:
    try:
        return int(os.environ.get("COMFYUI_MAX_BYTES") or DEFAULT_MAX_BYTES)
    except ValueError:
        return DEFAULT_MAX_BYTES


def kakao_target() -> tuple | None:
    """(outbox, chat_id, send_bin) when a room is waiting, else None.

    None is the gateway and the CLI, where nothing is listening for a file and
    ``music_cover_status`` is how the path gets picked up.
    """
    outbox = os.environ.get("COMFYUI_OUTBOX_DIR")
    chat_id = os.environ.get("COMFYUI_CHAT_ID")
    send_bin = os.environ.get("COMFYUI_SEND_BIN")
    if not (outbox and chat_id and send_bin):
        return None
    try:
        return Path(os.path.expanduser(outbox)), int(chat_id), send_bin
    except ValueError:
        return None


def caption_for(limit: int = 60) -> str:
    """"다 됐어", plus what was asked, unless the room already shows it.

    A song that lands eight minutes later is orphaned without this: the room has
    moved on and nothing ties the file to the request. When the daemon threads the
    delivery, KakaoTalk draws the question above the answer already and repeating
    it is noise.
    """
    if os.environ.get("KAKAO_THREAD_ID"):
        return "다 됐어"
    text = " ".join((os.environ.get("COMFYUI_REQUEST") or "").split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return f'다 됐어 - "{text}"' if text else "다 됐어"
