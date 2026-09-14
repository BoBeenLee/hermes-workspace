# frida/ — put KakaoTalk photos & files into the same 댓글(thread) as their caption

Iris threads a **text** reply (`/reply threadId=` -> `chat_logs.thread_id`) but drops the
threadId on **media** rows: KakaoTalk's share path builds
`ChatSendingLog.b(id, mediaType, scope=0, threadId=null)` with those two literal. This hook
fills them in-process, so a photo/file lands inside the comment thread instead of as a loose
row below the caption.

## Why Frida and not LSPosed/Zygisk

Zygisk cannot inject zygote in redroid: there is no boot ramdisk, so `magiskinit` never hooks
the zygote launch. Verified on this host - Magisk daemon runs and Zygisk is enabled, but
zygote's maps stay clean and no LSPosed daemon comes up, even after a zygote restart. Riru is
archived (no Android 14). LSPatch would resign KakaoTalk and cost the login. Frida ptrace-
attaches the already-running app: no Magisk, no resign, no container recreate, login intact.

## Pieces

- `iris_thread.js` - the hook. Finds the primary media constructor
  `ChatSendingLog$b(long, cu8, int, java.lang.Long, boolean)` by argument SHAPE (not by
  obfuscated names - the enum's constant names `Photo`/`File`/... survive R8, and the arg
  order type,scope,threadId is stable). When a fresh hint is present it rewrites scope=3
  (방+스레드: the media shows in the main chat AND is linked as a 댓글; scope=2 hid it from
  the main timeline, which read as "missing") and the
  threadId. Consume-once by mtime: it runs as the kakao uid and cannot delete the root-owned
  hint file, so it remembers the last mtime it used.
- `driver.py` - host-side, keeps the hook attached; re-attaches when KakaoTalk restarts and
  relaunches frida-server when the container restarts. Run under systemd.
- `kakao-frida-hook.service` - the systemd **user** unit that runs driver.py.
- `frida_start.sh` - runs INSIDE the container; imports system_server's env (BOOTCLASSPATH
  etc., without which frida-server's JavaVM creation aborts) then execs frida-server.

## The hint protocol

`scripts/hermes/iris_client.py:write_thread_hint` writes the turn's 댓글 root to
`/data/local/tmp/iris_thread_pending` (single file, refreshed via `docker exec printf` right
before each media send in `kakao_ai_chat.send_message`). The hook reads it, applies it once,
and the same root threads the caption (via Iris) and every media row (via this hook). A
non-thread send (cron) writes no hint, so nothing stale is applied.

Limitation: a multi-image `reply_images` is one Iris call producing N builder calls, and
consume-once threads only the first. Our sends are a single image; files go one per
`iris_send_file`, each refreshing the hint, so multi-file threads fully.

## Deploy (DGX)

frida-server + client pinned to **16.7.19** (17.x removed the global `Java` bridge). Host uses
a venv at `~/redroid-build/venv` (`pip install frida==16.7.19 frida-tools`).

    # frida-server into the container (docker cp fails on this container's read-only /dev
    # binds; stream via tar over docker exec instead):
    curl -L .../frida-server-16.7.19-android-arm64.xz | unxz > frida-server
    tar -C . --transform 's/.*/frida-server/' -cf - frida-server \
      | docker exec -i redroid-poc /system/bin/sh -c 'cd /data/local/tmp && tar -xf - && chmod 755 frida-server'
    # frida_start.sh -> /data/local/tmp/ (same tar-over-exec trick)
    # then:
    cp iris_thread.js driver.py ~/redroid-build/frida/
    cp kakao-frida-hook.service ~/.config/systemd/user/
    systemctl --user daemon-reload && systemctl --user enable --now kakao-frida-hook.service

`/data` is a host bind mount, so frida-server and frida_start.sh survive a container restart;
driver.py relaunches frida-server after one. Verify: `journalctl --user -u kakao-frida-hook`
shows `armed` + `attached`; a threaded media send logs `<Type> -> thread <root>`.

## Re-pin on a KakaoTalk update

The only version-sensitive assumption is the constructor shape `(long, cu8, int, Long,
boolean)` and the media enum constant names. After a forced KakaoTalk upgrade (no Play Store
here, so updates are manual APK reinstalls) confirm both with a Frida probe; adjust
`iris_thread.js` if they moved. Measured against com.kakao.talk 26.7.2 (versionCode 29260720).
