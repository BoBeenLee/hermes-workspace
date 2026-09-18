"""MiniMax Music 3 on the local ComfyUI, as two tools rather than a provider slot.

hermes has provider registries for images, video, TTS and transcription -- there is
no music one -- so this registers plain tools instead. They go into the ``web``
toolset because that is the one the KakaoTalk daemon's fixed ``--toolsets`` string
already carries; a new toolset name is dropped with a one-line warning.

**A song is not a render, and its cost is the song's length, not the graph.**
Measured on this box: a 60s cap gave 41s of music in 205s wall clock (cold), a 40s
cap 23.6s of music in 108s (warm), and a full 3-4 minute song 846s / 1159s (music
repo, ``runs/2026-08-29-minimax-music3-ai-future.md``). Nothing here waits for
that, not even on the gateway -- every call returns a prompt_id, and the file
arrives either through the detached deliverer (KakaoTalk) or through
``music_status`` (gateway, CLI).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

try:  # how the plugin loader imports it
    from . import comfy
except ImportError:  # `python3 music.py` for the self-check, with no package around it
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import comfy

logger = logging.getLogger(__name__)

WORKFLOW = Path(__file__).resolve().parent / "workflows" / "minimax-music3-t2m.json"

# Node ids are the ComfyUI bundled template's (audio_minimax_music_3.json), kept
# as-is so the graph stays diffable against it and against the music repo's takes.
TEXT_NODE, SAMPLER_NODE, SAVE_NODE = "4", "7", "9"

# The baseline is take 1 of the music repo, unchanged: 30 steps, cfg 1.7, top_k 50,
# euler/simple. Those live in the workflow file. Only four inputs move per request.
DEFAULT_MAX_DURATION_S = 120.0
MAX_DURATION_S = 360.0  # MiniMaxMusic3TextEncode's own ceiling.

# Twice the longest measured run, because the deliverer is the only thing that will
# ever say anything in the room and a child that gives up early is a silent failure.
DELIVER_TIMEOUT_S = 2400.0

DELIVERY_NOTE = (
    "노래 파일은 위 audio 경로에 있다. 사용자에게 들려주려면 그 절대경로를 파일로 첨부해라 "
    "(카카오톡이면 `[[file: 경로]]` 한 줄). `[[image: ]]` 로는 거부된다. 경로만 글로 적으면 전달되지 않는다.")

GENERATE_SCHEMA = {
    "name": "music_generate",
    "description": (
        "Write and record a full song locally with MiniMax Music 3 (vocals, lyrics, arrangement). "
        "Use it for any 노래/음악/곡 만들어 달라는 요청. You write the caption and the lyrics -- the "
        "model sings exactly the lyrics you pass. IT TAKES MINUTES, roughly as long as the song is "
        "allowed to be: ~3 minutes of waiting for a 60-second song, 15-20 for a full 3-4 minute one. "
        "This returns immediately with a prompt_id and the song is delivered on its own when it is "
        "done. Say one short line ('노래 만들고 있어, 좀 걸려') and end the turn. NEVER call it twice for "
        "one request -- a second call is another whole render and a second song. Text only; it cannot cover, remix, or "
        "continue an existing track, and it has no melody or reference-audio input -- when the user "
        "points at a song they already have (이 곡처럼 / 이 느낌으로 / 커버 / 레퍼런스), use music_cover instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "caption": {
                "type": "string",
                "description": (
                    "Production brief in English, however long you like. Genre, BPM, key, mood, "
                    "the vocal (gender, timbre, delivery), and the arrangement section by section. "
                    "This is the only style control there is -- a one-line caption gets a generic song."
                ),
            },
            "lyrics": {
                "type": "string",
                "description": (
                    "The words to sing, in any language, with section tags on their own lines: "
                    "[Intro] [Verse] [Pre-Chorus] [Chorus] [Bridge] [Instrumental] [Outro]. "
                    "Lyric length is what actually sets the song's length. Leave empty for an instrumental."
                ),
            },
            "max_duration": {
                "type": "number",
                "description": (
                    f"Upper bound in seconds (default {int(DEFAULT_MAX_DURATION_S)}, max {int(MAX_DURATION_S)}). "
                    "A cap, not a target: the song ends when the lyrics do. Longer costs proportionally more time."
                ),
                "minimum": 30, "maximum": MAX_DURATION_S,
            },
            "seed": {
                "type": "integer",
                "description": "Optional. Random each call. The same seed does not reproduce a song once the lyrics change.",
            },
        },
        "required": ["caption"],
    },
}

STATUS_SCHEMA = {
    "name": "music_status",
    "description": (
        "Check a song started by music_generate and get its file path once it is finished. "
        "Only useful outside KakaoTalk -- there the song is delivered to the room on its own. "
        "Expect 'running' for the first few minutes, longer for a long song."
    ),
    "parameters": {
        "type": "object",
        "properties": {"prompt_id": {"type": "string", "description": "The prompt_id music_generate returned."}},
        "required": ["prompt_id"],
    },
}


def build_graph(caption: str, lyrics: str, seed: int, max_duration: float) -> Dict[str, Any]:
    """The baseline graph with this request's four inputs patched in.

    Both seeds move together. The text encode's seed is the one that matters --
    it is an autoregressive generator, so it decides the arrangement *and* the
    latent's shape -- and leaving the sampler's at the file's constant would make
    "same seed" mean two different things.
    """
    return comfy.patch(comfy.load_workflow(WORKFLOW), {
        TEXT_NODE: {"caption": caption, "lyrics": lyrics, "seed": seed,
                    "max_duration": max_duration},
        SAMPLER_NODE: {"seed": seed},
    })


def generate(args: Dict[str, Any]) -> Dict[str, Any]:
    caption = (args.get("caption") or "").strip()
    if not caption:
        return {"error": "caption is required (English production brief)"}
    lyrics = (args.get("lyrics") or "").strip()
    try:
        duration = float(args.get("max_duration") or DEFAULT_MAX_DURATION_S)
    except (TypeError, ValueError):
        duration = DEFAULT_MAX_DURATION_S
    duration = max(30.0, min(duration, MAX_DURATION_S))
    try:
        seed = int(args.get("seed")) if args.get("seed") is not None else comfy.random_seed()
    except (TypeError, ValueError):
        seed = comfy.random_seed()

    client = comfy.ComfyUI()
    refusal = client.gate()
    if refusal:
        return {"error": refusal}

    try:
        prompt_id = client.submit(build_graph(caption, lyrics, seed, duration))
    except comfy.ComfyError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - one uniform shape for the dispatcher
        logger.debug("music_generate failed", exc_info=True)
        return {"error": f"ComfyUI 호출 실패: {exc}"}

    result = {"success": True, "status": "queued", "prompt_id": prompt_id,
              "seed": seed, "max_duration": duration, "instrumental": not lyrics}
    target = comfy.async_target()
    if target and comfy.spawn_deliverer(
            prompt_id, target, client, node=SAVE_NODE, fence="file", noun="노래",
            caption=comfy.caption_for(caption), timeout=DELIVER_TIMEOUT_S):
        result["note"] = ("노래는 다 되면 따로 이 방으로 간다 (길이에 따라 3~20분). 지금은 '만들고 있어' 한 줄만 "
                          "답하고 턴을 끝내라. 다시 부르지 마라 - 중복으로 두 곡이 나간다.")
        return result
    result["note"] = (f"길이에 따라 3~20분 걸린다. 끝나면 music_status 로 prompt_id={prompt_id} 를 확인해라. "
                      "지금은 '만들고 있어' 한 줄만 답하고 턴을 끝내라.")
    return result


def status(args: Dict[str, Any]) -> Dict[str, Any]:
    prompt_id = (args.get("prompt_id") or "").strip()
    if not prompt_id:
        return {"error": "prompt_id is required"}
    client = comfy.ComfyUI()
    try:
        # timeout=0 is one history read with the failure check attached; poll()
        # owns that check, so there is no second copy of it here.
        entry = client.poll(prompt_id, timeout=0.0)
        if entry is None:
            return {"status": "running", "prompt_id": prompt_id,
                    "note": "아직 만들고 있다. 길이에 따라 3~20분 걸린다."}
        rendered = client.output_paths(entry, SAVE_NODE)[0]
        handed = comfy.hand_over(rendered, comfy.destination_dir("audio"), comfy.max_bytes())
        comfy.prune(handed.parent)
    except comfy.ComfyError as exc:
        return {"status": "error", "prompt_id": prompt_id, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.debug("music_status failed", exc_info=True)
        return {"status": "error", "prompt_id": prompt_id, "error": f"ComfyUI 호출 실패: {exc}"}
    return {"status": "done", "prompt_id": prompt_id, "audio": str(handed),
            "bytes": handed.stat().st_size, "note": DELIVERY_NOTE}


def available() -> bool:
    """Local only: the picker calls this on every paint, so no network here."""
    return WORKFLOW.is_file()


def demo() -> None:
    """Self-check: the graph the baseline produces is the graph we think it is."""
    graph = build_graph("test caption", "[Verse]\nla la la", 1234, 90.0)
    text = graph[TEXT_NODE]["inputs"]
    assert text["caption"] == "test caption" and text["lyrics"].startswith("[Verse]")
    assert text["seed"] == 1234 == graph[SAMPLER_NODE]["inputs"]["seed"]
    assert text["max_duration"] == 90.0
    assert graph[SAVE_NODE]["class_type"] == "SaveAudioMP3"
    # The file on disk must stay the untouched baseline: patch() deep-copies, and a
    # mutated template would silently carry one request's lyrics into the next.
    fresh = comfy.load_workflow(WORKFLOW)
    assert fresh[TEXT_NODE]["inputs"]["caption"] == ""
    # 128k, not the node's V0 default: at V0 a six-minute song crosses KakaoTalk's
    # 10 MB attachment cap and is dropped without a word.
    assert graph[SAVE_NODE]["inputs"]["quality"] == "128k"
    print("music.py self-check ok")


if __name__ == "__main__":
    demo()
