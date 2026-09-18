"""Turn a reference recording into a new song, then hand it to the room.

Detached on purpose. The whole pipeline is transcription plus two model loads and
runs six to twelve minutes; a hermes tool has roughly 420 seconds before the core
gives up on it, and the KakaoTalk tick is single-threaded, so anything that waits
here silences every other room. The tool spawns this and returns a job id.

Three environments, because the models disagree about their dependencies: YuE2
pins transformers 4.57.6, SheetSage2 pins 4.45.2, ComfyUI on this box runs 5.10.2.
Nothing here is a ComfyUI graph and nothing here touches ComfyUI's queue.

It always says something. A room told "만들고 있어" that then hears nothing is the
one failure mode worth designing against, so every exit path -- success, refusal,
crash, SIGTERM from a deploy -- sends a line.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paths  # noqa: E402

# SheetSage2 reads at 24 kHz mono; handing it that directly skips a resample and
# makes the reference we measured and the reference we listened to the same file.
REFERENCE_RATE = 24000
# Past this the reference is a full album rip or a podcast, not a song, and every
# stage downstream scales with it.
REFERENCE_MAX_SECONDS = 420.0
# mp3 bitrates to walk down when the encode overshoots KakaoTalk's cap. 96k on a
# ten-minute song is still audible; refusing to send is not.
BITRATE_LADDER = ("192k", "128k", "96k", "64k")
# YuE2 wants ~10 GB and SheetSage2 ~4.3 GB. ComfyUI holding models is the usual
# reason there is less, and /free is cheap when its queue is empty.
MIN_FREE_GB = 24.0
COMFY_URL = os.environ.get("COMFYUI_URL") or "http://127.0.0.1:8188"

STAGE_NOTES = {
    "reference": "레퍼런스 곡 받는 중",
    "transcribe": "레퍼런스 분석하는 중",
    "describe": "레퍼런스 듣는 중",
    "generate": "곡 만드는 중",
    "encode": "파일로 굽는 중",
}


# -- job file ---------------------------------------------------------------
#
# One JSON per job, the same shape the room and `music_cover_status` both read.
# Written after every stage so a job that dies mid-way still says where it got to.

def write_job(job_id: str, **fields) -> Path:
    paths.JOBS_DIR.mkdir(parents=True, exist_ok=True)
    path = paths.JOBS_DIR / f"{job_id}.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = {"job_id": job_id, "created_at": time.time()}
    current.update(fields)
    current["updated_at"] = time.time()
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_job(job_id: str) -> dict | None:
    try:
        return json.loads((paths.JOBS_DIR / f"{job_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# -- talking to the room ----------------------------------------------------

def send(send_bin: str, chat_id: int, text: str) -> None:
    """One message through the daemon's own outside-caller entry point.

    Deliberately not a second transport: `--send-to` already owns the bot prefix,
    the thread id and the [[file:]] fence.
    """
    try:
        subprocess.run([sys.executable, send_bin, "--send-to", str(chat_id), "--text", text],
                       stdin=subprocess.DEVNULL, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


# -- memory ------------------------------------------------------------------

def mem_available_gb() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024 * 1024)
    except (OSError, ValueError, IndexError):
        return None
    return None


def free_comfyui() -> None:
    """Ask ComfyUI to drop its models. Best effort: it may not be running at all.

    This is the gate `run_comfy_batch.py` applies to every ComfyUI job and that
    YuE2 would otherwise skip entirely -- it is a separate process, invisible to
    that gate, and the two of them sharing unified memory is what takes the host
    down.
    """
    body = json.dumps({"unload_models": True, "free_memory": True}).encode()
    request = urllib.request.Request(f"{COMFY_URL}/free", data=body,
                                     headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=20).read()
    except Exception:  # noqa: BLE001 - ComfyUI being down is not our problem
        pass


# -- stage 1: the reference --------------------------------------------------

def looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def fetch_reference(reference: str, work: Path) -> Path:
    """A local path stays put; a URL goes through yt-dlp. Returns what to decode."""
    if not looks_like_url(reference):
        source = Path(os.path.expanduser(reference))
        if not source.is_file():
            raise RuntimeError(f"레퍼런스 파일을 못 찾았어: {reference}")
        return source
    if not paths.YT_DLP.is_file():
        raise RuntimeError("링크에서 받으려면 yt-dlp 가 필요한데 이 호스트에 없어.")
    target = work / "source.%(ext)s"
    result = subprocess.run(
        [str(paths.YT_DLP), "-q", "--no-playlist", "-f", "bestaudio/best",
         "-o", str(target), reference],
        capture_output=True, text=True, timeout=600, check=False)
    got = sorted(work.glob("source.*"))
    if result.returncode or not got:
        tail = (result.stderr or "").strip().splitlines()[-1:] or ["실패"]
        raise RuntimeError(f"링크에서 오디오를 못 받았어: {tail[0][:160]}")
    return got[0]


def to_reference_wav(source: Path, work: Path) -> Path:
    """Decode to 24 kHz mono wav, truncated. ffmpeg comes from the SheetSage2 venv.

    There is no system ffmpeg on this host; `pip install imageio-ffmpeg` put an
    aarch64 static build inside that venv, which is also what let SheetSage2 be
    installed without touching the host at all.
    """
    if not paths.FFMPEG.exists():
        raise RuntimeError("ffmpeg 이 없어 (imageio-ffmpeg 설치 확인 필요).")
    wav = work / "reference.wav"
    result = subprocess.run(
        [str(paths.FFMPEG), "-v", "error", "-nostdin", "-y", "-i", str(source),
         "-vn", "-ac", "1", "-ar", str(REFERENCE_RATE),
         "-t", str(REFERENCE_MAX_SECONDS), str(wav)],
        capture_output=True, text=True, timeout=600, check=False)
    if result.returncode or not wav.is_file():
        raise RuntimeError(f"오디오를 읽을 수 없어: {(result.stderr or '').strip()[:160]}")
    return wav


# -- stage 2: what the reference is ------------------------------------------

def transcribe(wav: Path, work: Path) -> Path:
    """SheetSage2 to ABC. Used by both modes -- `style` wants only its header.

    Running it for `style` too is not waste: the header is where tempo and key are
    measured rather than guessed, and this is the only tool on the box that can
    measure them (there is no librosa here, and no uv to borrow one).
    """
    out = work / "score"
    env = dict(os.environ)
    env["PATH"] = f"{paths.FFMPEG.parent}:{env.get('PATH', '')}"
    result = subprocess.run(
        [str(paths.SHEETSAGE_PYTHON), str(paths.SHEETSAGE_INFER), str(wav),
         "--output", str(out), "--melody-only"],
        capture_output=True, text=True, timeout=1800, check=False, env=env)
    score = out / "score.abc"
    if result.returncode or not score.is_file():
        tail = (result.stderr or "").strip().splitlines()[-1:] or ["실패"]
        raise RuntimeError(f"레퍼런스 채보 실패: {tail[0][:160]}")
    return out


def header_facts(score_abc: str, key_lab: str = "") -> dict:
    """Tempo and key, as measured. Pure -- see demo().

    `key.lab` is one `start end LABEL` row per key region; its first row is the
    song's key. The ABC header carries the tempo as `Q:1/4=NNN`.
    """
    facts: dict = {}
    tempo = re.search(r"^Q:\s*1/4\s*=\s*(\d+)", score_abc, re.MULTILINE)
    if tempo:
        facts["bpm"] = int(tempo.group(1))
    key = re.search(r"^K:\s*(\S+)", score_abc, re.MULTILINE)
    if key:
        facts["abc_key"] = key.group(1)
    for line in key_lab.splitlines():
        parts = line.split()
        if len(parts) >= 3 and ":" in parts[-1]:
            root, _, quality = parts[-1].partition(":")
            facts["key"] = f"{root} {quality}"
            break
    return facts


def describe(wav: Path, work: Path) -> str:
    """MOSS-Music listens and says what it hears. Best effort, by design.

    The caller wrote its `style` text without hearing anything, and writing a
    caption from prior knowledge of a named song is how this knowledge base got
    seven wrong facts into one caption. This is the only listener on the box.
    Losing it degrades the result; it must not lose the song.
    """
    try:
        script = paths.MOSS_SCRIPT or Path(__file__).with_name("describe_music_moss.py")
        prompts = script.with_name(script.stem + ".prompts.txt")
        if not (script.is_file() and prompts.is_file()
                and paths.MOSS_PYTHON.is_file() and paths.MOSS_MODEL.is_dir()):
            return ""
        result = subprocess.run(
            [str(paths.MOSS_PYTHON), str(script), str(wav),
             "--prompt-file", str(prompts), "--model", str(paths.MOSS_MODEL),
             "--repo", str(paths.MOSS_REPO)],
            capture_output=True, text=True, timeout=1500, check=False,
            cwd=str(paths.MOSS_REPO))
        if result.returncode:
            return ""
        (work / "moss.md").write_text(result.stdout, encoding="utf-8")
        return result.stdout
    except Exception:  # noqa: BLE001 - the docstring promises this cannot lose the song
        logging.getLogger(__name__).debug("MOSS description skipped", exc_info=True)
        return ""


def clip_sentences(text: str, limit: int) -> str:
    """Cut at a sentence end, not mid-word. Pure -- see demo().

    A style prompt ending "...The mix i" is what a plain slice produced on the
    first real run. Dropping the fragment costs a few characters and keeps the
    slot readable.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    return head[:cut + 1] if cut > limit // 3 else head.rsplit(" ", 1)[0]


def moss_prose(markdown: str, keep: tuple = (1, 2), limit: int = 700) -> str:
    """The answers out of describe_music_moss.py's report, and nothing else.

    Its stdout is a report, not a caption: `#` metadata lines carry torch and GPU
    versions, `## prompt N` headers carry timings, and every question is echoed
    back as a `>` block. Passing that through put "torch 2.9.1+cu128" and the
    questions themselves into a style prompt on the first real run.

    Only prompts 1 and 2 (production, then the vocal) belong in a style slot.
    Prompt 3 quotes the reference's own lyrics -- which must not leak into a song
    that carries different ones -- and 4 restates tempo and key we already
    measured. Pure -- see demo().
    """
    sections: dict[int, list[str]] = {}
    current = None
    for line in markdown.splitlines():
        stripped = line.strip()
        header = re.match(r"^##\s*prompt\s+(\d+)", stripped)
        if header:
            current = int(header.group(1))
            sections[current] = []
            continue
        if current is None or not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith(">") or stripped.startswith("["):
            continue
        sections[current].append(stripped)
    picked = [" ".join(sections.get(n, [])) for n in keep]
    return clip_sentences(" ".join(part for part in picked if part), limit)


def style_text(caller_style: str, described: str, facts: dict, limit: int = 1200) -> str:
    """The style prompt YuE2 gets: the reference first, the caller's brief last.

    Order is the only lever this slot has. `style` is a flat prose field with no
    notion of "source" versus "target", so a reference described as a female
    vocal and a caller asking for a male one simply contradict each other. The
    caller's words go last because they are the instruction and the reference is
    context, and prose prompts weight the end.

    Tempo and key go in as numbers because they were measured rather than
    guessed. They are weaker here than in an ABC header -- prose BPM drifted 8%
    in testing where a `Q:` header held to 2% -- but `style` mode lets YuE2 write
    its own score, and an ABC carrying a header and no notes is an untested
    shape. Pure -- see demo().
    """
    parts = []
    if facts.get("bpm"):
        parts.append(f"{facts['bpm']} BPM")
    if facts.get("key"):
        parts.append(f"{facts['key']}")
    measured = ", ".join(parts)
    heard = moss_prose(described) if described else ""
    # rstrip: the clipped prose already ends in a full stop, and ". ".join would
    # make it "...the calm.. 82 BPM".
    pieces = [p.rstrip(" .") for p in (heard, measured, caller_style.strip()) if p.strip()]
    return ". ".join(pieces)[:limit]


# -- stage 3: the song --------------------------------------------------------

def run_yue2(request: dict, abc_file: Path | None, cot: str, out_dir: Path) -> Path:
    """`examples/generate.py` from the checkout -- upstream owns the generator."""
    request_path = out_dir.parent / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    command = [str(paths.YUE_PYTHON), str(paths.GENERATE_PY),
               "--request", str(request_path), "--cot", cot, "--output", str(out_dir)]
    if abc_file is not None:
        command += ["--abc-file", str(abc_file)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=3000,
                            check=False, cwd=str(paths.YUE_ROOT))
    audio = out_dir / "audio.flac"
    if result.returncode or not audio.is_file():
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:] or ["실패"]
        raise RuntimeError(f"곡 생성 실패: {tail[0][:200]}")
    return audio


def to_mp3(flac: Path, destination: Path, cap: int) -> Path:
    """flac -> mp3, walking the bitrate down until it fits.

    YuE2 writes 48 kHz stereo flac: 8.5 MB for 58 seconds, so a three-minute song
    is far over KakaoTalk's 10 MB cap, and an oversized attachment is dropped
    without a word rather than refused. Returns the last attempt either way -- an
    over-cap file that someone can look at beats a silent nothing.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    mp3 = destination
    for bitrate in BITRATE_LADDER:
        result = subprocess.run(
            [str(paths.FFMPEG), "-v", "error", "-nostdin", "-y", "-i", str(flac),
             "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3)],
            capture_output=True, text=True, timeout=600, check=False)
        if result.returncode or not mp3.is_file():
            raise RuntimeError(f"mp3 변환 실패: {(result.stderr or '').strip()[:160]}")
        if mp3.stat().st_size <= cap:
            return mp3
    return mp3


def prune(directory: Path, days: int = 7) -> None:
    cutoff = time.time() - days * 86400
    try:
        for path in directory.glob("yue2_*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
    except OSError:
        pass


# -- the pipeline -------------------------------------------------------------

def run(args) -> int:
    job_id = args.job_id
    target = paths.kakao_target()
    chat_id = args.chat_id if args.chat_id is not None else (target[1] if target else None)
    send_bin = args.send_bin or (target[2] if target else None)
    outbox = Path(args.outbox) if args.outbox else (target[0] if target else paths.STATE_DIR / "out")

    def say(text: str) -> None:
        if chat_id is not None and send_bin and not args.no_send:
            send(send_bin, chat_id, text)

    def stage(name: str) -> None:
        write_job(job_id, status="running", stage=name)

    # A deploy restarts the daemon by killing its whole cgroup, and this child is
    # inside it. Speak before dying rather than leaving the room waiting.
    def on_term(_signum, _frame):
        write_job(job_id, status="stopped", error="SIGTERM")
        say("노래 만들던 게 중단됐어 (서버가 다시 뜨는 중). 다시 불러 줘.")
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, on_term)

    work = paths.WORK_DIR / job_id
    work.mkdir(parents=True, exist_ok=True)
    write_job(job_id, status="running", stage="reference", mode=args.mode,
              reference=args.reference, chat_id=chat_id)

    try:
        free_comfyui()
        available = mem_available_gb()
        if available is not None and available < MIN_FREE_GB:
            raise RuntimeError(f"지금 메모리가 모자라 ({available:.0f}GB 남음). 잠시 뒤 다시 불러 줘.")

        source = fetch_reference(args.reference, work)
        wav = to_reference_wav(source, work)

        stage("transcribe")
        score_dir = transcribe(wav, work)
        score_abc = (score_dir / "score.abc").read_text(encoding="utf-8")
        key_lab = ""
        if (score_dir / "key.lab").is_file():
            key_lab = (score_dir / "key.lab").read_text(encoding="utf-8")
        facts = header_facts(score_abc, key_lab)

        stage("describe")
        described = describe(wav, work) if args.mode == "style" else ""

        stage("generate")
        request = {
            "id": job_id,
            "style": style_text(args.style, described, facts),
            "lyrics": args.lyrics or "",
            "seed": args.seed,
        }
        # `style` borrows mood and instrumentation and lets YuE2 compose; `cover`
        # hands it the reference's own melody, which it uses verbatim -- the abc
        # slot replaces the plan rather than informing it, so a transcription
        # error becomes the song.
        if args.mode == "cover":
            abc_file, cot = score_dir / "score.abc", "melody"
        else:
            abc_file, cot = None, "full"
        request["cot"] = cot
        flac = run_yue2(request, abc_file, cot, work / "out")

        stage("encode")
        outbox.mkdir(parents=True, exist_ok=True)
        mp3 = to_mp3(flac, outbox / f"yue2_{int(time.time() * 1000)}.mp3", paths.max_bytes())
        prune(outbox)

        write_job(job_id, status="done", stage="done", audio=str(mp3),
                  bytes=mp3.stat().st_size, style=request["style"], cot=cot,
                  score=str(score_dir / "score.abc"), facts=facts,
                  described=bool(described))
        if mp3.stat().st_size > paths.max_bytes():
            say(f"곡은 만들었는데 파일이 너무 커서 카톡으로 못 보내 ({mp3.stat().st_size // (1024*1024)}MB). "
                f"경로: {mp3}")
        else:
            say(f"[[file: {mp3}]]\n{paths.caption_for()}")
        return 0
    except Exception as exc:  # noqa: BLE001 - every failure has to reach the room
        write_job(job_id, status="error", error=str(exc))
        say(f"노래 만들다 실패했어: {str(exc)[:300]}")
        return 1
    finally:
        if not args.keep_work:
            shutil.rmtree(work / "out", ignore_errors=True)


def demo() -> None:
    """Self-check for the two pure functions: what gets measured, and what is said."""
    abc = "X:1\nM:4/4\nL:1/16\nQ:1/4=83\nK:C\n% verse\n"
    facts = header_facts(abc, "0.0\t58.4\tC:major\n")
    assert facts == {"bpm": 83, "abc_key": "C", "key": "C major"}, facts
    # No key.lab (SheetSage2 can omit it): the ABC key survives, the spoken one does not.
    assert header_facts(abc) == {"bpm": 83, "abc_key": "C"}
    assert header_facts("X:1\n") == {}

    report = (
        "# describe_music_moss - model MOSS\n"
        "# torch 2.9.1+cu128 - load 94s - gpu mem 16.9 GiB\n"
        "\n## prompt 1   (gen 26.2s, peak gpu 17.3 GiB)\n"
        "\n> Please give a detailed musical description. Do not name any artist.\n"
        "\nA contemporary indie pop ballad with a resonant grand piano.\n"
        "\n## prompt 2   (gen 15.9s)\n"
        "\n> Describe the lead vocal only.\n"
        "\nThe lead vocal is a female singer, intimate and controlled.\n"
        "\n## prompt 3   (gen 14.1s)\n"
        "\n> Give the song structure with timestamps.\n"
        "\n[verse1 11.64s-34.92s]\nNeon fades along the lane.\n")
    prose = moss_prose(report)
    # The report's scaffolding is the whole point of this function.
    for leaked in ("torch", "gpu mem", "Please give", "Describe the lead", "prompt 1"):
        assert leaked not in prose, (leaked, prose)
    assert "indie pop ballad" in prose and "female singer" in prose
    # Prompt 3 quotes the reference's own lyrics; they must not reach the slot.
    assert "Neon fades" not in prose, prose
    assert moss_prose("") == "" and moss_prose("# only metadata\n") == ""

    # Truncation lands on a sentence end rather than mid-word.
    assert clip_sentences("aa. bb. cc.", 99) == "aa. bb. cc."
    assert clip_sentences("one two three. four five six. seven", 30) == "one two three. four five six."
    # No sentence end near enough to be worth keeping: fall back to a word boundary.
    assert clip_sentences("averyveryverylongsingleclause continues onward", 30) == "averyveryverylongsingleclause"
    assert not clip_sentences("one two three. four five six. seven", 30).endswith(" ")

    text = style_text("warm jazz trio", report, facts)
    # The caller's brief is last: it is the instruction, the reference is context.
    assert text.endswith("warm jazz trio"), text
    assert "83 BPM" in text and "C major" in text and "indie pop ballad" in text
    assert ".." not in text, text
    # Measurement still lands when the caller said nothing and MOSS was skipped.
    assert style_text("", "", facts) == "83 BPM, C major"
    # Nothing measured, nothing heard: the caller's words are all there is.
    assert style_text("lofi", "", {}) == "lofi"
    assert len(style_text("x" * 2000, report, facts)) <= 1200

    assert looks_like_url("https://youtu.be/x") and not looks_like_url("/tmp/a.mp3")
    print("worker.py self-check ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make a song from a reference recording")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--reference", required=True, help="local path or URL")
    parser.add_argument("--mode", choices=("style", "cover"), default="style")
    parser.add_argument("--style", default="", help="the caller's production brief")
    parser.add_argument("--lyrics", default="")
    parser.add_argument("--seed", type=int, default=831001)
    parser.add_argument("--chat-id", type=int, default=None)
    parser.add_argument("--send-bin", default=None)
    parser.add_argument("--outbox", default=None)
    parser.add_argument("--no-send", action="store_true", help="run the pipeline, say nothing")
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        demo()
        return 0
    return run(args)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--selftest":
        demo()
    else:
        raise SystemExit(main())
