# iris-thread-hook

LSPosed(Zygisk) module: puts a KakaoTalk **photo/file** into the same 댓글(thread) as its
caption, for the Iris bot. Companion to `scripts/hermes/iris_client.py:write_thread_hint`.

## Why this exists

Iris threads a text reply (`/reply threadId=` -> `chat_logs.thread_id`) but drops threadId on
media: KakaoTalk's share path builds `ChatSendingLog.b(id, mediaType, scope=0, threadId=null)`
with those literal, and no external surface changes them (upstream Iris#113 closed "can't").
The builder itself has no type restriction, so an in-process hook can fill the two args.

## How it hooks (obfuscation strategy)

Depends only on things obfuscation/updates do **not** move:
- class `com.kakao.talk.manager.send.sending.ChatSendingLog$b` (real package, not obfuscated),
- the message-type enum's constant **names** (`Photo`/`File`/... - R8 keeps enum names),
- constructor arg order `(chatRoomId, type, int scope, Long threadId, ...)` - scope/threadId
  sit right after the type enum.

It hooks every `$b` constructor, finds the media enum arg, requires arg0 to be a `Long`
(the media path passes a primitive chatRoomId; the other ctor takes a chatroom object - the
text path, skipped), then rewrites the following int (scope) and Long (threadId) slots from a
hint file. No obfuscated field/setter name is referenced. Kotlin's default-arg synthetic ctor
restores defaults via its bitmask, so the injection lands on the real 5-arg ctor it delegates
to - both are hooked, only the real one sticks.

## Hint protocol

Daemon writes `/data/local/tmp/iris_thread_<chatId>` (decimal threadId, mode 644) right before
a media send it wants threaded, and removes it for a non-thread send. The hook reads it keyed
by chatId, TTL 60s. Dir is 771 so uid 10087 (com.kakao.talk) reads it by exact path though it
cannot list the dir.

## Build

Needs Android SDK + JDK 17 (not on the DGX host by default - build on a dev machine or a
throwaway SDK container):

    cd android/iris-thread-hook
    gradle assembleDebug          # or ./gradlew if you add a wrapper
    # -> build/outputs/apk/debug/iris-thread-hook-debug.apk

`de.robv.android.xposed:api:82` is `compileOnly` from `https://api.xposed.info/`; if that repo
is down, the same jar is on jitpack.

## Install + enable (inside the redroid container, after Part A gives it LSPosed)

    docker cp iris-thread-hook-debug.apk redroid-poc:/data/local/tmp/m.apk
    docker exec redroid-poc /system/bin/pm install -r /data/local/tmp/m.apk
    # enable in LSPosed Manager, scope = com.kakao.talk, then force-stop KakaoTalk so it
    # reloads with the module. Headless enable: drive the Manager UI once (uiautomator) or
    # edit the LSPosed config DB under /data/adb/lspd/config/.

Verify it armed: `logcat -d | grep iris-thread` shows `armed on ...`; a threaded media send
logs `<Type> chat <id> -> thread <root>`.

## Re-pin on a KakaoTalk update (maintenance)

The arg-order assumption is the only version-sensitive thing. After a forced KakaoTalk upgrade
(no Play Store here, so updates are manual APK reinstalls - the only re-pin trigger), confirm
with baksmali that `ChatSendingLog$b`'s constructors still lay out `(…, type-enum, int scope,
Long threadId, …)` and that media enum constant names are unchanged. If the layout moved, fix
`inject()` in `IrisThreadHook.java`. Measured against com.kakao.talk 26.7.2 (versionCode
29260720).
