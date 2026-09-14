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

The DGX AI Control app wraps this; see [DGX Android Container](dgx-android-container.md).

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

## Files: `/reply` Cannot, The Intent Behind It Can

`/reply` takes exactly three types. `ReplyType` is a Kotlin enum with three entries and
kotlinx.serialization rejects everything else in the request body, so `file`, `link` and a
nonsense `zzzz` all fail identically - it is not a file-specific refusal:

```
{"status":false,"message":"Failed to convert request body to class party.qwer.iris.model.ReplyRequest"}
```

Upstream `main` has the same three entries, and v0.32 (2026-06-28) is the latest release, so
there is no newer build to wait for and no undocumented fourth type. The `sendFile`/`FILE`
strings in the dex are Ktor symbols, not Iris features.

**But photos never went through `/reply`'s intent either.** `Replier.sendMultiplePhotosInternal`
fires a plain Android share intent, and KakaoTalk's receiving filter is not image-only:

```
com.kakao.talk/.activity.RecentExcludeIntentFilterActivity
  Action: SEND, SEND_MULTIPLE, SENDTO
  StaticType: application, audio, image, video, text
```

`AndroidHiddenApi` falls back to the calling package `"com.android.shell"` - exactly what the
container's `am` uses - so `am start` reproduces it with no APK rebuild. Verified 2026-09-14
against the MemoChat room: a PDF and a `.txt` both landed as `chat_logs.type = 18` with
`attachment.name`/`size`/`url`, headless, no picker and no tap.

```sh
D=/sdcard/Android/data/com.kakao.talk/files    # KakaoTalk's own dir, so u0_a79 can read it
cp <src> $D/<name>; chmod 644 $D/<name>
am start -a android.intent.action.SEND -t application/octet-stream \
  --eu android.intent.extra.STREAM file://$D/<name> \
  --el key_id <chatId> --ei key_type 1 --ez key_from_direct_share true \
  -f 335544320 -n com.kakao.talk/.activity.RecentExcludeIntentFilterActivity
```

Four things decide whether this works:

- **The mime decides which row you get.** `application/octet-stream` gives a file
  (`type = 18`); `video/mp4` gives a playable video (`type = 3`, carrying `w`/`h`/`d`
  and a thumbnail key). A video also lands noticeably later, because KakaoTalk
  transcodes it first - 12s was too early to see it, 37s was enough.
- **`-t text/plain` silently does nothing.** KakaoTalk reads that as a text share and looks for
  `EXTRA_TEXT`; a `.txt` handed over as `EXTRA_STREAM` is dropped with no error, no picker and no
  logcat complaint - the trampoline just forwards to `MainActivity` and the app sits there. Use
  `application/octet-stream` for anything that is not real media. This is the whole reason the
  first attempt looked like a hard refusal.
- **`ACTION_SEND`, not `ACTION_SEND_MULTIPLE`.** `am --eu` sets a single Uri; `SEND_MULTIPLE`
  wants an `ArrayList<Uri>`, which `am` cannot build. One file per call.
- **The file must live under `/sdcard/Android/data/com.kakao.talk/files`.** The Uri is a bare
  `file://`, so KakaoTalk reads it as itself. Elsewhere it is unreadable.
- **`am` is not the limit and neither is the referer.** The share path never touches
  `NotificationReferer`; only `/reply`'s text send does.

Delivery still has to be read back from `chat_logs` - `am start` prints `Starting: Intent {...}`
whether or not anything was sent, the same trap as `/reply`'s `{"success":true}`. KakaoTalk
stamps files with a 14-day expiry (`attachment.expire`), so this is not archival transport.

### Upstream Is Building This, Which Is When To Retire The Workaround

[Iris#129](https://github.com/dolidolih/Iris/pull/129) adds video and arbitrary files to
`/reply`. **Open, not merged** (checked 2026-09-14), so nothing to wait for yet - but read it
before touching this code, for two reasons.

First, it confirms the intent independently. Its `sendFileInternal` is the same
`ACTION_SEND` + `key_id`/`key_type`/`key_from_direct_share` + `NEW_TASK|CLEAR_TOP` we
reverse-engineered, with `type = mediaType` as the one variable. Upstream reaching the same
shape is the strongest evidence available that this is the supported path and not a trick.

Second, **it does not add a `file` ReplyType** - its `ReplyType.kt` change is a trailing
newline. Files arrive as a raw binary body on a separate route, `POST /reply?room=…&filename=…`
with the mime in `Content-Type`, streamed rather than base64'd so a large upload cannot OOM the
device. So "the enum has three entries" stays true even after it merges, and a client that
adopts it is writing a new call, not a new `type` value. Its cap is 300 MiB, which is the real
KakaoTalk ceiling; our own `attach_max_bytes` is a much lower policy choice, not a limit.

Adopting it means building an APK from an unmerged third-party branch and replacing the Iris
on the device that holds the companion slot. The `am` path costs no build and is already
verified, so the trade only becomes worth it once #129 is merged and released.

## `@멘션`: An Attachment, Not Text

Typing `@이보빈` into the message body sends the three characters and nothing else - no
highlight, no mention notification. The mention lives in `chat_logs.attachment` on an
ordinary `type = 1` row:

```json
{"mentions":[{"at":[1],"user_id":135397747,"len":3}]}
```

`/reply` has no slot for it: `ReplyType` carries a bare `data` string (same three-entry enum as
above; `strings` on Iris's dex finds no `mention` at all), and the text leaves as a
NotificationActionService REPLY_MESSAGE intent, which has nowhere to put an attachment. So this
is the Frida hook's job, exactly like media threading - see `frida/README.md`.

**`at` is the 1-based ordinal of the `@` CHARACTER, counting every `@` in the message.** Not a
character offset, not a word index. Measured 2026-09-15: `"x@y @이보빈 A"` needs `at=[2]`,
because the `@` in `x@y` takes ordinal 1. This is worth getting right because a wrong `at` is
not a no-op - the renderer takes the `@` you pointed at, eats `len` characters after it and
paints the resolved nickname over them, so the same message with `at=[1]` rendered as
`x@이보빈이보빈 A1`.

**`len` is the character count of the nickname**, which is how a nickname with a space works
(`@노래하는 춘식이`, `len` 8): the renderer consumes `len` chars, it never tokenises.

`scripts/hermes/iris_client.py:mentions_for` builds the list from a nickname → user_id map and
`write_mention_hint` hands it to the hook. Verified in 평일04 (`18415707579364567`), both as a
plain room message and inside a 댓글 - `threadId` and mentions are independent, one rides
`/reply`, the other the hook, and a single send carries both.

**Open chats only.** `user_id` here is an `open_chat_member.user_id`, and no table maps a name
to an id in a DirectChat or MultiChat - see "Where Sender Names Come From" below. The map itself
is the harder half: `open_chat_member` is a partial cache (평일04's link had zero rows in it),
so a room's roster may have to come off the `/ws` feed instead. `db2.open_profile` covers our
own per-link nickname, which is what the 평일04 test used.

## Not Verified

- **Long-run stability**, reconnect behaviour, and whether an injected or stale referer survives KakaoTalk rewriting `shared_prefs`. Since the referer is issued per notification handling, expect it to rotate and plan an Iris restart around that.
- Whether upstream redroid breaking on a kernel update takes this stack with it.

## The Decryption Rule `/query` Does Not Advertise

`/query` returns `message` and `attachment` **decrypted only when the SELECT also
asks for `user_id` and `v`.** Iris hands those to
`KakaoDecrypt.decrypt(enc, b64_ciphertext, user_id)` - `v` carries the `enc` type,
`user_id` seeds the key salt. Leave either column out and the value comes back as
base64 with HTTP 200, no error and no warning:

```
select id, chat_id, user_id, type, message, attachment, created_at
  -> 'WbZJz+ZPtR5iRhriGWj9kA=='
select id, chat_id, user_id, type, message, attachment, created_at, v
  -> '미사역팀은 내일 7시에 10번출구쪽 대로변으로 와주시면 됩니다.'
     attachment {"thumbnailUrl":"https://talk.kakaocdn.net/..."}
```

A `WHERE user_id = ...` does not count - the column has to be selected. This is
the single sharpest edge in the whole backend, because the failure mode is data
that looks corrupt rather than locked. `scripts/hermes/iris_client.py` refuses
such a SELECT instead of returning it.

`POST /decrypt` exists (`{b64_ciphertext, user_id, enc}`) but is not needed for
this. It is also easy to misread: handing it an already-decrypted string answers
`Illegal base64 character 3f`, which looks like a key problem and is not.

## `/query` Sees Three Databases

Measured 2026-09-14 with `SELECT name, file FROM pragma_database_list`:

| schema | file | holds |
| --- | --- | --- |
| `db1` | KakaoTalk.db | `chat_logs`, `chat_rooms`, `chat_threads` |
| `db2` | KakaoTalk2.db | `open_chat_member`, `open_profile`, `open_link`, `call_log` |
| `db3` | multi_profile_database.db | `multi_profiles` (mine, with `statusMessage`) |

Unqualified table names resolve across all three, so `FROM open_chat_member` works
without a prefix. **`sqlite_master` does not**: it is per schema, and `main` holds
nothing but `android_metadata`. A schema dump that forgets the prefix reads as an
empty database - ask `db2.sqlite_master` instead.

An earlier version of this runbook said KakaoTalk2.db was not attached and that
`open_chat_member` lived in KakaoTalk.db. Both were wrong.

## Where Sender Names Come From

**There is no `friends` table in any database on the device** - all 14 files under
`databases/` were checked, not just the attached three. `chat_rooms.members` holds
numeric ids and `private_meta` holds the *room* name, so for a DirectChat,
MultiChat or PlusChat there is no name to read at all, ever.

Those names arrive on the `/ws` push feed, which Iris resolves itself and which also
backs the `webServerEndpoint` webhook - `sharedFlow.collect { send(msg) }`, the
same stream. A consumer that polls `/query` therefore needs the feed as a
side-channel purely for names, and should tolerate a miss.

## Member Profiles: Open Chats Only, And Partially

`db2.open_chat_member` is the one table that maps a user id to a name and a picture,
and it exists for open chats alone. Sixteen columns, of which five are useful:

```sql
SELECT user_id, enc, nickname, profile_image_url, full_profile_image_url
  FROM open_chat_member WHERE involved_chat_id = <chat_id>
```

- `profile_image_url` is 110², `full_profile_image_url` 640², `original_profile_image_url`
  the upload (916² in the row measured, EXIF intact). All three are plain
  `open.kakaocdn.net` / `iopen.kakaocdn.net` URLs, fetchable from the host with `curl`.
- **The decryption rule above applies with one column renamed.** The nickname and all
  three URLs come back base64 unless `user_id` **and `enc`** are in the SELECT - `enc`
  here, not `v`. `open_profile` is the same trap with `v` instead. `require_decryptable`
  in `scripts/hermes/iris_client.py` refuses both shapes.
- There is no status message, real name, birthday or friend flag. The remaining
  columns (`type`, `profile_type`, `link_member_type`, `privilege`, `report`, `pf_id`,
  `profile_link_id`) are undecoded numeric flags.
- **It is a lazy cache.** KakaoTalk fills a row when it renders that member: measured
  48 rows across 5 links, with 5 rows for an 80-member room and 18 for a 78-member one.
  33 of the 48 carried a picture URL. An absent member means uncached, never absent
  from the room, and no query can force the rest to materialise.

`kakao_ai_chat.py --profiles <chat_id> [--match <name>] [--image]` wraps this; see
[KakaoTalk AI Chat Daemon](kakao-ai-chat.md).

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
