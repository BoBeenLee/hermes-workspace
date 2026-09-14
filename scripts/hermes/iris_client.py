#!/usr/bin/env python3
"""Iris HTTP/WebSocket client - the Linux counterpart of kakaocli + kmsg.

Iris runs inside the redroid Android container and exposes KakaoTalk's own
SQLite database over HTTP. It replaces two macOS binaries at once:

    kakaocli query <sql>   ->  POST /query
    kmsg send --chat-id    ->  POST /reply

Two things about it decide how callers must be written.

**`/reply` returning success does not mean the message was sent.** Iris only
confirms it queued an Android intent; with a stale `NotificationReferer` it
returns the same payload and nothing leaves the device. Verify against
`chat_logs`, never against the response body.

**`/query` decrypts `message` and `attachment` only when the SELECT also asks
for `user_id` and `v`.** Iris feeds those two to `KakaoDecrypt.decrypt(enc,
ciphertext, user_id)` - `v` carries the `enc` type, `user_id` seeds the key
salt. Leave either out and the column comes back as base64 ciphertext with no
error and no warning, which reads exactly like working code. `require_columns`
below turns that into a refusal.

**`/query` reaches three databases, not one.** `pragma_database_list` answers
`db1`=KakaoTalk.db (`chat_logs`, `chat_rooms`), `db2`=KakaoTalk2.db
(`open_chat_member`, `open_profile`, `open_link`) and `db3`=multi_profile_database.db.
Unqualified names resolve across all three, so `FROM open_chat_member` works, but
`sqlite_master` does not: it is per schema, and `main` holds nothing but
`android_metadata`. Ask `db2.sqlite_master` or the DB reads as empty.

**No `friends` table exists in any of them**, so a display name for a member of a
DirectChat or MultiChat cannot be read at all - those names arrive on the `/ws` push
feed and nowhere else. Only open chats have a member table.

**The push feed carries a whole decrypted row, not a notification.** Each frame is
`{msg, room, sender, json: {...chat_logs row...}}` with `message` and `attachment`
already in the clear. That makes `/ws` the natural read path for live messages and
leaves `/query` for history lookups by id.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import pathlib
from pathlib import Path

DEFAULT_BASE_URL = "http://172.17.0.2:3000"
DEFAULT_TIMEOUT_SECONDS = 20.0


class IrisError(RuntimeError):
    pass


class IrisClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise IrisError(f"Iris {path} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise IrisError(f"Iris {path} unreachable: {exc.reason}") from exc
        try:
            return json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise IrisError(f"Iris {path} returned non-JSON: {body[:200]}") from exc

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/dashboard", timeout=self.timeout) as r:
                return r.status == 200
        except OSError:
            return False

    def query(self, sql: str) -> list[dict]:
        payload = self._post("/query", {"query": sql})
        if payload.get("status") is False:
            raise IrisError(f"Iris query rejected: {str(payload.get('message'))[:300]}")
        data = payload.get("data")
        return data if isinstance(data, list) else []

    def query_rows(self, sql: str, columns: tuple[str, ...]) -> list[list]:
        """Positional rows, so callers can keep using a zip-into-dict helper.

        Iris answers with dicts keyed by the SELECT alias; everything upstream of
        this was written against kakaocli's positional output.
        """
        require_decryptable(sql)
        return [[row.get(name) for name in columns] for row in self.query(sql)]

    def reply(self, chat_id, text: str, thread_id=None) -> dict:
        """Queue one text message. Success here is not delivery - read it back.

        `thread_id` is an open-chat 댓글 root, and it is the ONLY reply form Iris can
        send. KakaoTalk's ordinary 답장 is a `type=26` row carrying `src_logId` in its
        attachment, and that is unreachable: `Replier.sendMessageInternal` fires a
        NotificationActionService REPLY_MESSAGE intent with nowhere to put one. Adding
        `src_logId` to this body does not fail on that - kotlinx rejects the whole
        request on the unknown key first, which makes it look like a body-shape problem
        when it is not.

        The value is `chat_logs.id`, not `_id`. Measured: an `_id` is accepted and
        stored verbatim, producing a 댓글 rooted at a message that does not exist.
        """
        body = {"type": "text", "room": str(chat_id), "data": text}
        if thread_id is not None:
            body["threadId"] = int(thread_id)
        payload = self._post("/reply", body)
        if payload.get("success") is not True:
            raise IrisError(f"Iris reply refused: {str(payload)[:300]}")
        return payload

    def decrypt(self, enc, ciphertext: str, user_id) -> str | None:
        """One KakaoTalk field in the clear, or None when Iris cannot unlock it.

        `/query` only decrypts `message` and `attachment`. Every other encrypted
        column - `open_chat_member.nickname` above all - comes back as base64 and has
        to come through here. The salt is the *viewer's* user id, not the row's.
        """
        try:
            payload = self._post(
                "/decrypt",
                {"enc": int(enc or 0), "b64_ciphertext": ciphertext, "user_id": int(user_id)},
            )
        except IrisError:
            return None
        plain = payload.get("plain_text")
        return plain if isinstance(plain, str) and plain else None

    def reply_images(self, chat_id, images: list[str], thread_id=None) -> dict:
        """Queue one or more base64 images. Queued is not delivered - read it back.

        **`thread_id` is accepted and dropped.** A photo row cannot be a 댓글:
        `IrisServer.kt` reads `threadId` for every type but hands it only to
        `ReplyType.TEXT`, and `Replier.sendPhoto`/`sendMultiplePhotos` have no such
        parameter to hand it to. The two paths are different intents - text goes out
        as a NotificationActionService REPLY_MESSAGE carrying `thread_id` and
        `is_chat_thread_notification`, photos as an ACTION_SEND_MULTIPLE share, which
        has no slot for either. Measured 2026-09-14: a threaded caption and its photo
        arrived one second apart, the caption with `thread_id`, the photo with NULL.
        It is still sent because it costs nothing and upstream may wire it up; the
        caption beside the photo is what carries the thread today.

        `file` and `link` are not options: ReplyType is a three-entry enum, so the
        request body fails to deserialize - as does any other unknown type. Arbitrary
        files still reach KakaoTalk, just not through Iris: an ACTION_SEND intent with
        `-t application/octet-stream` does it. See knowledge/runbooks/iris-on-dgx.md.
        """
        if not images:
            return {}
        body = ({"type": "image", "data": images[0]} if len(images) == 1
                else {"type": "image_multiple", "data": images})
        if thread_id is not None:
            body["threadId"] = int(thread_id)
        payload = self._post("/reply", {"room": str(chat_id), **body})
        if payload.get("success") is not True:
            raise IrisError(f"Iris image reply refused: {str(payload)[:300]}")
        return payload

    def watch(self, sink, cache: dict, stop: threading.Event | None = None) -> threading.Thread:
        """Feed live rows to `sink` and names to `cache`, in a daemon thread.

        `sink` takes one row dict per pushed message. Only live messages arrive
        here: a consumer that also needs history keeps using `query` for that.
        """
        thread = threading.Thread(
            target=self._watch_loop, args=(sink, cache, stop), name="iris-watch", daemon=True
        )
        thread.start()
        return thread

    def _watch_loop(self, sink, cache: dict, stop: threading.Event | None) -> None:
        url = self.base_url.replace("http://", "ws://", 1).replace("https://", "wss://", 1) + "/ws"
        while stop is None or not stop.is_set():
            try:
                import websockets.sync.client as ws_client

                with ws_client.connect(url, open_timeout=10) as socket:
                    while stop is None or not stop.is_set():
                        try:
                            frame = socket.recv(timeout=30)
                        except TimeoutError:
                            # A quiet room is not a dead feed. Letting this reach the
                            # reconnect below tore the socket down every 40s and lost
                            # whatever arrived during the 5s sleep - measured, not
                            # theoretical. A real death arrives as ConnectionClosed,
                            # because the library runs its own keepalive ping.
                            continue
                        record_names(cache, frame)
                        row = row_from_frame(frame)
                        if row is not None and sink is not None:
                            sink(row)
            except Exception:
                # A dropped feed must never take the daemon down. Reconnecting loses
                # only what arrived while it was down, which `query` can recover by id.
                time.sleep(5)


# (ciphertext columns, then one group per input the SELECT must also name).
DECRYPT_RULES = (
    (("message", "attachment"), ("user_id",), ("v",)),
    # open_chat_member and open_profile hide a nickname and three picture URLs
    # behind the same scheme, with the enc type in `enc` on the first table and
    # `v` on the second. `profile_image_url` covers the `full_`/`original_`
    # columns too, since it is a substring of both.
    (("nickname", "profile_image_url"), ("user_id",), ("enc", "v")),
)


def require_decryptable(sql: str) -> None:
    """Refuse a SELECT that would silently hand back ciphertext.

    Asking for an encrypted column without the inputs Iris decrypts it with is not
    an error to Iris - it just returns base64. Catching it here costs one check and
    saves a debugging session against data that looks corrupt rather than locked.
    """
    lowered = sql.lower()
    if not lowered.lstrip().startswith("select"):
        return
    body = lowered.split(" from ", 1)[0]
    for columns, *groups in DECRYPT_RULES:
        wanted = [c for c in columns if c in body]
        if not wanted:
            continue
        missing = [" or ".join(group) for group in groups if not any(c in body for c in group)]
        if missing:
            raise IrisError(
                f"select asks for {', '.join(wanted)} but omits {', '.join(missing)}; "
                "Iris would return ciphertext, not an error."
            )


PUSH_ROW_KEYS = {
    "id": "log_id",
    "chat_id": "chat_id",
    "thread_id": "thread_id",
    "user_id": "author_id",
    "type": "type",
    "message": "message",
    "attachment": "attachment",
    "created_at": "sent_at",
    "v": "v",
}


def row_from_frame(raw):
    """One push frame to one row dict, or None when the frame is not a message.

    The nested `json` object is the chat_logs row Iris already decrypted, so this
    is a rename rather than a parse. `sender` rides along because it exists nowhere
    else reachable.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    source = payload.get("json")
    if not isinstance(source, dict) or source.get("id") in (None, ""):
        return None
    row = {internal: source.get(key) for key, internal in PUSH_ROW_KEYS.items()}
    for key in ("log_id", "chat_id", "author_id", "type", "sent_at"):
        try:
            row[key] = int(row.get(key) or 0)
        except (TypeError, ValueError):
            row[key] = 0
    sender = payload.get("sender")
    row["sender_name"] = sender.strip() if isinstance(sender, str) and sender.strip() else None
    return row


def record_names(cache: dict, raw) -> None:
    """Pull user_id -> sender out of one push frame. Tolerates shape drift."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    sender = payload.get("sender")
    raw_row = payload.get("raw") if isinstance(payload.get("raw"), dict) else payload
    user_id = raw_row.get("user_id") if isinstance(raw_row, dict) else None
    if user_id in (None, "") or not isinstance(sender, str) or not sender.strip():
        return
    cache[str(user_id)] = sender.strip()


# --------------------------------------------------------------------------
# files: not Iris at all
# --------------------------------------------------------------------------

# Where the staged file has to sit. The share Uri is a bare `file://`, so
# KakaoTalk reads it as itself and only its own external dir is readable.
KAKAO_FILES_DIR = "/sdcard/Android/data/com.kakao.talk/files"
DEFAULT_CONTAINER = "redroid-poc"
SHARE_ACTIVITY = "com.kakao.talk/.activity.RecentExcludeIntentFilterActivity"
# NEW_TASK | CLEAR_TOP, copied from Replier.sendMultiplePhotosInternal.
SHARE_FLAGS = "335544320"
DOCKER_TIMEOUT_SECONDS = 120.0

# KakaoTalk branches on the mime it is handed. `video/mp4` arrives as a playable
# video row (`chat_logs.type` 3, with w/h/duration), everything else as a file row
# (type 18). Only `.mp4` is mapped because only `.mp4` was measured against the
# live app; other video suffixes still arrive, just as files.
#
# Never widen this with `mimetypes.guess_type`. It answers `text/plain` for `.txt`,
# and KakaoTalk reads `text/*` as a text share - it looks for EXTRA_TEXT and drops
# the file with no error, no picker and no logcat line.
SHARE_MIMES = {".mp4": "video/mp4"}
DEFAULT_SHARE_MIME = "application/octet-stream"


def safe_device_name(name: str) -> str:
    """A file name that is safe as an argv path segment and still readable in the room.

    KakaoTalk shows this name and takes the extension from it, so it is worth
    keeping rather than replacing with a uuid. Hangul stays; `..` and separators
    do not, which is what keeps a crafted name inside KAKAO_FILES_DIR.
    """
    cleaned = re.sub(r"[^0-9A-Za-z\uac00-\ud7a3._-]", "_", name).lstrip(".-")
    return cleaned[:80] or "file"


def share_mime(path: Path) -> str:
    """The mime to hand KakaoTalk, which decides whether this is a video or a file."""
    return SHARE_MIMES.get(path.suffix.lower(), DEFAULT_SHARE_MIME)


def send_file(chat_id, path: Path, container: str = DEFAULT_CONTAINER) -> str:
    """Put one arbitrary file in a room. Returns the name KakaoTalk will show.

    This does not go through Iris. `/reply`'s ReplyType is a three-entry enum, so
    `file` fails to deserialize - and always did, in every release. KakaoTalk's own
    share intent takes the file instead, and `am` may fire it because Iris's own
    hidden-API caller name falls back to "com.android.shell" anyway.

    **The mime must not be `text/*`** - see SHARE_MIMES for why. `.mp4` is the one
    suffix that earns a real type, because a video row plays inline where a file row
    only downloads. Photos keep their own path (`reply_images`), which is what makes
    them arrive as photos rather than as attachments.

    Queued is not delivered, same as `/reply`: `am` prints its intent either way.
    Read `chat_logs` back - a delivered file is `type = 18`, a video `type = 3`.
    A video lands noticeably later than a file: KakaoTalk transcodes it first.
    """
    name = safe_device_name(path.name)
    target = f"{KAKAO_FILES_DIR}/{name}"
    # argv all the way down, never `sh -c`: the name reaches the device unquoted.
    _docker(["cp", str(path), f"{container}:/data/local/tmp/{name}"])
    _docker(["exec", container, "/system/bin/mv", f"/data/local/tmp/{name}", target])
    _docker(["exec", container, "/system/bin/chmod", "644", target])
    _docker(["exec", container, "/system/bin/am", "start",
             "-a", "android.intent.action.SEND",
             "-t", share_mime(path),
             "--eu", "android.intent.extra.STREAM", f"file://{target}",
             "--el", "key_id", str(chat_id),
             "--ei", "key_type", "1",
             "--ez", "key_from_direct_share", "true",
             "-f", SHARE_FLAGS,
             "-n", SHARE_ACTIVITY])
    # ponytail: the staged copy is left behind, exactly as Iris leaves its photos
    # there. Deleting it would race KakaoTalk's upload, which is asynchronous.
    return name


# Where the in-app Frida hook looks for the "which thread does the next media send
# belong to" hint (see frida/iris_thread.js). Single file, consume-once by mtime on the
# hook side: the hook runs as the kakao uid and cannot delete a root-owned file here, so
# it remembers the last mtime it used instead. dir is 771 and root writes the file
# world-readable, so the kakao uid can read it. See knowledge/runbooks/iris-on-dgx.md.
HINT_FILE = "/data/local/tmp/iris_thread_pending"


def write_thread_hint(chat_id, thread_id, container: str = DEFAULT_CONTAINER) -> None:
    """Signal the in-app hook which thread the next media send belongs to.

    Photo and file rows cannot carry a threadId through Iris - KakaoTalk builds the share
    as ChatSendingLog.b(..., threadId=null) and drops anything we pass. The Frida hook
    fills those two args on the next media build after this file is refreshed. Written
    only when there IS a thread to hang off; a None thread_id writes nothing, so a later
    non-thread send (a cron result) inherits no fresh hint - the hook ignores a hint it
    has already consumed or one older than its TTL.

    docker exec + printf, not docker cp: cp fails on this container's read-only /dev
    binds, and the sole interpolated value is int(thread_id), so the one sh -c that the
    redirect needs has no injection surface. chat_id is kept for the call site and logs;
    the hint is a single file, not keyed by room (Frida marshals the long chat_id
    lossily, and the bot serialises media sends), so it is deliberately unused here.
    """
    if thread_id is None:
        return
    _docker(["exec", container, "/system/bin/sh", "-c",
             "printf %s " + str(int(thread_id)) + " > " + HINT_FILE + "; /system/bin/chmod 644 " + HINT_FILE])


def _docker(args: list[str]) -> None:
    result = subprocess.run(
        ["docker", *args],
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=DOCKER_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise IrisError(f"docker {args[0]} failed ({result.returncode}): "
                        f"{(result.stderr or result.stdout).strip()[:300]}")


def demo() -> None:
    """Self-check for the parts that do not need a live Iris."""
    cache: dict = {}

    record_names(cache, json.dumps({"sender": "조창희", "raw": {"user_id": 993369}}))
    assert cache == {"993369": "조창희"}, cache

    # flat shape, no nested raw
    record_names(cache, json.dumps({"sender": "Iris", "user_id": "502396"}))
    assert cache["502396"] == "Iris", cache

    # frames with nothing usable must not raise or pollute the cache
    for junk in ("not json", json.dumps({"sender": "  "}), json.dumps([1, 2]),
                 json.dumps({"raw": {"user_id": 7}}), b'{"sender":"X","raw":{"user_id":8}}'):
        record_names(cache, junk)
    assert "7" not in cache and cache.get("8") == "X", cache

    assert IrisClient("http://example.invalid:3000/").base_url == "http://example.invalid:3000"

    # a push frame becomes a row, ints coerced, sender carried
    frame = json.dumps({
        "msg": "안녕", "room": "Iris", "sender": "조창희",
        "json": {"id": "3929034871365916673", "chat_id": "128426307555607",
                 "user_id": "135397747", "type": "1", "message": "안녕",
                 "attachment": "{}", "created_at": "1789308000", "v": "{}"},
    })
    row = row_from_frame(frame)
    assert row["log_id"] == 3929034871365916673, row
    assert row["chat_id"] == 128426307555607 and row["author_id"] == 135397747
    assert row["type"] == 1 and row["sent_at"] == 1789308000
    assert row["message"] == "안녕" and row["sender_name"] == "조창희"

    # frames that are not messages yield nothing rather than a half-row
    for junk in ("not json", json.dumps([1]), json.dumps({"sender": "x"}),
                 json.dumps({"json": {"chat_id": 1}}), json.dumps({"json": "no"})):
        assert row_from_frame(junk) is None, junk

    # a missing sender is not an error; the caller has a fallback label
    bare = row_from_frame(json.dumps({"json": {"id": 5, "message": "m"}}))
    assert bare["sender_name"] is None and bare["log_id"] == 5, bare

    # query_rows must project in the caller's column order, missing keys as None
    class FakeClient(IrisClient):
        def query(self, sql: str) -> list[dict]:
            return [{"b": 2, "a": 1}]

    assert FakeClient().query_rows("select 1", ("a", "b", "c")) == [[1, 2, None]]

    # the ciphertext trap: message/attachment without user_id and v
    for bad in ("select id, message from chat_logs where chat_id = 1",
                "select id, user_id, attachment from chat_logs",
                "SELECT id, v, MESSAGE FROM chat_logs"):
        try:
            require_decryptable(bad)
        except IrisError:
            pass
        else:
            raise AssertionError(f"should have refused: {bad}")
    # the same trap on the profile tables, where the enc type column is named `enc`
    for bad in ("select user_id, nickname from open_chat_member",
                "select nickname, enc from open_chat_member",
                "select full_profile_image_url from open_chat_member"):
        try:
            require_decryptable(bad)
        except IrisError:
            pass
        else:
            raise AssertionError(f"should have refused: {bad}")
    require_decryptable("select user_id, enc, nickname, profile_image_url from open_chat_member")
    require_decryptable("select user_id, v, nickname from open_profile")

    # both present, and columns that carry no ciphertext, are fine
    require_decryptable("select id, user_id, type, message, attachment, v from chat_logs")
    require_decryptable("select id, chat_id from chat_rooms")
    require_decryptable("select count(*) from chat_logs")
    # a where clause naming user_id must not count as selecting it
    try:
        require_decryptable("select id, message, v from chat_logs where user_id = 5")
    except IrisError:
        pass
    else:
        raise AssertionError("where-clause user_id must not satisfy the guard")

    # file names: hangul survives, traversal and separators do not
    assert safe_device_name("보고서 2026.pdf") == "보고서_2026.pdf"
    # traversal dies on the separator, not on the dots: what matters is that no
    # name can ever address a second path segment.
    assert safe_device_name("../../etc/passwd") == "_.._etc_passwd"
    assert safe_device_name("a b; rm -rf /.txt") == "a_b__rm_-rf__.txt"
    assert safe_device_name("...") == "file"
    assert safe_device_name("") == "file"
    assert "/" not in safe_device_name("x/y/z") and ".." not in safe_device_name("..a")

    # the mime decides video vs file, and `.txt` must never become text/plain
    assert share_mime(Path("clip.MP4")) == "video/mp4"
    assert share_mime(Path("a.txt")) == "application/octet-stream"
    assert share_mime(Path("a.pdf")) == "application/octet-stream"
    assert share_mime(Path("noext")) == "application/octet-stream"
    assert not any(m.startswith("text/") for m in SHARE_MIMES.values())

    # the thread hint: a set writes the int to the single pending file via one sh -c;
    # a None thread_id touches docker not at all (no stale hint for a non-thread send).
    global _docker
    real_docker, calls = _docker, []
    _docker = lambda args: calls.append(args)
    try:
        write_thread_hint(128426307555607, 3929500590731, container="c")
        assert len(calls) == 1 and calls[0][:4] == ["exec", "c", "/system/bin/sh", "-c"], calls
        assert "3929500590731" in calls[0][4], calls
        assert "/data/local/tmp/iris_thread_pending" in calls[0][4], calls
        calls.clear()
        write_thread_hint(128426307555607, None, container="c")
        assert calls == [], calls   # None writes nothing
    finally:
        _docker = real_docker

    print("iris_client demo ok")


if __name__ == "__main__":
    demo()
