# Knowledge Log

## 2026-09-13

- Completing the MCP server rename took four more places than the config edit suggested, and each one failed quietly: the `jarvis` profile keeps its own `mcp_servers` block, `bin/kakaocli-self-ssh` hard-codes the vendored binary path, and `messenger_assistant.py` and `kakao_ai_chat.py` pin the name as module constants while running from deployed copies outside this repo. Wrote it up as [Renaming An MCP Server](runbooks/renaming-an-mcp-server.md).
- The lesson worth keeping: `hermes -t <name> -z` answering OK proves the toolset resolves and nothing else. Both dependent services were broken while that check was green.

- Swept the remaining `kakaotalk_mac` / `openhuman-kakaotalk-mac` identifiers out of the workspace, task artifacts and quoted output included, so nothing in the repo names something that no longer exists.
- That sweep caught real breakage, not just prose: `scripts/hermes/messenger_assistant.py` pinned `KAKAO_TOOLSET` and `KAKAO_MCP_TOOL_PREFIX` to the old names, and `scripts/hermes/kakao_ai_chat.py` held absolute paths under the old server directory. The controller is deployed on the default macOS target, so it was redeployed with the fix.

- Dropped "mac" from the shared identifiers of the KakaoTalk skill and from the live Hermes config, since the repo now serves two backends: `kakaotalk-message/` → `kakaotalk-message/`, `openhuman-kakaotalk` → `openhuman-kakaotalk`, and the `kakaotalk.*` tool namespace → `kakaotalk.*`. The backend documents went the other way and gained an explicit `macos` marker, because with two backends the platform is information rather than noise.
- The tool namespace and the server name are one contract spanning the repo, the deployed server directory and `config.yaml`, so all three moved in a single window with the gateways down. Verified after restart: the old toolset name is now rejected, the new one resolves, `hermes doctor` reports no toolset warnings, and the gateway registered the same 19 tools under `mcp__openhuman_kakaotalk__`.
- Found and set aside a stale top-level `adapters/` copy inside the server directory that the sync script never touched and the entrypoint never imported; it still carried the old namespace and would have been a confusing false lead.

- Renamed the KakaoTalk skill repo to `kakaotalk-message-skill` (GitHub and local) now that it covers both platforms, and pointed the canonical-doc reference in this log at the new path. Nothing on the default macOS target had to change: it holds no clone of that repo and no `~/.openhuman/skills/`, and the deployed MCP servers under `~/.hermes/mcp-servers/` keep their names.
- Added a Linux backend to that skill, covering the redroid plus Iris path built here, with a backend-selection section at the top of `SKILL.md` because most of the macOS guidance does not apply. The skill directory and the MCP server name were renamed in a follow-up, together with the Hermes config change they are a contract with.

- Made the Android container a first-class service in the DGX AI Control app (`~/src/dgx-ai-control`, commit `07217a8`): Start / Stop / Restart / Logs plus `--android start|stop|restart|status`, with the binder prep, container start, boot wait and Iris launch behind one action. Measured ~9s to start, ~10s to stop.
- Restyled that app, which had no styling at all, and recorded the reasoning in its own `PRODUCT.md` and `DESIGN.md`. It is light rather than dark because it is seen over RDP inside a macOS window, where compression bands dark tonal steps.

- Deferred the messenger-assistant policy-engine port to a later session and recorded what it actually involves: the Mac controller's fail-closed guards are written against macOS adapter evidence (`NTUser.directChatId`, `userType`) that the Android schema does not supply in the same shape, so it is a rule rewrite rather than a transport swap.
- Wrote down the reboot-recovery order for the container, since the binder module, the binderfs mount and its `0666` permissions are all lost on a host reboot while the container and the KakaoTalk session survive in the bind mount.

- **Completed the round trip: Iris sends as well as reads.** `POST /reply` delivered a message into the target room, and it came back through the observer as a new `chat_logs` row (253 → 254), confirmed on screen.
- Resolved the `NotificationReferer` question: KakaoTalk 26.7.2 still writes the key, and it overwrote the injected placeholder with a real ~20-character token the moment an incoming message from another party raised a notification. No version incompatibility. Iris reads it once at startup, so it needs a restart whenever the referer changes.
- Recorded that Iris `/reply` returns `{"success":true}` merely for queuing the intent — with a bogus referer it says the same and nothing is sent, so sends must be verified against `chat_logs`, not the response body.

- **Ported the read half of the KakaoTalk assistant to the DGX.** Iris v0.32 runs in the redroid container and forwards live decrypted messages: a phone-sent `123` went KakaoTalk → encrypted DB → DBObserver → decrypted → HTTP, with `chat_logs` going 251 → 252. Recorded as [Iris On DGX](runbooks/iris-on-dgx.md).
- Two non-obvious blockers: `docker exec` has no Android environment so `app_process` exits silently (replicate it from `/proc/$(pidof system_server)/environ`, skipping `ANDROID_SOCKET_*`), and `Main.kt:18` reads `NotificationReferer` before anything else and kills the whole process when it is absent — even though only the send path uses it.
- The send path is left inert on purpose by injecting a bogus `NotificationReferer`, so nothing can leave the container by accident. A real referer needs an incoming notification from another party, which a self-sent message never produces.

- **Signed the DGX container in as a KakaoTalk companion device and it worked.** The tablet ("다른 기기와 함께 사용") login path reaches `MainActivity` with the real account and friend list. The phone kept its session; the Mac's KakaoTalk.app was evicted to a login window, which settles the open question: a tablet sub-device and the PC client share one companion slot.
- Reframed the device-slot finding: it blocks running the Mac client and the DGX in parallel, but it does not block migrating the assistant off the Mac, which needs no second account.
- Found the tablet gate to be device identity, not form factor: `sw800dp` plus `ro.build.characteristics=tablet` plus a `ko-KR` locale was not enough; the checkbox appeared only after `ro.product.model`/`brand`/`manufacturer` were also set to a tablet.
- Noted the QR and security code are each valid ~60s, so a chat round-trip for both will expire; and that the Android `KakaoTalk*.db` files are plain `SQLite format 3` at the file level (per-field encryption only), which is the shape Iris decrypts.

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
  `/Users/mac_al03241161/Documents/mygit/kakaotalk-message-skill/docs/hermes/kakaotalk-macos-mcp.md`.
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
