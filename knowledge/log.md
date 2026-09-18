# Knowledge Log

## 2026-09-18

- KakaoTalk replies went silent after the container restart although the daemon logged every send: KakaoTalk had only been started as a service and never brought to the foreground, so Iris's `REPLY_MESSAGE` `startService` was refused with `Background start not allowed` while `/reply` kept returning success. Fixed with `cmd deviceidle whitelist +com.kakao.talk` (AMS treats the allowlist as `APP_START_MODE_NORMAL`) plus `am start` of `SplashActivity`; recorded as step 4 of the reboot recovery.
- The 2026-09-18 KakaoTalk outage was lmkd, not Iris, KakaoTalk or netd. lmkd spun on `epoll_wait` returning `EINVAL`, never accepted on its socket, `system_server` blocked in `LmkdConnection`, Watchdog restarted the `main` class every ~90 s, and each restart left netd without a rule for table 1002. Memory pressure, Bluetooth and the log flood were each measured and ruled out; silencing the log tags cut logd from 100% to 12% and changed nothing.
- Root cause is upstream: Linux 6.9+ reports `EPOLLHUP` on a pidfd once the killed process is reaped (measured on this 6.17 host), and Android 14 lmkd treats any `EPOLLHUP` as a dropped data connection, closing system_server's socket and decrementing `maxevents` every loop until it is 0. AOSP `667fdbfe` fixed it in `android-15.0.0_r20`; no `android-14` tag has it. It needs an lmkd kill to trigger, and lmkd kills in this container because it reads the host's PSI — the first watchdog came 74 s after a YuE2 run was launched.
- Disarmed lmkd with the knob `lmkd.rc` already exposes: `persist.device_config.lmkd_native.psi_{partial,complete}_stall_ms=0`. Each setprop became `lmkd --reinit` over the socket; PSI fds went 2 → 1 → 0 with the lmkd pid unchanged. No monitors means no kills, no pidfd, no wedge, and no more container apps killed by host swap.
- The repair is `setprop ctl.restart lmkd` (5 s, `system_server` untouched, no critical-crash count), not `docker restart`, which dropped Iris and KakaoTalk and destroyed the fd evidence. `kill -9` also works but counts toward init's 4-in-4-minutes reboot. `setprop lmkd.reinit 1` cannot repair a wedge — its helper blocks reading the same deaf socket.
- Added `redroid/lmkd-watchdog.{sh,service,timer}`: two 5 s CPU samples, capture `/proc/<lmkd>/fd` and the lmkd log, then `ctl.restart`, at most once per 10 minutes.
- Upgrading the image would also remove the bug: redroid `15.0.0_64only-latest` is `android-15.0.0_r36` (`BP1A.250505.005.D1`, read from its layer) and the fix is in every 15 tag from r20 on, in no 14 tag. Not done: lmkd on 15 still reads the host's PSI so the `psi_*=0` knobs stay anyway, booting 15 on the 14 `/data` puts the KakaoTalk device-slot login at risk, and 16 would force Frida 17 and a hook rewrite.

## 2026-09-14

- There is no readable expiry for the KakaoTalk companion login in the DGX container, and the question has three separate answers that all land there: the DataStore credential file has no time field among its 36 keys, `OauthHelper` only refreshes after a request has already failed, and the status enum has no `TOKEN_EXPIRED`. Detection is the only option; prediction is not.
- The one endpoint that returns `expires_in`, `account/oauth2_token.json`, is a rotation rather than a read. Calling it to check the session invalidates the pair the container's KakaoTalk is still holding, so the check would cause the logout it was meant to anticipate.
- `sekdlak` in KakaoTalk's prefs is the screen-lock passcode, not the access token. It is the only credential-shaped string left in `shared_prefs`, which is exactly why it reads as the token; the real ones moved to a Jetpack DataStore.
- The LOCO socket check has to read `/proc/net/tcp6`. The connection is IPv4-mapped, so `/proc/net/tcp` reports zero every time and looks like a dead session.
- Moved the Mac-side role from the leftover `jarvis` profile to `mac-jarvis`. Six places had to follow, and only one of them was code: the messenger assistant already reads `profile`/`profile_dir` from its config.json, so the `"jarvis"` literals scattered through `messenger_assistant.py` are defaults that never fire.
- `install_messenger_assistant.py` was the real hazard - it hardcoded the profile in module constants, so the next install would have silently pulled everything back to `jarvis`. It reads `HERMES_MESSENGER_PROFILE` now. Its launchd labels and cron name stay as they are: those are registered identifiers, and renaming them orphans the installed agents.
- Not every "jarvis" in that codebase is a profile. `kakao_ai_chat.py`'s `speaker_for()` returns "jarvis" as the bot's display name in a chat transcript, matching `bot_prefix`. Grepping a name and replacing it everywhere would have renamed the bot in people's KakaoTalk rooms.
- mac-jarvis inherited the jarvis bot token rather than keeping its own restored one. The channel it polls was set up for that bot, and REST-polling it does not collide with the DGX's websocket - an arrangement already verified. Using the restored profile's own bot would have needed a human in the Discord UI, for a bot that may no longer exist.

## 2026-09-13

- Stood the Mac hermes stack down and went DGX-only. The prompt for it was a good question I had answered too fast: `메신저 시작` re-enables a *Mac* process, so "run everything from the DGX" and "the KakaoTalk assistant works" cannot both be true today.
- Three things block KakaoTalk from following the agent: the account's companion slot is held by Mac KakaoTalk.app, Iris is not serving on :3000 even though its process is up, and the policy engine's fail-closed guards read macOS-adapter evidence the Android schema does not supply. Only the third is real work.
- `launchctl bootout` does not stop a Hermes gateway at all — it answers "No such process" for a label `launchctl list` is printing. The other agents do boot out, but only from `gui/<uid>`; the same command against `user/<uid>` gives the identical error and sends you chasing the wrong thing.
- `bootout` alone is not "off": these agents carry `RunAtLoad`, and a resurrected `gateway-jarvis` would rejoin the channel the DGX now owns. `disable` them.
- `kakao_ai_chat` survives its own boot-out. It runs itself back through a local `ssh 127.0.0.1` because launchd has no TCC context, so launchd supervises the ssh and the Python child on the far side keeps polling.

- The DGX is a Hermes host now, not a candidate for one. Hermes Agent v0.21.2 installs per-user on Ubuntu 24.04 aarch64 with no sudo at all, and the gateway really is a systemd **user** unit (`hermes-gateway.service`, lingering already enabled). That last point was the open unknown the portability study left behind; it is answered.
- What actually cost time was never the install. `bin/hermes-remote` sshs to `$HERMES_REMOTE_HOST` verbatim while `install.sh`/`doctor.sh` build `user@host`, so a bare IP installs cleanly and then fails every subcommand with `Permission denied`. Putting the user in the host value satisfies both.
- Two stdin traps worth remembering: `hermes model` refuses a non-TTY outright, and `hermes config migrate` prompts — it will eat the remainder of an `ssh 'bash -s' <<EOF` script as its answer and the rest of your script silently never runs.
- Did not clone the Mac's `config.yaml` onto the DGX. The Mac is v0.20.6 / 699 lines, the DGX shipped v0.21.2 / 2138 commented lines; ported the identity-bearing sections with `hermes config set` (it takes JSON for nested keys, but rewrites a bare `model` to `model.default` and stores the JSON as a string) and let `config migrate` carry the version to 44.
- The macOS-only MCP servers went to `enabled: false` rather than being deleted, so the Linux port of each one is a path swap rather than an archaeology exercise.
- Split the Discord identity by host: the DGX holds it in its **default** profile (aliased `dgx-jarvis`) because `bin/hermes-remote` only passes `--profile` for Hallmark — a named profile there would leave 40 subcommands addressing an empty default.
- Recovered the `product` profile deleted on 2026-08-29 from `backups/pre-update-2026-08-29-163521.zip` and renamed it `mac-jarvis`. Its Discord channels are deliberately blank: the restored `.env` still pointed at the channel the DGX now owns, and a different bot answering on the same channel is the one failure this split exists to prevent.
- Those backup zips exclude every `.git` directory, so a restored profile's `skill-sources/` checkout has files and no history. Worth knowing before trusting one as a recovery source.
- `bin/hermes-remote`'s Hallmark commands had hardcoded the `product` profile and were therefore dead for two weeks without anyone noticing. They read `HERMES_HALLMARK_PROFILE` now.
- `hermes config migrate` does not drop `custom_providers` — it converts it into the v44 `providers.<name>` shape, after which `hermes config get custom_providers` answers `Config key not set`. That reads exactly like data loss and cost a round of re-adding a legacy block that then had to be removed as a duplicate.
- Copied the Mac's `.env` onto the DGX after all, and the runbook now says why: the "never copy" rule is for standing up an independent host, and dgx-jarvis is an identity migration — it has to present the same bot token and keys. Streamed it ssh-to-ssh so it never touched the operator's laptop. The one thing an `.env` copy misses is `providers.altalt.extra_headers.X-Machine-ID`, which lives in `config.yaml`.
- Cut the jarvis Discord identity over to the DGX. `launchctl bootout gui/<uid>/<label>` answers `Boot-out failed: 3: No such process` for a label `launchctl list` is happily printing; `hermes --profile <name> gateway stop` knows its own service target and just works.
- The cutover was safe for a reason I had not actually checked: channel …3051 was configured in three profiles, not two, and the third was inert only because someone had retired it back in June. Counting the profiles on a channel is a pre-flight step, not a post-mortem one.
- Verify a provider chain by calling each rung, not by reading the key list. `groq` answers on the Mac (v0.20.6) and returns 413 on the DGX (v0.21.2) with the same key and *fewer* skills loaded — a built-in tool schema difference, costing the third fallback rung.

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
