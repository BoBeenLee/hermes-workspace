# Hermes Remote Ops Context

## Language

**Hermes remote ops**:
The operating model for managing the Hermes MacBook from a Control MacBook over an approved SSH/Tailscale path. It includes diagnosis, gateway operations, computer_use setup, Kanban setup, incident triage, and workspace lifecycle work.
_Avoid_: generic automation repo, one-off SSH scripts

**Control MacBook**:
The local Mac where Codex/Desktop automation runs. It is the operator entry point for SSH, docs, and repo changes.
_Avoid_: local laptop, Claude Mac

**Hermes MacBook**:
The remote Mac that runs NousResearch `hermes-agent` for the user account.
_Avoid_: target machine, other Mac

**Hermes agent**:
The per-user Hermes install at `~/.hermes/hermes-agent`, with config/data/logs under `~/.hermes` and command wrapper at `~/.local/bin/hermes`.

**Remote access path**:
The SSH route from Control MacBook to Hermes MacBook. LAN hostnames and Tailscale aliases are access paths, not application state.

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
