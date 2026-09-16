"""Wait out a ComfyUI job the chat turn could not, then hand the result to the room.

Renders and songs alike: the only difference is the fence word the daemon reads
to pick a transport, and the noun a failure line calls the thing.

Spawned detached by the provider when a render does not finish inside the turn's
window. It must outlive the hermes process that started it, so it takes plain
argv rather than anything inherited, and it always says something -- a room that
was told "만들고 있어" and then hears nothing is the one failure mode that matters.

Not a service: one process per job, exits when the job does.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import comfy  # noqa: E402


def send(send_bin: str, chat_id: int, text: str) -> None:
    """One message into the room through the daemon's own outside-caller entry point.

    Deliberately not a second send path: `--send-to` already owns the transport,
    the bot prefix and the image/file fence.
    """
    subprocess.run([sys.executable, send_bin, "--send-to", str(chat_id), "--text", text],
                   stdin=subprocess.DEVNULL, timeout=180, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deliver a finished ComfyUI render to a chat room")
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--node", required=True, help="Save* node id to read outputs from")
    parser.add_argument("--chat-id", type=int, required=True)
    parser.add_argument("--send-bin", required=True, help="path to kakao_ai_chat.py")
    parser.add_argument("--outbox", required=True, help="fenced directory the room can send from")
    parser.add_argument("--url", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--max-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--caption", default="다 됐어")
    # Images leave through Iris /reply, everything else through the share intent;
    # the daemon picks the transport off the fence word, so a song sent as
    # `[[image: ...]]` is refused at the fence with "이미지가 아니다".
    parser.add_argument("--fence", default="image", choices=("image", "file"))
    # Used in failure lines only, and every one of them is worded to take no
    # Korean particle after it -- "노래이" would be the alternative.
    parser.add_argument("--noun", default="그림", help="what to call it when it fails")
    args = parser.parse_args(argv)

    client = comfy.ComfyUI(base_url=args.url, output_root=args.output_root)
    try:
        entry = client.poll(args.prompt_id, timeout=args.timeout, interval=5.0)
    except comfy.ComfyError as exc:
        send(args.send_bin, args.chat_id, f"{args.noun} 만들다 실패했어: {exc}"[:400])
        return 1
    except Exception as exc:  # noqa: BLE001 - the room must hear something either way
        send(args.send_bin, args.chat_id, f"{args.noun} 만들다 실패했어: {exc}"[:400])
        return 1

    if entry is None:
        send(args.send_bin, args.chat_id,
             f"{int(args.timeout)}초 안에 안 끝나서 {args.noun} 만들다 포기했어 (prompt_id={args.prompt_id})")
        return 1

    try:
        rendered = client.output_paths(entry, args.node)[0]
        handed = comfy.hand_over(rendered, Path(args.outbox), args.max_bytes)
        comfy.prune(Path(args.outbox))
    except Exception as exc:  # noqa: BLE001
        send(args.send_bin, args.chat_id, f"{args.noun} 다 됐는데 파일을 못 옮겼어: {exc}"[:400])
        return 1

    send(args.send_bin, args.chat_id, f"[[{args.fence}: {handed}]]\n{args.caption}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
