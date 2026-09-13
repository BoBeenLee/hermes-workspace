---
type: Runbook
title: Iris On DGX
description: Running the Iris KakaoTalk DB observer inside the DGX redroid container — the two things that block startup, the read-path verification, and why the send path stays inert.
resource: repo://hermes-workspace/knowledge/runbooks/iris-on-dgx.md
tags: [kakaotalk, iris, dgx-spark, redroid, android]
timestamp: 2026-09-13T21:05:00+09:00
---

# Iris On DGX

[Iris](https://github.com/dolidolih/Iris) v0.32 is the Android counterpart of the Mac's
`kakaocli` (read) and `kmsg` (send). Verified on 2026-09-13 inside the container from
[DGX Android Container](dgx-android-container.md): **the read path works end to end; the send
path is deliberately left inert.**

Container prerequisites are in that runbook. This one covers Iris only.

## Install

Take the release from the project's own GitHub release and verify it. v0.32 `Iris.apk` is
`6ca57924bbc44d1dc603a7f533df9a8c` (the published `.MD5` is uppercase — compare case-insensitively).

```bash
scp Iris.apk dgx:~/redroid-poc/data64/apk/      # /data is the bind mount
docker exec redroid-poc sh -c 'cp /data/apk/Iris.apk /data/local/tmp/Iris.apk'
```

`iris_control` from the release requires `adb`, which the DGX does not have. Its actual work is
just `CLASSPATH=<apk> app_process / party.qwer.iris.Main` as root, which `docker exec` can do —
with one catch below.

## Blocker 1: `docker exec` Has No Android Environment

`docker exec` gives a bare environment (`PATH=/usr/local/sbin:…:/bin`, `HOME=/`) with no
`ANDROID_ROOT`, `ANDROID_DATA`, or `BOOTCLASSPATH`. `app_process` then starts the runtime,
prints nothing, and exits — no exception, no logcat entry. `adb shell` works because it supplies
that environment.

Replicate it from a running Android process:

```sh
#!/system/bin/sh
SP=$(pidof system_server)
tr "\0" "\n" < /proc/$SP/environ > /data/local/tmp/aenv.txt
while IFS= read -r line; do
  case "$line" in
    ANDROID_SOCKET_*) continue ;;   # inherited fds, must not be re-exported
    *=*) export "$line" ;;
  esac
done < /data/local/tmp/aenv.txt
export CLASSPATH=/data/local/tmp/Iris.apk
exec app_process / party.qwer.iris.Main
```

Android's `sh` has no process substitution, so `< <(...)` fails silently. Use the temp file.

Run it detached: `docker exec -d redroid-poc sh -c 'sh /data/apk/iris_start.sh > /data/local/tmp/iris.log 2>&1'`.

## Blocker 2: `NotificationReferer` Is Missing

With the environment fixed, Iris fails with:

```text
Iris Error
java.lang.Exception: failed to extract referer from data
	at party.qwer.iris.Main$Companion.readNotificationReferer(Main.kt:58)
```

`readNotificationReferer()` pulls `<string name="NotificationReferer">` out of
`shared_prefs/KakaoTalk.hw.perferences.xml`. On a freshly signed-in companion device that key
does not exist — KakaoTalk writes it only after handling a notification, and **a message you
send yourself does not raise one**. Confirmed absent from the whole app data directory.

`Main.kt:18` calls this **first**, so the exception kills the DB observer too, even though
`notificationReferer` is used only by `Replier.sendMessage`/`sendPhoto` in `IrisServer.kt:177`.
The read path never needs it.

Inject a placeholder rather than rebuilding the APK:

```sh
F=/data/data/com.kakao.talk/shared_prefs/KakaoTalk.hw.perferences.xml
cp $F $F.bak-iris-poc
sed -i 's#</map>#    <string name="NotificationReferer">iris-poc-placeholder</string>\n</map>#' $F
```

A bogus value keeps the send path inert, which is a useful safety default while validating
reads — nothing can leave the container by accident.

**KakaoTalk overwrites the placeholder with a real referer the moment it handles an incoming
notification from another party** (a ~20-character token). Version 26.7.2 still uses this key, so
the placeholder is a bootstrap, not a permanent patch. Once a real value lands, **restart Iris** —
`readNotificationReferer()` runs once at startup and the process keeps the old value in memory.

`PathUtils.getAppPath()` logging `/data_mirror/data_ce/null/0/com.kakao.talk/` is **not** a bug —
`null` is the internal-storage volume UUID and the path resolves to the same inode as
`/data/data/com.kakao.talk/`.

## Verified Read Path

Iris writes `/data/local/tmp/config.json`, which is reachable from the host at
`~/redroid-poc/data64/local/tmp/config.json` because `/data` is the bind mount. Point
`webServerEndpoint` at a listener on the docker bridge gateway (`172.17.0.1`) and keep it off
any external interface.

| Check | Result |
| --- | --- |
| Startup | `Bot user_id is detected: 135397747`, `DBObserver started`, `Initial lastLogId: 251` |
| `GET /dashboard` (via `172.17.0.2:3000`) | 200 |
| `POST /query` `select count(*) from chat_logs` | 251, then 252 after one new message |
| Live forward | `Detected 1 new log(s)` → POST to the listener → `HTTP Response Code: 200` |
| **Decryption** | payload carried `"message":"123"` in cleartext for a row whose `v` field reports `"enc":31` |

That is structural parity with `kakaocli`: encrypted DB in, structured decrypted events out.

## Verified Send Path

Once a real referer was in place and Iris restarted, `POST /reply` with
`{"type":"text","room":"<chatId>","data":"..."}` delivered a message that appeared in KakaoTalk,
reached the server, and came back through the observer loop as a new `chat_logs` row
(253 → 254). Confirmed on screen in the target room.

`Replier.sendMessageInternal` does this by firing an intent at
`com.kakao.talk/.notification.NotificationActionService` with action
`com.kakao.talk.notification.REPLY_MESSAGE`, carrying `noti_referer`, `chat_id`, and the text in
a RemoteInput results bundle — it is the notification inline-reply path, which is why the referer
gates it.

**`/reply` returning `{"success":true}` does not mean the message was sent.** It only confirms
Iris queued the intent; with a bogus referer it returns the same thing and nothing leaves. Verify
against `chat_logs` or the observer loop-back, never against the response body.

## Not Verified

- **Long-run stability**, reconnect behaviour, and whether an injected or stale referer survives KakaoTalk rewriting `shared_prefs`. Since the referer is issued per notification handling, expect it to rotate and plan an Iris restart around that.
- Whether upstream redroid breaking on a kernel update takes this stack with it.

## Next: Porting The Policy Engine

Read and write both work, so the remaining gap between this and the Mac stack is
`scripts/hermes/messenger_assistant.py` — the fail-closed controller described in
[Jarvis Messenger Assistant](jarvis-messenger-assistant.md). **Deferred to a separate session
(2026-09-13).**

The port is not a transport swap. The controller's guards are written against the macOS
adapter's evidence, and the Android side supplies different fields:

| Mac guard | Evidence it uses | Android equivalent |
| --- | --- | --- |
| 1:1 room check | `NTUser.directChatId` plus `userType` classified `human` | not the same schema; needs a rule derived from `chat_rooms`/`chat_logs` |
| read-state trigger | KakaoTalk-for-Mac read flags | `chat_logs.v` carries `isMine`, `pushAlert`, `enc` |
| send binding | one no-send MCP call binding read-side chat id to the kmsg send id | `chat_id` is the same key on both sides, so this stage may collapse |
| adapter transport | stdio MCP server, one tool call per action | HTTP `/reply` and `/query`, or the WebSocket feed |

Two traps already established that the port must respect: `/reply` reporting success for a queued
intent rather than a delivered message, and the referer needing an Iris restart when it rotates.

Do not start this until the device-slot decision in
[KakaoTalk Control Portability](kakaotalk-control-portability.md) is settled — the Mac client
and this container cannot both hold the companion slot.
