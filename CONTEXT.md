# Hermes Workspace Context

## Language

**Hermes remote ops**:
The operating model for managing configured Hermes targets from a Control MacBook over an approved SSH/Tailscale path. It includes diagnosis, gateway operations, target profile selection, computer_use setup when supported, Kanban setup, incident triage, and workspace lifecycle work.
_Avoid_: generic automation repo, one-off SSH scripts

**Hermes workspace**:
The git-backed work management repository used by the remote Hermes agent. It stores task handoffs, research/report artifacts, workspace lifecycle rules, and the SSH-first ops toolkit for Hermes targets.
_Avoid_: ops scripts only, scratch repo

**Control MacBook**:
The local Mac where Codex/Desktop automation runs. It is the operator entry point for SSH, docs, and repo changes.
_Avoid_: local laptop, Claude Mac

**Hermes MacBook**:
The current default macOS Hermes target that runs NousResearch `hermes-agent` for the user account.
_Avoid_: only supported target, hardcoded destination

**Hermes target**:
A configured remote host that runs NousResearch `hermes-agent` and is selected through a target profile.
_Avoid_: hardcoded machine, one-off SSH destination

**Hermes agent**:
The per-user Hermes install at `~/.hermes/hermes-agent`, with config/data/logs under `~/.hermes` and command wrapper at `~/.local/bin/hermes`.

**Remote access path**:
The SSH route from Control MacBook to a Hermes target. LAN hostnames and Tailscale aliases are access paths, not application state.

**Target profile**:
The `config/targets/<name>.env` contract that defines a Hermes target's SSH host, OS, service manager, computer-use backend, Hermes paths, workspace root, and workspace repo.
_Avoid_: scattered host constants, MacBook hardcode

**Remote workspace manager**:
The profile-aware `bin/hermes-remote` command interface for remote target lifecycle work: SSH checks, status, gateway, Kanban, dashboard, logs, Discord thread triage, and OS/backend-specific setup.
_Avoid_: ad hoc remote command runner

**Computer-use backend**:
The target profile capability that determines whether desktop control commands are supported. `cua-driver` means macOS CuaDriver support; `none` means those commands should fail clearly.
_Avoid_: assuming every Hermes target has macOS desktop control

**Workspace Lifecycle module**:
The repo-level interface that every Hermes task follows: choose a task type, start in the canonical workspace root, work in an isolated worktree, produce required outputs, run checks, and finish as `done` or `review-required`.
_Avoid_: ad hoc task instructions, scattered prompt rules

**Research Analysis module**:
The interface for market research and analysis work. It owns the brief, source ledger, notes, and report artifacts for research-based tasks.
_Avoid_: loose notes, source-less summary

**Source ledger**:
The durable evidence list for research-based tasks. Each entry records source URL, title, publisher, retrieval time, relevance, and trust note.
_Avoid_: links section, references dump

**Review-required completion**:
A terminal task state for work that is implemented or drafted but needs human review before merge, gateway restart, key/auth/config change, or recurring automation.
_Avoid_: done when human action is still required
