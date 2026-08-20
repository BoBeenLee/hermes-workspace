# Knowledge Log

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
