---
type: Runbook
title: KakaoTalk Control Portability
description: Why KakaoTalk control cannot move off the default macOS target, what each alternative path actually costs, and the account device-slot rule that decides the question.
resource: repo://hermes-workspace/knowledge/runbooks/kakaotalk-control-portability.md
tags: [kakaotalk, dgx-spark, linux, computer-use, portability, wine, redroid]
timestamp: 2026-09-13T19:40:00+09:00
---

# KakaoTalk Control Portability

## Question This Answers

"Can the DGX Spark run the same Hermes agent as the default macOS target, including KakaoTalk control?"

The two halves have opposite answers. Do not answer them together.

| Half | Verdict |
| --- | --- |
| Hermes agent on DGX | **Yes**, as a headless Linux host. See [Hermes Agent Multi-Host Bootstrap](hermes-agent-multi-host.md) and [Linux Target Profile](linux-target-profile.md). |
| KakaoTalk control on DGX | **No** with the current account. The blocker is the account device slot, not the software. |

## What Actually Implements KakaoTalk Control

`openhuman-kakaotalk-mac` is a thin wrapper, not the mechanism. Its `mcp_server.py`
contains zero calls to `osascript`, `AXUIElement`, `CGEvent`, or `NSWorkspace`; it
shells out to two vendored Swift binaries. The macOS dependency lives there.

| Binary | Role | Verified dependency |
| --- | --- | --- |
| `vendor/kakaocli` | read | Mach-O arm64 linking `libsqlcipher` and `Vision.framework`. Reads the SQLCipher database under `~/Library/Containers/com.kakao.KakaoTalkMac/Data/Library/Application Support/`, with the key pulled from the macOS Keychain item `com.kakaocli.credentials`. |
| `vendor/kmsg` | send, watch | Mach-O arm64 linking `AppKit` and `ApplicationServices`. Drives the KakaoTalk.app window through the macOS Accessibility API (`AXUIElement`, `AXPress`). Requires a TCC Accessibility grant. |

Re-check on the default macOS target:

```bash
ssh bobeen 'cd ~/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor && otool -L kmsg/.build/release/kmsg | head -5'
ssh bobeen 'cd ~/.hermes/mcp-servers/openhuman-kakaotalk-mac/vendor && otool -L kakaocli/.build/release/kakaocli | head -3'
```

**Side effect warning:** `kmsg status` launches KakaoTalk.app if it is not already
running. It is not a read-only probe. Do not use it as a liveness check.

The chain is macOS app plus TCC Accessibility grant plus Keychain/Container. That is a
rewrite target, not a recompile target.

## The Rule That Decides It: Device Slots

KakaoTalk permits **one mobile device plus one companion (PC or tablet)** signed in
at a time.

- The companion slot is currently held by KakaoTalk.app on the default macOS target, which is what `kmsg` drives.
- A Windows KakaoTalk under Wine on the DGX takes **the same companion slot**, so it evicts the Mac.
- An Android KakaoTalk in a container on the DGX takes **the mobile slot**, so it evicts the phone.

A second host cannot add a slot. It can only take one away from something that already
works. **Any DGX KakaoTalk work therefore presupposes a separate phone number or
account.** Confirm that before spending effort on any path below.

## Path Evaluation

### Wine plus KakaoTalk PC: not worth pursuing

Three independent problems, and clearing all three still loses capability.

1. **Run.** KakaoTalk runs under Wine 11.0 on x86_64 Ubuntu 24.04; Korean IME composition in the chat box is the hard part, not launching. The DGX is aarch64: `dpkg --print-foreign-architectures` is empty and the distro `wine` is a 9.0 arm64 build, so x86 PE binaries will not run. [Hangover](https://github.com/AndreRH/hangover) 11.0 (Wine 11 plus FEX/Box64, arm64 `.deb` for Ubuntu 24.04) is the only route, and the project scopes itself to "simple Win32/Win64 applications". No KakaoTalk success report was found. Unverified.
2. **Control.** Wine has **no AT-SPI bridge**. NVDA does not work under Wine and the bridge has been discussed for years without an implementation, so `computer-use-linux` or any other AT-SPI client would see an empty shell where the KakaoTalk window is. Wine's `uiautomationcore` implements 36 of 98 exports, so `pywinauto` with `backend="uia"` is not dependable either. What remains is raw Win32 window messages (`FindWindow` to `RichEdit50W` to `SendMessage`) executed by a Win32 binary inside the same prefix. Plausible, since Wine's `user32` is solid, but unverified and it is new code.
3. **Capability regression.** The Jarvis messenger assistant's fail-closed rules depend on structured database evidence: `NTUser.directChatId`, `userType`, read state, timestamps. A window-message plus clipboard scrape cannot produce that evidence, so the direct-room guard and read-state rules in [Jarvis Messenger Assistant](jarvis-messenger-assistant.md) lose their basis. A working Wine path would be a **downgrade**, not parity.

### Android container (redroid plus Iris): the only structural match

[redroid](https://github.com/remote-android/redroid-doc) publishes arm64 images and runs
headless. Because the DGX is aarch64, the KakaoTalk ARM APK runs **natively**, with no
`libhoudini` or `libndk` translation layer, which an x86 host would need.

The container half of this was **built and verified on 2026-09-13**: Android 14 boots on the
DGX in 10 seconds, `arm64-v8a` native, with input injection, screenshots, view-hierarchy dumps,
`sqlite3`, and loopback ADB all working. It took four workarounds, one of which hard-reset the
host on the first attempt. The recipe and the hazards are in
[DGX Android Container](dgx-android-container.md).

Two results from that PoC constrain a KakaoTalk port:

- `ro.product.cpu.abilist` is `arm64-v8a` **only** — GB10 has no AArch32, so the KakaoTalk APK must ship 64-bit native libraries.
- upstream redroid does not support binderfs kernels, so this stack is unsupported configuration that a kernel update can break at any time.

[Iris](https://github.com/dolidolih/Iris) is the Android counterpart of the current Mac
stack: it polls KakaoTalk's Android SQLite `chat_logs`, decrypts the encrypted fields,
publishes over HTTP/WebSocket, and sends replies through Android's hidden
`IActivityManager` intent API. It requires root, which a redroid container has. That
read-from-database plus send-through-app shape maps one to one onto `kakaocli` plus
`kmsg`, so the messenger assistant's policy engine could port.

Caveats: Iris documents neither arm64 support nor the device-slot consequence. The
author's redroid reference integration, `PyKakaoDBBot`, is marked **DEPRECATED** in
favour of Iris and targets x86_64 Ubuntu 24.04, so arm64 is unproven ground.

### Official Kakao API: cannot do this at all

The [KakaoTalk Message API](http://developers.kakao.com/docs/ko/kakaotalk-message/common)
offers send-to-self (unlimited) and send-to-friend (consent plus daily caps). It provides
**no way to read or reply to a received 1:1 conversation**. It is not a fallback for the
messenger assistant.

### LOCO protocol reimplementation: effectively dead

`node-kakao` (424 stars) last shipped 2023-11; `loco.rs` 2022; `kakao-nibs` 2023. The only
2026 candidate has no adoption. These are reverse-engineered private protocols that break
when the server changes and carry explicit permanent-restriction warnings. Do not build
on them.

## Operating Notes For A DGX PoC

- `sudo` on the DGX requires a password over SSH. `sudo -n -l` reports only `/sbin/shutdown`, `/usr/sbin/shutdown`, `/sbin/poweroff`, and `/usr/sbin/poweroff` as NOPASSWD, so loading `binder_linux` and reaching Docker both need a human-run bootstrap. Passwordless SSH key login is unrelated and does not extend to `sudo`. This matches the interactive-sudo constraint recorded for [DGX Spark Remote Access](dgx-spark-remote-access.md).
- `bobeenlee` is not in the `docker` group, and the group is empty.
- Keep the container's ADB endpoint on loopback and reach it over an SSH tunnel, per [Safety Rules](../policies/safety-rules.md).
- Do **not** sign in to KakaoTalk during infrastructure validation. Sign-in is the step that consumes a device slot and evicts an existing client.
- Unofficial KakaoTalk automation sits outside Kakao's terms; Iris states educational and research purposes only. This is the same exposure already accepted on the Mac, but a new account increases it.

## Verdict

Keep KakaoTalk on the default macOS target. Wine is not worth further investigation: it is
unverified on aarch64, has no accessibility surface, and would reduce capability even if it
worked. If a separate phone number becomes available, redroid plus Iris is the path to
evaluate.
