---
type: Tool
title: Hermes Mac Manager
description: SwiftUI operator app for managing the remote macOS Hermes host, including gateway, local LLM, logs, and optional power scheduling.
resource: repo://hermes-workspace/knowledge/tools/hermes-mac-manager.md
tags: [hermes, macos, tool, launchd, power]
timestamp: 2026-07-05T20:33:00+09:00
---

# Hermes Mac Manager

Hermes Mac Manager is a small SwiftUI operator app under `apps/HermesMacManager/`. It wraps local shell commands for the active macOS user account and is built with:

```bash
scripts/hermes/build-hermes-mac-manager.sh
```

Use it for quick host operations such as Hermes gateway control, local LLM endpoint checks, log access, and the optional macOS power schedule controls.

## Power Schedule

The Power Schedule section is disabled by default. It does not change host power settings until the user clicks Apply.

Default window:

- Start: `10:00`
- Sleep: `20:00`
- Days: `MTWRFSU`
- Mode: wake or power on at start, sleep at end

Apply uses a macOS administrator prompt through AppleScript and then runs:

```bash
pmset repeat wakeorpoweron MTWRFSU 10:00:00 sleep MTWRFSU 20:00:00
```

It also installs a user-level LaunchAgent:

```text
~/Library/LaunchAgents/ai.hermes.mac-manager.power-window.plist
```

The LaunchAgent starts `/usr/bin/caffeinate -i -t <duration>` at the configured start time so the Mac stays awake during the server window. The duration ends five minutes before the scheduled sleep time so the 20:00 sleep event is not blocked.

Disable unloads and removes the LaunchAgent, then asks for administrator approval before running:

```bash
pmset repeat cancel
```

## Safety Notes

- `pmset repeat` has one system-wide repeating schedule slot. Applying this feature replaces any existing repeating power schedule.
- Power schedule changes and LaunchAgent changes are operational changes and finish as `review-required`.
- Prefer sleep over shutdown for the remote Mac so the logged-in user session and user-level Hermes services can resume after wake.
- Verify without applying changes through the app Refresh output, which includes `pmset -g sched` and LaunchAgent status.
