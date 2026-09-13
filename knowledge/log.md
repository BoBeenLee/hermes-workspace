# Knowledge Log

## 2026-09-13

- Installed and launched KakaoTalk 26.7.2 inside the DGX redroid container. It reaches a clean login screen on an uncertified, rooted Android, `KakaoTalk.db` and `KakaoTalk2.db` are present, and the window exposes a 124-line view hierarchy. Play Integrity did not block it. The run was stopped at the login screen so no device slot was consumed.
- Sourced the app as Play splits pulled from the operator's own Galaxy S25 Ultra over ADB rather than from a third-party mirror, and recorded that `pm install-multiple` does not exist on the redroid image — a `pm install-create` session is required.

- Built and verified a redroid Android 14 container on the DGX Spark: boots in 10 seconds, `arm64-v8a` native, with input injection, `screencap`, `dumpsys` view hierarchy, `sqlite3`, and loopback ADB. Recorded as [DGX Android Container](runbooks/dgx-android-container.md).
- **Incident:** the first container hard-reset the DGX at 19:44:34. Android `init` reboots on early-boot failure, and `--privileged` grants `CAP_SYS_BOOT` with seccomp unconfined, so the reboot reached the host. No work was lost (ComfyUI queue was empty, zero failed units after boot). `--cap-drop=SYS_BOOT` does not work under `--privileged`; an explicit `--security-opt seccomp=` profile does, and is now mandatory for this container.
- Found that `--device` cannot pass binderfs nodes into a container (mknod loses the binderfs inode, giving EACCES/ENXIO); a `-v` bind mount of the node works, and the nodes must be `chmod 0666` because Android services are not root.
- Established that GB10 has no AArch32, so only redroid `_64only` images boot and `ro.product.cpu.abilist` is `arm64-v8a` alone.
- Noted that `docker` group membership on the DGX is already root-equivalent, so host setup runs through `nsenter` in a privileged container without the sudo password.

- Recorded why KakaoTalk control cannot move to the DGX Spark while the Hermes agent itself can: the MCP server is a thin wrapper and the macOS dependency lives in the vendored `kakaocli` (SQLCipher container DB plus Keychain) and `kmsg` (Accessibility `AXPress`) binaries.
- Established the deciding constraint as the KakaoTalk device-slot rule, not software portability: a Wine companion client evicts the Mac and an Android container evicts the phone, so a DGX path presupposes a separate number or account.
- Evaluated and rejected Wine plus KakaoTalk PC on aarch64: unverified under Hangover, no AT-SPI bridge in Wine, `uiautomationcore` at 36 of 98 exports, and a capability regression because the messenger assistant's fail-closed rules need database evidence a scrape cannot supply.
- Measured the DGX against redroid prerequisites and found all of them met (binderfs, memfd, IPv6, DMA-BUF heaps, 4KB pages), making redroid plus Iris the only structurally matching path.
- Noted that `kmsg status` launches KakaoTalk.app and is not a read-only probe, and that DGX `sudo` is password-only except `shutdown`/`poweroff`.

## 2026-08-20

- Made the DGX Spark runbook the single entry point for DGX work: added a `DGX Doc Map` that assigns ComfyUI service internals to the `remote-comfyui` repo, and an `Accounts And Control Paths` section covering the `bobeenlee` vs `comfyops` boundary, the three `comfyui.service` control paths that all resolve to the owner's user unit, and the tunnel and MCP-host equivalence.
- Stopped restating ComfyUI service internals under Local AI Services, and routed the DGX Spark concept doc at the runbook with the Tailscale address as the current access path.
- Corrected the pre-shutdown idle check to `~/src/ComfyUI/output`; `~/ComfyUI/output` does not exist on the device, so the check silently always reported no recent ComfyUI writes.

## 2026-08-19

- Documented the DGX Spark shutdown path: the pre-shutdown idle checklist, `ssh -t` plus interactive `sudo shutdown -h now` as the only working remote route, why `sudo -n` and `systemctl poweroff` fail from an SSH session, and what comes back automatically after boot.

## 2026-08-17

- Recorded the `platform_toolsets` validation warning as a documented false positive: `hermes config migrate` cannot see MCP-server toolset aliases because they are only registered on MCP connect, so editing the config to silence it would disable those tools.

## 2026-07-05

- Moved the detailed KakaoTalk Mac MCP runbook to the canonical skill repo:
  `/Users/mac_al03241161/Documents/mygit/kakaotalk-mac-message-list-skill/docs/hermes/kakaotalk-mac-mcp.md`.
- Verified direct Discord mention-based KakaoTalk MCP lookup through Jarvis with KST timestamps, after adding short-lived cache fallback guidance.
- Recorded the Jarvis Discord KakaoTalk timeout incident, root cause, bounded MCP scan behavior, and recovery verification.
- Documented Hermes Mac Manager power schedule controls, including default-disabled behavior, `pmset` effects, the keep-awake LaunchAgent, and review-required safety notes.
- Initially documented the KakaoTalk Mac MCP runbook for remote Hermes Agent
  verification, then moved the canonical copy to the skill repo above.
- Documented `HERMES_RUN_TOOLSETS` for `bin/hermes-remote run` so MCP-specific prompts can bypass the macOS `computer_use` default.

## 2026-06-27

- Created the `knowledge/` OKF bundle.
- Migrated Hermes concepts, workflows, runbooks, tools, skills, policies, and plans into OKF-style Markdown documents.
- Added future authoring rules so durable knowledge is created under `knowledge/` with required frontmatter.
