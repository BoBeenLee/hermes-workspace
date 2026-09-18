"""Reference-driven song generation with YuE2, as two plain tools.

hermes has provider registries for images, video, TTS and transcription; there is
no music one, so this registers tools the same way ``plugins/comfyui/music.py``
does, into the ``web`` toolset -- the one already in the KakaoTalk daemon's fixed
``--toolsets`` string. A new toolset name is dropped with a one-line warning, and
riding an existing one means the daemon is not touched at all.

This is the second music backend and the two do not overlap. ``music_generate``
(comfyui plugin, MiniMax Music 3) writes a song from text and says so itself: it
"cannot cover, remix, or continue an existing track, and it has no melody or
reference-audio input". That is exactly the hole here.

Nothing in this plugin runs in ComfyUI. YuE2 pins transformers 4.57.6 against
ComfyUI's 5.10.2, and the transcription step pins 4.45.2 -- three-way incompatible,
so all three live in their own environments and this plugin shells out to them.
There are ComfyUI node packs for YuE2, but their own documentation says generation
stays "score-conditioned rather than audio-to-audio" and "audio transcription is
not included", which is the half we need.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict

try:  # how the plugin loader imports it, under a package name it chooses
    from . import paths, worker
except ImportError:  # `python3 __init__.py` for the self-check, with no package
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import paths  # type: ignore
    import worker  # type: ignore

logger = logging.getLogger(__name__)

WORKER = Path(__file__).resolve().parent / "worker.py"

# What the model should say while it waits, reused nearly verbatim from music.py:
# the shape is proven and the two tools reading differently would be worse.
WAIT_NOTE = ("노래는 다 되면 따로 이 방으로 간다 (6~12분). 지금은 '만들고 있어' 한 줄만 답하고 턴을 "
             "끝내라. 다시 부르지 마라 - 중복으로 두 곡이 나간다.")

GENERATE_SCHEMA = {
    "name": "music_cover",
    "description": (
        "Write a NEW song FROM a song the user already has. This is the tool for 이 곡처럼 / "
        "이 노래 느낌으로 / 레퍼런스 / 커버 / 이 멜로디로 requests -- anything where the user points at an "
        "existing track. It listens to that track and measures its tempo and key rather than guessing "
        "them from the title, so never describe a named song from memory: pass the file. "
        "For a song from nothing but your own words, use music_generate instead. "
        "IT TAKES 6-12 MINUTES. This returns immediately with a job_id and the song is delivered to "
        "the room on its own. Say one short line ('만들고 있어, 좀 걸려') and end the turn. NEVER call it "
        "twice for one request -- a second call is another whole song. "
        "The reference must be a FILE the user sent (KakaoTalk 파일 첨부) or a URL; a KakaoTalk 음성 "
        "메시지 is not downloaded and cannot be used -- ask for it as a 파일. "
        "Local and non-commercial: the model's weights forbid commercial use."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reference": {
                "type": "string",
                "description": (
                    "The reference track: an absolute path to a file already on disk (the room's "
                    "attachments arrive in the conversation as `file=/path/...` -- pass that path "
                    "verbatim), or an http(s) URL to download. Required."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["style", "cover"],
                "description": (
                    "'style' (default) borrows only mood, instrumentation and genre and writes a new "
                    "melody -- an original song that sounds like the reference. 'cover' keeps the "
                    "reference's own melody and re-arranges it, which makes a derivative of that "
                    "recording; choose it only when the user asks for the same tune. 'cover' is slower."
                ),
            },
            "style": {
                "type": "string",
                "description": (
                    "Optional production brief in English for what should CHANGE -- the target genre, "
                    "instrumentation, vocal and mood. What the reference already is gets measured and "
                    "added for you, so write the destination, not the source. Safe to leave empty."
                ),
            },
            "lyrics": {
                "type": "string",
                "description": (
                    "The words to sing, with section tags on their own lines: [Verse] [Chorus] "
                    "[Bridge] [Outro]. Leave empty for an instrumental. Official languages are "
                    "English and Chinese; Korean sings but its syllable alignment is untested."
                ),
            },
            "seed": {
                "type": "integer",
                "description": "Optional. Only useful to repeat an earlier job with one thing changed.",
            },
        },
        "required": ["reference"],
    },
}

STATUS_SCHEMA = {
    "name": "music_cover_status",
    "description": (
        "Check a song started by music_cover and get its file path once it is finished. "
        "Only useful outside KakaoTalk -- there the song is delivered to the room on its own. "
        "Expect 'running' for the first several minutes."
    ),
    "parameters": {
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "The job_id music_cover returned."}},
        "required": ["job_id"],
    },
}

DELIVERY_NOTE = (
    "노래 파일은 위 audio 경로에 있다. 사용자에게 들려주려면 그 절대경로를 파일로 첨부해라 "
    "(카카오톡이면 `[[file: 경로]]` 한 줄). `[[image: ]]` 로는 거부된다. 경로만 글로 적으면 전달되지 않는다.")


def resolve_reference(value: str) -> tuple[str, str]:
    """(reference, error). A URL passes through; a path must exist before we detach.

    Checked here rather than in the worker because a typo should come back inside
    the turn, while the user is still there, instead of as a message eight minutes
    later from a job that never had a chance. Pure -- see demo().
    """
    reference = (value or "").strip()
    if not reference:
        return "", "reference is required: a file path or a URL"
    if worker.looks_like_url(reference):
        return reference, ""
    expanded = os.path.expanduser(reference)
    if not Path(expanded).is_file():
        return "", (f"그 경로에 파일이 없다: {reference}. 카톡 첨부는 대화에 `file=/경로` 로 들어오니 그 경로를 "
                    "그대로 넘겨라. 음성 메시지는 파일로 저장되지 않으니 사용자에게 파일로 보내 달라고 해라.")
    return expanded, ""


def generate(args: Dict[str, Any]) -> Dict[str, Any]:
    reference, refusal = resolve_reference(args.get("reference") or "")
    if refusal:
        return {"error": refusal}

    mode = (args.get("mode") or "style").strip().lower()
    if mode not in ("style", "cover"):
        mode = "style"
    try:
        seed = int(args.get("seed")) if args.get("seed") is not None else 831001
    except (TypeError, ValueError):
        seed = 831001

    if not paths.YUE_PYTHON.is_file():
        return {"error": "YuE2 가 이 호스트에 설치돼 있지 않다."}

    job_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    command = [sys.executable, str(WORKER),
               "--job-id", job_id, "--reference", reference, "--mode", mode,
               "--style", (args.get("style") or "").strip(),
               "--lyrics", (args.get("lyrics") or "").strip(),
               "--seed", str(seed)]
    target = paths.kakao_target()
    if target:
        outbox, chat_id, send_bin = target
        command += ["--chat-id", str(chat_id), "--send-bin", send_bin, "--outbox", str(outbox)]

    try:
        # start_new_session and closed stdio are the point: this outlives the
        # hermes process that ends with the turn.
        subprocess.Popen(  # noqa: S603 - argv only, every value is ours
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("music_cover could not spawn its worker", exc_info=True)
        return {"error": f"작업을 시작하지 못했다: {exc}"}

    result = {"success": True, "status": "started", "job_id": job_id, "mode": mode, "seed": seed}
    result["note"] = WAIT_NOTE if target else (
        f"6~12분 걸린다. 끝나면 music_cover_status 로 job_id={job_id} 를 확인해라. "
        "지금은 '만들고 있어' 한 줄만 답하고 턴을 끝내라.")
    return result


def status(args: Dict[str, Any]) -> Dict[str, Any]:
    job_id = (args.get("job_id") or "").strip()
    if not job_id:
        return {"error": "job_id is required"}
    job = worker.read_job(job_id)
    if job is None:
        return {"status": "unknown", "job_id": job_id, "error": "그런 job_id 가 없다."}
    state = job.get("status")
    if state == "done":
        return {"status": "done", "job_id": job_id, "audio": job.get("audio"),
                "bytes": job.get("bytes"), "style": job.get("style"), "note": DELIVERY_NOTE}
    if state in ("error", "stopped"):
        return {"status": state, "job_id": job_id, "error": job.get("error") or "실패"}
    stage = worker.STAGE_NOTES.get(job.get("stage") or "", "작업 중")
    return {"status": "running", "job_id": job_id, "stage": job.get("stage"),
            "note": f"{stage}. 6~12분 걸린다."}


def available() -> bool:
    """The picker calls this on every paint, so it stays a local stat and nothing more."""
    return paths.YUE_PYTHON.is_file() and paths.GENERATE_PY.is_file()


def _json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def register(ctx) -> None:
    ctx.register_tool(
        name="music_cover", toolset="web", schema=GENERATE_SCHEMA,
        handler=lambda args, **kw: _json(generate(args)),
        check_fn=available, emoji="🎼")
    ctx.register_tool(
        name="music_cover_status", toolset="web", schema=STATUS_SCHEMA,
        handler=lambda args, **kw: _json(status(args)),
        check_fn=available, emoji="🎚")


def demo() -> None:
    """Self-check: the refusal that has to happen inside the turn, and the schema."""
    reference, refusal = resolve_reference("/definitely/not/here.mp3")
    assert reference == "" and "file=" in refusal, refusal
    assert resolve_reference("") == ("", "reference is required: a file path or a URL")
    assert resolve_reference("https://youtu.be/x") == ("https://youtu.be/x", "")
    here, refusal = resolve_reference(__file__)
    assert here == __file__ and refusal == ""

    # A missing file must not detach a worker: the user is still in the room.
    assert generate({"reference": "/definitely/not/here.mp3"}).get("error")
    assert generate({}).get("error")

    assert GENERATE_SCHEMA["parameters"]["required"] == ["reference"]
    assert set(GENERATE_SCHEMA["parameters"]["properties"]["mode"]["enum"]) == {"style", "cover"}
    assert status({}).get("error") and status({"job_id": "nope"})["status"] == "unknown"
    print("yue2 __init__.py self-check ok")


if __name__ == "__main__":
    demo()
