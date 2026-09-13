---
type: Runbook
title: DGX Android Container
description: Verified recipe for running a redroid Android container on the DGX Spark, and the four kernel and container gotchas that must each be worked around, including one that hard-resets the host.
resource: repo://hermes-workspace/knowledge/runbooks/dgx-android-container.md
tags: [dgx-spark, redroid, android, docker, binderfs, arm64]
timestamp: 2026-09-13T20:15:00+09:00
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
  redroid/redroid:14.0.0_64only-latest androidboot.redroid_gpu_mode=guest
```

## The Four Gotchas

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
