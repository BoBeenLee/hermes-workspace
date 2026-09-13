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

**`/query` reaches KakaoTalk.db only.** `chat_logs`, `chat_rooms` and
`open_chat_member` are there; the `friends` table that maps a user id to a
display name lives in KakaoTalk2.db, which Iris does not attach. Sender names
therefore cannot be joined in SQL - they arrive on the `/ws` push feed, which
Iris resolves itself.

**The push feed carries a whole decrypted row, not a notification.** Each frame is
`{msg, room, sender, json: {...chat_logs row...}}` with `message` and `attachment`
already in the clear. That makes `/ws` the natural read path for live messages and
leaves `/query` for history lookups by id.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

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

    def reply(self, chat_id, text: str) -> dict:
        """Queue one text message. Success here is not delivery - read it back."""
        payload = self._post("/reply", {"type": "text", "room": str(chat_id), "data": text})
        if payload.get("success") is not True:
            raise IrisError(f"Iris reply refused: {str(payload)[:300]}")
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
                        frame = socket.recv(timeout=30)
                        record_names(cache, frame)
                        row = row_from_frame(frame)
                        if row is not None and sink is not None:
                            sink(row)
            except Exception:
                # A dropped feed must never take the daemon down. Reconnecting loses
                # only what arrived while it was down, which `query` can recover by id.
                time.sleep(5)


DECRYPT_INPUTS = ("user_id", "v")
ENCRYPTED_COLUMNS = ("message", "attachment")


def require_decryptable(sql: str) -> None:
    """Refuse a SELECT that would silently hand back ciphertext.

    Asking for `message` or `attachment` without `user_id` and `v` is not an
    error to Iris - it just returns base64. Catching it here costs one check and
    saves a debugging session against data that looks corrupt rather than locked.
    """
    lowered = sql.lower()
    if not lowered.lstrip().startswith("select"):
        return
    body = lowered.split(" from ", 1)[0]
    wanted = [c for c in ENCRYPTED_COLUMNS if c in body]
    if not wanted:
        return
    missing = [c for c in DECRYPT_INPUTS if c not in body]
    if missing:
        raise IrisError(
            f"select asks for {', '.join(wanted)} but omits {', '.join(missing)}; "
            "Iris would return ciphertext. Add both user_id and v to the column list."
        )


PUSH_ROW_KEYS = {
    "id": "log_id",
    "chat_id": "chat_id",
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

    print("iris_client demo ok")


if __name__ == "__main__":
    demo()
