#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request


def load_env(path):
    env = {}
    for line in pathlib.Path(path).read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("channel_id")
    parser.add_argument("message_id")
    parser.add_argument("limit")
    parser.add_argument(
        "--env-path",
        default=None,
        help="Path to Hermes .env. Defaults to $HERMES_ENV_PATH or $HERMES_REMOTE_HOME/.hermes/.env or $HOME/.hermes/.env.",
    )
    args = parser.parse_args()

    home = pathlib.Path(os.environ.get("HERMES_REMOTE_HOME") or os.environ.get("HOME") or "~").expanduser()
    env_path = args.env_path or os.environ.get("HERMES_ENV_PATH") or str(home / ".hermes" / ".env")
    channel_id, message_id, limit = args.channel_id, args.message_id, args.limit
    env = load_env(env_path)
    token = env.get("DISCORD_BOT_TOKEN", "").strip()
    print("token_configured:", bool(token))
    if not token:
        return 1

    url = (
        f"https://discord.com/api/v10/channels/{channel_id}/messages?"
        + urllib.parse.urlencode({"around": message_id, "limit": limit})
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "HermesIssue43/1.0",
        },
    )

    try:
        raw = urllib.request.urlopen(request, timeout=20).read().decode("utf-8")
        messages = json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print("http_ok: false")
        print("status:", exc.code)
        print("body:", body[:1000])
        return 1

    print("http_ok: true")
    print("count:", len(messages))
    for message in sorted(messages, key=lambda item: item.get("id", "")):
        author = message.get("author", {})
        print("---MESSAGE---")
        print("id:", message.get("id"))
        print("timestamp:", message.get("timestamp"))
        print(
            "author:",
            author.get("global_name") or author.get("username") or "",
            "bot=" + str(author.get("bot", False)),
        )
        print("content:", (message.get("content") or "")[:4000].replace("\r", ""))
        if message.get("attachments"):
            print("attachments:", json.dumps(message["attachments"], ensure_ascii=False)[:1200])
        if message.get("embeds"):
            compact = [
                {key: embed.get(key) for key in ["title", "description", "url", "type"]}
                for embed in message["embeds"]
            ]
            print("embeds:", json.dumps(compact, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
