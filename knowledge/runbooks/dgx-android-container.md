---
type: Runbook
title: DGX Android Container
description: Verified recipe for running a redroid Android container on the DGX Spark, the six kernel and container gotchas that must each be worked around including one that hard-resets the host, and why the KakaoTalk login inside it has no expiry clock to read.
resource: repo://hermes-workspace/knowledge/runbooks/dgx-android-container.md
tags: [dgx-spark, redroid, android, docker, binderfs, arm64, kakaotalk]
timestamp: 2026-09-18T21:40:00+09:00
---

# DGX Android Container

Verified working on 2026-09-13: `redroid/redroid:14.0.0_64only-latest`, Android 14 / SDK 34,
boot in 10 seconds, 49 services, 583MB RSS, 0.11% CPU on an idle DGX.

Upstream redroid does **not** support binderfs kernels and the DGX kernel is binderfs-only,
so every step below is a workaround rather than a supported configuration. Treat this as a
lab recipe, not a production pattern.

## Hazard First: `--privileged` Lets The Container Hard-Reset The DGX

On the first attempt the DGX **rebooted**. The boot ledger shows the previous boot ending
mid-crash-loop with no systemd shutdown sequence:

```text
journalctl --list-boots
 -1 ... Sun 2026-09-13 13:39:40 KST  Sun 2026-09-13 19:44:34 KST
  0 ... Sun 2026-09-13 19:45:53 KST  ...
```

Android `init` reboots the device when early boot fails. Under `--privileged` the container
holds `CAP_SYS_BOOT` and runs seccomp-unconfined, so that reboot reached the host.

`--cap-drop=SYS_BOOT` does **not** help; `--privileged` wins:

```bash
docker run --rm --privileged --cap-drop=SYS_BOOT debian:stable-slim grep CapEff /proc/self/status
# CapEff: 000001ffffffffff   ← identical to plain --privileged
```

An explicit seccomp profile **does** override `--privileged`. Always pass one:

```json
{
  "defaultAction": "SCMP_ACT_ALLOW",
  "syscalls": [
    { "names": ["reboot", "kexec_load", "kexec_file_load"], "action": "SCMP_ACT_ERRNO", "errnoRet": 1 }
  ]
}
```

Verify it took: `docker exec <c> grep Seccomp: /proc/1/status` must print `Seccomp: 2`.

Never start a redroid container on the DGX without this profile. ComfyUI runs on this host.

## Host Setup

`sudo` needs a password on the DGX, but membership in the `docker` group is already
root-equivalent, so host-level setup can run through a privileged container:

```bash
docker run --rm --privileged --pid=host debian:stable-slim nsenter -t 1 -m -u -i -n -p -- sh -c '
  lsmod | grep -q binder_linux || modprobe binder_linux devices=binder,hwbinder,vndbinder
  mkdir -p /dev/binderfs
  mountpoint -q /dev/binderfs || mount -t binder binder /dev/binderfs
  chmod 0666 /dev/binderfs/binder /dev/binderfs/hwbinder /dev/binderfs/vndbinder
  ls -la /dev/binderfs/'
```

This does not survive a reboot. Re-run it after each boot.

## Run

```bash
docker run -itd --name redroid-poc --privileged \
  --security-opt seccomp=$HOME/redroid-poc/no-reboot.json \
  -v /dev/binderfs/binder:/dev/binder \
  -v /dev/binderfs/hwbinder:/dev/hwbinder \
  -v /dev/binderfs/vndbinder:/dev/vndbinder \
  -v ~/redroid-poc/data64:/data -p 127.0.0.1:5555:5555 \
  -v /dev/null:/dev/kmsg \
  redroid/redroid:14.0.0_64only-latest androidboot.redroid_gpu_mode=guest
```

## The Six Gotchas

### 1. Bind-mount the binder nodes; `--device` does not work

The kernel is `CONFIG_ANDROID_BINDERFS=m`, and upstream `binder_init()` skips legacy device
creation entirely when binderfs is compiled in. So `modprobe binder_linux devices=...` never
creates `/dev/binder`, and the redroid docs' Ubuntu recipe silently does nothing useful.

`--device=/dev/binderfs/binder:/dev/binder` mknods a **new** node with the same major/minor.
That node is not the binderfs inode, so opening it fails:

```text
ProcessState: Opening '/dev/binder' failed: Permission denied
hw-ProcessState: Opening '/dev/hwbinder' failed: No such device or address
```

`-v /dev/binderfs/binder:/dev/binder` bind-mounts the original inode and works.

### 2. binderfs nodes are `0600 root:root`

Android's `hwservicemanager` and friends do not run as root, so a bind-mounted 0600 node
yields `Opening '/dev/hwbinder' failed: Permission denied` and an endless
`ServiceManagerCppClient: Waited for servicemanager.ready` loop. `chmod 0666` them on the
host. Real devices ship these at 0666.

This loosens host permissions until the next reboot: any local user can then open binder.

### 3. GB10 has no AArch32, so only `_64only` images boot

The standard image reboot-loops with:

```text
[persist.sys.boot.reason]: [reboot,boringssl-self-check-failed]
[init.svc.boringssl_self_test32_vendor]: [stopped]
```

`boringssl_self_test32_vendor` is a 32-bit binary. The kernel never reports
`CPU features: detected: 32-bit EL0 Support`, and `/sys/devices/system/cpu/aarch32_el0` does
not exist, so the GB10 cores (`CPU part 0xd87`) cannot execute it. Combined with gotcha 1
this failure also triggered the host reboot.

Consequence beyond booting: `ro.product.cpu.abilist` is `arm64-v8a` **only**. Any APK whose
native libraries are 32-bit-only will not run here.

### 4. `uiautomator dump` is dead on Android 14

It exits 0, writes nothing, and logs nothing, whether invoked as `uiautomator dump`,
via `app_process`, or as `cmd uiautomator` (`Can't find service: uiautomator`). Use
`dumpsys activity top` for the view hierarchy, or drive uiautomator over ADB from a client
such as uiautomator2.

### 5. The container writes Android's logs into the host kernel ring buffer

Under `--privileged` the container gets the host `/dev/kmsg`, so Android's `init`, `libselinux`
and anything that logs before `logd` is up land in the **host** journal as `_TRANSPORT=kernel`.
Measured 2026-09-13: 63,656 of the host boot's 108,827 journal lines (58%) came from the
container. During the early-boot loop it is `ServiceManagerCppClient: Waited for
servicemanager.ready` at 1 Hz; once booted it settles to `SELinux: Loaded service context from:`
about every 3 s.

That is not only noise. It is what buried the host's own shutdown sequence when the tail of the
previous boot was read during the shutdown investigation in
[DGX Spark Remote Access](dgx-spark-remote-access.md).

Give the container its own sink — this is in the `Run` block above:

```bash
-v /dev/null:/dev/kmsg
```

Container-scoped and it survives host reboots, but it is a `docker run` argument, so applying it
to an already-created container means `docker rm` + `docker run`; `dgx-ai-control` only ever
calls `docker start` / `docker stop`. The host-wide alternative needs no restart but also
silences `systemd-shutdown`, which logs to kmsg after journald has stopped:

```bash
sysctl -w kernel.printk_devkmsg=off
```

Do not reach for `journalctl --vacuum-size` to clean up afterwards. The spam is the *newest*
data, so vacuum-by-size deletes the oldest archives first — here that is the boot ledger back to
August that the shutdown diagnosis rests on. journald already self-caps (4 GB default) and 591 MB
on a 3.7 TB disk is not a problem worth trading evidence for.


### 6. lmkd wedges `system_server` on a 6.9+ host kernel

Symptom: KakaoTalk goes dark. Inside the container `ip rule` has no rule for table 1002 although
the routes are all there; `zygote64`, `netd` and `system_server` share one age and it resets every
~90 s; `lmkd` and `logd` sit at 100% CPU; `/data/anr/` fills with `system_server` dumps whose main
thread is in `LmkdConnection` (`waitForConnection`, `write`, or waiting for the AMS lock held by a
thread in `LmkdConnection.write`). The missing rule is a by-product of the restart loop, not a
config fault — a clean boot has no 1002 rule either.

Cause, verified 2026-09-18 from source and a live kernel test. lmkd registers a `pidfd` in its
epoll set while it waits for a process it killed to die. Linux 6.9+ reports `EPOLLHUP` on a pidfd
once the process is *reaped* (this host runs 6.17; measured 1 before reap, 17 after). Android 14's
lmkd treats every `EPOLLHUP` as a dropped data-socket connection: it closes data slot 0 —
system_server's socket — and decrements `maxevents`, and because the second pass skips `EPOLLHUP`
events the pidfd is never unregistered, so the level-triggered event repeats each iteration until
`maxevents` reaches 0 and `epoll_wait` returns `EINVAL` forever: a busy loop that logs 600k lines/s
and never accepts on `/dev/socket/lmkd`. Upstream fixed it in AOSP `667fdbfe` ("lmkd: fix handling
of EPOLLHUP for pidfd", 2024-09-13), first shipped in `android-15.0.0_r20`; none of the 71
`android-14` tags has it, so a redroid 14 image always carries the bug.

It fires only when lmkd kills, and lmkd kills here because `/proc/pressure/memory` inside the
container is the **host's** PSI. A heavy host job (this time a YuE2 run launched 74 s before the
first watchdog) trips the trigger, lmkd kills a cached app, and the race against zygote's reap
decides whether lmkd survives. `dumpsys activity exit-info` showed 16 such kills over five days;
one lost the race. The kill that wedges lmkd never shows there — AMS persists exit records every
30 min and Watchdog kills `system_server` within 90 s.

The fix, in force since 2026-09-18 and persisted in `/data/property` (bind-mounted, so it survives
restarts and even `docker rm`):

```bash
docker exec redroid-poc setprop persist.device_config.lmkd_native.psi_partial_stall_ms 0
docker exec redroid-poc setprop persist.device_config.lmkd_native.psi_complete_stall_ms 0
```

A threshold of 0 makes `init_mp_psi` skip that level, so lmkd registers no PSI monitor: no kills,
no pidfd, no wedge. `lmkd.rc` turns each `setprop` into `lmkd --reinit`, which reloads the props
over the socket without a restart — the lmkd pid did not change. Verify with
`ls -l /proc/$(pidof lmkd)/fd | grep -c pressure` → `0` and `Properties reinitilized` in logcat.
lmkd was protecting nothing here (the container has no memory limit) and was killing container
apps in response to host swap.

If it wedges anyway, **do not `docker restart`** — that drops Iris and KakaoTalk, which do not come
back on their own, and destroys the evidence. Capture, then restart lmkd alone:

```bash
docker exec redroid-poc sh -c 'ls -l /proc/$(pidof lmkd)/fd'   # fd 3 should be anon_inode:[eventpoll]
docker exec redroid-poc setprop ctl.restart lmkd
```

`ctl.restart` sets `SVC_RESTART`, which init's critical-crash counter ignores; `kill -9` counts as
a crash and four in four minutes reboot the container. lmkd is back in about 5 s and
`system_server` is untouched, because a *missing* lmkd socket makes `LmkdConnection.connect()` fail
fast — only a *deaf* one blocks. `setprop lmkd.reinit 1` cannot repair a wedge: it talks to lmkd
over the same deaf socket and its helper blocks in `read()` forever. `redroid/lmkd-watchdog.{sh,service,timer}`
automates capture-then-restart when lmkd exceeds 90% CPU over 5 s, at most once per 10 minutes;
it runs as a systemd user timer on the DGX.


## Installing A Play-Distributed App

Play ships App Bundles, so an app is a set of splits rather than one APK. Pull them from a
device that already has it, which also keeps provenance clean:

```bash
adb shell pm path com.kakao.talk        # base.apk + split_config.* + feature splits
adb pull <each> ./apk/
scp ./apk/*.apk dgx:~/redroid-poc/data64/apk/     # the /data bind mount, no docker cp needed
```

`pm install-multiple` **does not exist** on this image (`Unknown command`). Use a session:

```bash
docker exec redroid-poc sh -c '
SID=$(pm install-create -r -t | sed "s/.*\[\([0-9]*\)\].*/\1/")
for f in /data/apk/*.apk; do
  pm install-write -S $(stat -c%s $f) $SID $(basename $f) $f
done
pm install-commit $SID'
```

Benign noise during first launch: `vold: Failed to set project id ...` (project quotas are not
available on the bind-mounted `/data`) and `VerityUtils: Failed to measure fs-verity`. Neither
blocks the app.

## Presenting The Container As A Tablet

KakaoTalk only offers the companion ("다른 기기와 함께 사용") login on a device it classifies
as a tablet. Screen size and `ro.build.characteristics` alone are **not** enough — with
`sw800dp`, `xlrg`, `ro.build.characteristics=tablet` and a `ko-KR` locale the checkbox still
did not appear. It appeared only after the device identity was also changed:

```bash
androidboot.redroid_width=1600 androidboot.redroid_height=2560 androidboot.redroid_dpi=320
ro.build.characteristics=tablet
ro.product.model=SM-X926N ro.product.brand=samsung ro.product.manufacturer=samsung
ro.product.name=gts10ultraks ro.product.device=gts10ultra
```

Model, brand and manufacturer were changed together, so which one is the actual gate was not
isolated. `android.hardware.telephony` is already absent from redroid and is not the gate.

With that in place the login screen gains a pre-checked "다른 기기와 함께 사용" box and a
"QR코드 로그인" button, which routes to `SubDeviceQRLoginActivity`. The QR is valid for 60
seconds and the security code that follows for another 60, so relaying both through a chat
round-trip will time out — capture and hand over the QR first, then poll for the code.

Locale and timezone persist in the bind-mounted `/data`:

```bash
setprop persist.sys.locale ko-KR
setprop persist.sys.timezone Asia/Seoul
```

## The Login Session Has No Expiry Clock

Nothing on the device, in the app, or in the server's replies says when the companion login will
end. Checked on 2026-09-14 against the running container, a jadx export of KakaoTalk 25.7.2, and
node-kakao; all three agree that no such timestamp exists.

**The credential store holds no time field.** The tokens are not in `shared_prefs` any more; they
moved to a Jetpack Preferences DataStore. Parsing all 36 keys of
`/data/data/com.kakao.talk/files/datastore/LocalUser_DataStore.pref.preferences_pb`:

| Kind | Keys |
| --- | --- |
| Tokens | `encrypted_auth_token_v2`, `encrypted_auth_token`, `old_encrypted_auth_token`, `hashedRefreshToken` |
| State | `authenticationStatus`, `needToReauthenticate`, `authentication_at_install` |
| Rest | account id, phone number, revision counters |

None of them is a timestamp. `sekdlak` in `KakaoTalk.hw.perferences.xml` is **not** the access
token, despite looking like the only credential-shaped value in the prefs: it is the screen-lock
passcode, read only on the `PassLockActivity` / `PatternLockActivity` branch.

**The app refreshes reactively, not on a schedule.** In `OauthHelper` (`zK/C75681b` in the jadx
export) the refresh entry point runs only after a request has already failed. Its one time
constant, `last + 20000 < currentTimeMillis()`, is a 20-second debounce per token pair, not a TTL.
The 19-digit number taken from `accessToken.substring(32, 51)` is a pair identifier checked against
the refresh token (`OauthTokenValidatePairException`), not an issue time.

**The server reports failure, never a deadline.** The status enum has no `TOKEN_EXPIRED` member:

| Code | Name |
| --- | --- |
| -100002 | `INVALID_TOKEN` |
| -950 | `TOKEN_REFRESH_REQUIRED` |
| -998 | `AUTHENTICATION_REQUIRED` |
| -151 | `LOGIN_DENIED_BY_MAIN_DEVICE` |
| -101 | `ANOTHER_DEVICE_LOGGED_IN` |
| -100 | `NEED_DEVICE_AUTH` |

Each of these drives the logout path, which clears the token keys and sets `authenticationStatus`
away from `AllDone`. No public Kakao documentation states a companion-session lifetime either; the
"refresh token lasts two months" figure that search turns up belongs to third-party Kakao Login
OAuth, which is a different credential from the talk client's session.

### Do Not Call `oauth2_token.json` To Find Out

`POST katalk.kakao.com/<agent>/account/oauth2_token.json` with `grant_type=refresh_token` is the
one place that returns `expires_in`
([node-kakao `oauth-api-client.ts`](https://github.com/storycraft/node-kakao/blob/master/src/api/oauth-api-client.ts)).
It is a rotation, not a read: it mints a new pair and invalidates the old one. KakaoTalk in the
container still holds its own copy, so its next request fails with -950 or -100002 and takes the
logout path. Asking when the session expires this way expires it.

### Detect It Instead

Read the app's own verdict. `AllDone` means the login is still good:

```bash
docker exec redroid-poc strings \
  /data/data/com.kakao.talk/files/datastore/LocalUser_DataStore.pref.preferences_pb |
  grep -A1 '^authenticationStatus$' | tail -1
```

Prefer this to watching the LOCO socket. That check is
`docker exec redroid-poc grep ':2442 ' /proc/net/tcp6 | grep -c ' 10087 '` — port 9282 to
`chat-api-relay-*.kakao.com`, uid 10087 being `com.kakao.talk`, and it must read `tcp6` rather than
`tcp` because the connection is IPv4-mapped and `tcp` therefore always reports zero. But the socket
also disappears for a network outage or a reconnect, while `authenticationStatus` changes only when
the app itself considers the login gone.

Iris is not a source for this. `GET /dashboard/status` returns `isObserving`, the state of its DB
observer thread, which stays `true` after a logout because the database file is still there. It
also listens on the container address (`172.17.0.2:3000`), not on the host's loopback.

## Verified Control Surface

| Check | Result |
| --- | --- |
| `getprop ro.product.cpu.abi` | `arm64-v8a` — native, no translation layer |
| `getprop ro.product.cpu.abilist` | `arm64-v8a` only |
| `getprop ro.build.version.sdk` | `34` |
| `pm list packages` | 113 |
| `input keyevent` | works |
| `screencap -p` | works, 687KB PNG |
| `dumpsys activity top` | 77 view-hierarchy lines |
| `/system/bin/sqlite3`, `/data/data` | present — the surface an Iris-style DB observer needs |
| `adbd`, port 5555 | running, bound to `127.0.0.1` only |

## Resuming After A Host Reboot

**The DGX AI Control app does all of this.** `~/src/dgx-ai-control` has an Android Container row
with Start / Stop / Restart, and `dgx-ai-control --android start|stop|restart|status` from a
shell. Start runs the binder prep, starts the container, waits for `boot_completed`, then starts
Iris. Measured at roughly 9s cold, 10s to stop. Prefer it over the manual steps below; the manual
path is here so the app's behaviour is auditable and so recovery is possible if the app breaks.

Three things do not survive a reboot and must be redone in order before the container is useful
again. The container itself and the KakaoTalk session do survive, because they live in the
bind-mounted `/data`.

1. `binder_linux` and the `/dev/binderfs` mount — re-run the host setup block above.
2. `chmod 0666` on the three binderfs nodes — same block; without it Android's non-root services loop on `servicemanager.ready`.
3. `docker start redroid-poc`, then start Iris again (see [Iris On DGX](iris-on-dgx.md)); `app_process` does not come back on its own.

## Teardown

```bash
docker rm -f redroid-poc
docker run --rm --privileged --pid=host debian:stable-slim nsenter -t 1 -m -u -i -n -p -- sh -c '
  umount /dev/binderfs; rmmod binder_linux'
```

Removing `bobeenlee` from the `docker` group (`sudo gpasswd -d bobeenlee docker`) is the only
change that otherwise persists.

## Scope

This runbook covers the container. Whether KakaoTalk may run inside it is a separate and
independently blocking question: see [KakaoTalk Control Portability](kakaotalk-control-portability.md).
