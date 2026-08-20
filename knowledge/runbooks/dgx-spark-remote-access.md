---
type: Runbook
title: DGX Spark Remote Access
description: Runbook and entry point for the DGX Spark host: doc map, SSH, Tailscale, the account and service-control boundary, dashboard, model service, browser, shutdown, and remote desktop access.
resource: repo://hermes-workspace/knowledge/runbooks/dgx-spark-remote-access.md
tags: [dgx-spark, remote-access, linux]
timestamp: 2026-06-27T00:00:00+09:00
source_path: docs/dgx-spark-remote-access.md
---

# DGX Spark Remote Access

This guide records the working access path for the user's NVIDIA DGX Spark so future sessions can connect, inspect, and operate it without rediscovering the setup.

## Known Target

- Device: NVIDIA DGX Spark / GIGABYTE AI TOP ATOM
- Linux host: `aitopatom-36a9`
- LAN IP observed during setup: `172.30.1.87`
- Tailscale IP observed after setup: `100.103.30.62`
- SSH user: `bobeenlee`
- Primary interface observed on the device: `wlP9s9`
- DGX Dashboard service: bound on the device at `127.0.0.1:11000`

Do not commit passwords or private keys. Ask the user for the current password when an interactive SSH, sudo, RDP, or xrdp credential is needed.

## DGX Doc Map

This runbook is the entry point for anything on the DGX Spark. It owns the host, OS, network access, remote desktop, shutdown, the DGX Dashboard, and the local LLM service. The ComfyUI service layer is owned by a separate repo; do not restate its facts here.

| Topic | Owner | Path |
| --- | --- | --- |
| Host, SSH, Tailscale, RDP, shutdown, DGX Dashboard, `llama-local.service`, `dgx-ai-control` | this runbook | you are here |
| ComfyUI service internals: systemd unit, `COMFY_ROOT` / `COMFY_VENV`, model directories, the `comfyops` account, `sudo /usr/local/sbin/comfyui-ops`, the MCP target | `remote-comfyui` repo | `references/dgx-comfyui.md` |
| ComfyUI generation workflows, model recommendations, run packages | `remote-comfyui` repo | `docs/`, `knowledge/` |

Under the `bbl-ai-lab` superproject checkout, `remote-comfyui` is mounted at `ops/remote-comfyui/`.

## What Happened During First Setup

The sticker on the device showed an initial hotspot and setup address like:

```text
SSID: AITOPATOM-3649
URL: http://AITOPATOM-3649.local
```

After initial setup and update, that hotspot was no longer visible from the Control MacBook. The device appeared on the LAN as:

```text
aitopatom-36a9.local
172.30.1.87
```

The initial setup web UI on port `80` was available during onboarding, then stopped responding after setup completed. That is expected: the OS stayed alive and SSH remained reachable, while the temporary setup UI closed.

## Quick Status Check

From the Control MacBook:

```bash
ping -c 3 172.30.1.87
nc -vz -G 5 172.30.1.87 22
nc -vz -G 5 172.30.1.87 3389
curl -sS -i --max-time 5 http://172.30.1.87/
```

Expected steady state:

- SSH `22`: open
- HTTP `80`: usually closed after onboarding
- RDP `3389`: open if xrdp or GNOME Remote Desktop is enabled

SSH login:

```bash
ssh bobeenlee@172.30.1.87
```

Tailscale SSH login after the device is joined to the tailnet:

```bash
ssh -i ~/.ssh/id_ed25519_bobeenlee_nopass bobeenlee@100.103.30.62
```

Useful remote checks:

```bash
hostname
ip -brief addr
uptime
systemctl --no-pager --failed
nvidia-smi
ss -ltnp | grep -E ':(22|80|3389|11000)'
```

## Tailscale Access

Tailscale was installed from the official Ubuntu `noble` apt repository on the DGX Spark. The system service is `tailscaled`, and the observed tailnet address is:

```text
100.103.30.62
```

Check status from the DGX:

```bash
tailscale status
tailscale ip -4
systemctl --no-pager status tailscaled
```

From the Control MacBook, SSH over Tailscale works with the existing DGX key:

```bash
ssh -i ~/.ssh/id_ed25519_bobeenlee_nopass bobeenlee@100.103.30.62
```

Keep local web services bound to loopback on the DGX and access them with SSH tunnels over Tailscale:

```bash
ssh -i ~/.ssh/id_ed25519_bobeenlee_nopass \
  -L 8080:127.0.0.1:8080 \
  -L 8188:127.0.0.1:8188 \
  bobeenlee@100.103.30.62
```

Then open:

```text
http://127.0.0.1:8080/v1/models
http://127.0.0.1:8188
```

Do not expose `llama-server`, ComfyUI, or the DGX Dashboard directly with `tailscale serve` unless the user explicitly asks.

## Hermes Provider Path

Use [Local LLM Providers](../tools/local-llm-providers.md) when the DGX Spark model service should back a Hermes Agent provider.

Preferred pattern:

```text
Hermes host -> SSH tunnel -> DGX loopback model server -> /v1 endpoint
```

Keep the model server bound to DGX loopback, then create a tunnel from the machine where Hermes can reach the forwarded port. If Hermes runs on the control host, this is enough:

```bash
ssh -N \
  -L 8000:127.0.0.1:8000 \
  bobeenlee@172.30.1.87
```

Then register the Hermes custom endpoint:

```text
http://127.0.0.1:8000/v1
```

If Hermes runs on another remote Hermes host, create the tunnel from that Hermes host or forward to a port reachable from that host. Do not assume a tunnel opened on the control host is visible inside a separate remote Hermes host.

Verify before changing Hermes provider config:

```bash
curl -sS http://127.0.0.1:8000/v1/models
bin/hermes-remote check-llm-endpoint http://127.0.0.1:8000/v1
```

Provider changes are `remote-config` work and should finish as `review-required`.

## Accounts And Control Paths

Two accounts operate this DGX. Know which one you are before running anything.

| Account | Role | sudo | Owns |
| --- | --- | --- | --- |
| `bobeenlee` | owner and desktop session | in the `sudo` group, no `NOPASSWD` entry | the `--user` systemd units (`llama-local.service`, `comfyui.service`), `/home/bobeenlee/src/ComfyUI`, `/home/bobeenlee/venvs/comfyui`, `/home/bobeenlee/models`, the GNOME session |
| `comfyops` | restricted ComfyUI service account used by the `remote-comfyui` repo | `NOPASSWD: /usr/local/sbin/comfyui-ops` only | nothing; its home is `/home/comfyops` |

Both accounts are members of the `comfyui-ops` group, and the sudoers drop-in is `/etc/sudoers.d/comfyops-comfyui`. `comfyops` does not own the ComfyUI tree, so `$HOME`-relative ComfyUI paths are wrong under `comfyops`. The literal paths on this device are `/home/bobeenlee/src/ComfyUI` and `/home/bobeenlee/venvs/comfyui`; the deployed `/usr/local/sbin/comfyui-ops` carries the same values as its `OWNER_USER`, `COMFY_ROOT`, and `COMFY_VENV` defaults.

Three control paths exist for `comfyui.service`, and all three end at the same unit, `bobeenlee`'s user unit:

1. As `bobeenlee` over SSH: `systemctl --user restart comfyui.service`.
2. In the local desktop session: the `dgx-ai-control` GTK app, which uses `systemctl --user` only, with no sudo and no ports.
3. As `comfyops`: `sudo /usr/local/sbin/comfyui-ops restart`, which runs `runuser -u bobeenlee -- systemctl --user restart comfyui.service`. This is what `remote-comfyui`'s `bin/comfyui-ops restart` calls.

Pick one path per session; do not interleave them.

Port `8188` is reached with an SSH `-L` tunnel; see [Tailscale Access](#tailscale-access) for the tunnel and the `tailscale serve` rule. Two equivalent tunnels exist: the owner tunnel in that section, and `bin/comfyui-ops connect` in `remote-comfyui`, which forwards the same port over the `comfyops` account. Both land on `http://127.0.0.1:8188`. The agent and MCP target `http://dgx-comfyui.localhost:8188` is that same local port, because `*.localhost` resolves to loopback. Do not rename that host: it is hard-coded in `remote-comfyui`'s `.codex/config.toml` and in the Claude Code `comfyui-mcp` registration.

## Local AI Services

`llama-server` is configured as a single selected-model user service. Only one local LLM is served at a time on `127.0.0.1:8080`; model selection is handled by `dgx-ai-control`.

```bash
~/.local/bin/dgx-ai-control models
~/.local/bin/dgx-ai-control current-model
~/.local/bin/dgx-ai-control select-model gemma4
~/.local/bin/dgx-ai-control select-model laguna-s-2.1
~/.local/bin/dgx-ai-control select-model qwen3.6-35b-a3b-nvfp4
systemctl --user status llama-local.service
```

Current model registry:

- `gemma4`: `/home/bobeenlee/models/gemma-4-26b-a4b-it/gemma-4-26B-A4B-it-UD-Q6_K.gguf`, context `131072`
- `laguna-s-2.1`: `/home/bobeenlee/models/laguna-s-2.1/laguna-s-2.1-Q4_K_M.gguf`, context `262144`, with `/home/bobeenlee/models/laguna-s-2.1/laguna-s-2.1-DFlash-BF16.gguf`
- `qwen3.6-35b-a3b-nvfp4`: `/home/bobeenlee/models/qwen3.6-35b-a3b-nvfp4/Qwen3.6-35B-A3B-NVFP4.gguf`, context `65536`

Laguna uses the isolated Poolside build at `/home/bobeenlee/src/llama.cpp-poolside-laguna/build/bin/llama-server`; the existing llama.cpp build remains unchanged. Its registry entry enables full CUDA offload, Q8_0 K/V cache, Jinja, preserved reasoning, and DFlash speculative decoding. A 2026-07-26 three-run fixed coding benchmark improved median generation from `26.74 tok/s` without DFlash to `38.09 tok/s` with DFlash, and reduced median response time from `9.699s` to `6.867s`.

Live check on 2026-07-26 KST loaded Laguna successfully with one `262144`-token slot and loopback-only `127.0.0.1:8080`. Initial cold load took about `266s`; DFlash registered with block size `16` and passed chat, thinking, tool-call, and tool-result follow-up checks without assistant-token leakage. Loading populated about `1.3GiB` of swap transiently, but post-load checks showed no sustained swap I/O or memory pressure. The task finished with `gemma4` selected, `llama-local.service` inactive and disabled, and port `8080` closed.

ComfyUI is configured as an enabled user service and should start automatically after boot because lingering is enabled for `bobeenlee`:

```bash
loginctl show-user bobeenlee -p Linger
systemctl --user status comfyui.service
systemctl --user restart comfyui.service
journalctl --user -u comfyui.service -n 100 --no-pager
```

ComfyUI service internals, meaning the systemd unit file, `COMFY_ROOT`, `COMFY_VENV`, the model directories, the `comfyops` account, and the guarded ops wrapper, are owned by the `remote-comfyui` repo (`references/dgx-comfyui.md`). Do not restate them here.

Both services are intended to bind only to loopback:

```bash
ss -ltnp | grep -E ':(8080|8188)'
```

The DGX desktop also has a local GTK control app for these services:

```bash
dgx-ai-control
dgx-ai-control --check
```

Installed paths:

```text
/home/bobeenlee/src/dgx-ai-control
/home/bobeenlee/.local/bin/dgx-ai-control
/home/bobeenlee/.local/share/applications/dgx-ai-control.desktop
```

The app can select the active local LLM model, restart the single `llama-local.service` slot, and start, stop, restart, or toggle boot auto-start for `llama-local.service` and `comfyui.service`. It uses only `systemctl --user`, stores no sudo password, and does not expose any network ports.

## Shutdown and Power Off

Confirm the box is idle before powering it off:

```bash
uptime
nvidia-smi
curl -sS --max-time 5 http://127.0.0.1:8188/prompt
loginctl list-sessions
ps -eo pid,user,etime,args | grep -Ei 'llama-|hf |huggingface|wget|rsync|cmake|train' | grep -v grep
find ~/src/ComfyUI/output ~/models -mmin -120 -type f 2>/dev/null | head
```

Idle looks like load average near `0.00`, GPU util `0%` with only the ComfyUI Python process and `Xorg`/`gnome-shell` holding GPU memory, `{"exec_info": {"queue_remaining": 0}}` from the ComfyUI prompt endpoint, no transfer or build processes, and no writes under `output/` or `models/` in the recent window.

Power off from the Control MacBook. `bobeenlee` is in the `sudo` group but has no `NOPASSWD` entry, so shutdown needs the user's password at an interactive prompt; allocate a TTY with `ssh -t`:

```bash
ssh -t -i ~/.ssh/id_ed25519_bobeenlee_nopass bobeenlee@100.103.30.62 'sudo shutdown -h now'
```

Non-interactive paths fail, so an agent session cannot power the device off unattended (measured 2026-08-19 KST):

```text
sudo -n shutdown -h now   ->  sudo: 암호가 필요합니다
systemctl poweroff        ->  Call to PowerOff failed: Interactive authentication required.
```

polkit refuses the power-off request from a remote SSH session, so `systemctl poweroff` needs either the local desktop session on `tty1` (GNOME power menu) or the same interactive password. `/etc/sudoers.d/comfyops-comfyui` covers only ComfyUI service operations for the `comfyui-ops` group and does not grant power-off. To make remote shutdown unattended, the user has to add a sudoers drop-in such as `bobeenlee ALL=(root) NOPASSWD: /sbin/shutdown, /sbin/poweroff`; treat that as `review-required`.

After the next boot, verified state on 2026-08-19: `Linger=yes` for `bobeenlee`, so `comfyui.service` is `enabled` and starts on its own, while `llama-local.service` stays `disabled` and `inactive`. Re-select a model with `dgx-ai-control select-model <name>` when the local LLM is needed, and re-open any SSH tunnels; nothing is served off loopback.

## DGX Dashboard

The DGX Dashboard service was observed running locally on the device:

```text
127.0.0.1:11000
```

Check it from SSH:

```bash
curl -sS -i --max-time 3 http://127.0.0.1:11000/ | head -40
systemctl --no-pager status dgx-dashboard dgx-dashboard-admin
```

Expose it to the Control MacBook with an SSH tunnel:

```bash
ssh -N -L 11000:127.0.0.1:11000 bobeenlee@172.30.1.87
```

Then open:

```text
http://127.0.0.1:11000/
```

Do not bind the dashboard externally unless the user explicitly asks.

## Remote Desktop

Two RDP paths were tested.

### GNOME Remote Desktop

GNOME Remote Desktop is present, but Windows App on macOS failed against the system GNOME RDP flow with logs like:

```text
[RDP] Sending server redirection
[DaemonSystem] Not found routing token on remote_clients list
ERRINFO_LOGOFF_BY_USER
```

If using GNOME Remote Desktop anyway, inspect status:

```bash
sudo grdctl --system status
systemctl --no-pager status gnome-remote-desktop.service
journalctl -u gnome-remote-desktop.service --no-pager -n 80
```

The system daemon needs readable TLS material owned by `gnome-remote-desktop`:

```bash
sudo mkdir -p /etc/gnome-remote-desktop
sudo openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /etc/gnome-remote-desktop/rdp.key \
  -out /etc/gnome-remote-desktop/rdp.crt \
  -days 365 \
  -subj '/CN=aitopatom-36a9.local'
sudo chown gnome-remote-desktop:gnome-remote-desktop /etc/gnome-remote-desktop/rdp.key /etc/gnome-remote-desktop/rdp.crt
sudo chmod 600 /etc/gnome-remote-desktop/rdp.key
sudo chmod 644 /etc/gnome-remote-desktop/rdp.crt
```

Then configure, substituting credentials provided by the user at runtime:

```bash
sudo grdctl --system rdp set-tls-cert /etc/gnome-remote-desktop/rdp.crt
sudo grdctl --system rdp set-tls-key /etc/gnome-remote-desktop/rdp.key
sudo grdctl --system rdp set-credentials bobeenlee '<password>'
sudo grdctl --system rdp disable-port-negotiation
sudo grdctl --system rdp enable
sudo systemctl restart gnome-remote-desktop.service
```

If Windows App still fails with routing token or redirection errors, use xrdp instead.

### xrdp Fallback

xrdp avoids the GNOME Remote Desktop routing-token failure by creating an RDP/Xorg session directly.

Current preferred RDP path: use `xrdp`. `gnome-remote-desktop.service` was disabled because it can race with `xrdp` for port `3389` at boot. When both are enabled, `xrdp` may fail with a bind error and the Control MacBook sees `3389` as closed.

Install:

```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y xrdp xorgxrdp
```

If `gnome-remote-desktop` already owns port `3389`, stop or disable it first:

```bash
sudo systemctl stop gnome-remote-desktop.service
sudo systemctl disable gnome-remote-desktop.service
sudo grdctl --system rdp disable || true
```

Fix the common xrdp TLS key permission issue:

```bash
sudo adduser xrdp ssl-cert
sudo systemctl restart xrdp xrdp-sesman
```

Make the user's RDP login start an Ubuntu GNOME session:

```bash
printf 'gnome-session --session=ubuntu\n' > ~/.xsession
chmod 600 ~/.xsession
```

Verify:

```bash
systemctl --no-pager status xrdp xrdp-sesman
systemctl is-enabled xrdp xrdp-sesman gnome-remote-desktop.service
ss -ltnp | grep -E ':(3389|3350)'
journalctl -u xrdp -u xrdp-sesman --no-pager -n 80
```

From Windows App or Microsoft Remote Desktop on the Control MacBook:

```text
PC name: 172.30.1.87
Username: bobeenlee
Password: ask the user
```

Prefer direct `172.30.1.87` access over an SSH tunnel for RDP. The direct port was reachable on the LAN, and tunneling through `127.0.0.1:<port>` made the GNOME RDP redirection path harder to diagnose.

## Browser Installation Note

The user's downloaded file was found at:

```text
/home/bobeenlee/다운로드/google-chrome-stable_current_amd64.deb
```

The DGX Spark is `arm64`, while that package is `amd64`:

```bash
dpkg --print-architecture
dpkg-deb -f /home/bobeenlee/다운로드/google-chrome-stable_current_amd64.deb Package Architecture Version
```

Do not install the amd64 Google Chrome `.deb` on this device. Use the arm64 Chromium snap instead:

```bash
sudo snap install chromium
command -v chromium
chromium --version
```

Observed working install:

```text
/snap/bin/chromium
Chromium 149.0.7827.53 snap
```

## Troubleshooting Signals

- `HTTP 80 connection refused`: usually the temporary onboarding UI is closed, not a dead device.
- `SSH 22 open but HTTP 80 closed`: OS is up; use SSH or dashboard tunnel.
- Windows App `0x207`: inspect server logs immediately; in the observed case, GNOME RDP redirection failed.
- xrdp log says `Cannot read private key file /etc/xrdp/key.pem: Permission denied`: add `xrdp` to `ssl-cert` and restart xrdp.
- `AITOPATOM-3649.local` does not resolve after setup: likely the initial hotspot is gone; use `aitopatom-36a9.local` or `172.30.1.87`.

## Safety

- Do not store or commit the user's SSH/RDP password.
- Keep RDP exposed only on trusted LANs. Prefer SSH tunnels for dashboard/admin web surfaces.
- Treat package installs and remote desktop daemon changes as `review-required` if they are part of a formal Hermes task.
