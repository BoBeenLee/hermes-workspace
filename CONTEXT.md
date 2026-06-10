# Hermes Workspace Context

## Language

**Hermes workspace**:
The operating model and canonical repo for managing the Hermes MacBook from a Control MacBook over an approved SSH/Tailscale path. It includes diagnosis, gateway operations, computer_use setup, Kanban setup, incident triage, and workspace lifecycle work.
_Avoid_: generic automation repo, one-off SSH scripts

**Control MacBook**:
The local Mac where Codex/Desktop automation runs. It is the operator entry point for SSH, docs, and repo changes.
_Avoid_: local laptop, Claude Mac

**Hermes MacBook**:
The remote Mac that runs NousResearch `hermes-agent` for the user account.
_Avoid_: target machine, other Mac

**DGX Spark**:
The user's NVIDIA DGX Spark / GIGABYTE AI TOP ATOM Linux workstation reachable on the LAN for SSH, DGX Dashboard, and remote desktop work. It is not the Hermes MacBook. Current observed access path is `bobeenlee@172.30.1.87` / `aitopatom-36a9.local`.
_Avoid_: assuming DGX operations use the Hermes MacBook tooling, treating the onboarding web UI as a permanent service

**DGX Dashboard**:
The NVIDIA dashboard service on the DGX Spark. It was observed bound to `127.0.0.1:11000` on the device and should be reached from the Control MacBook through an SSH tunnel unless the user explicitly asks for external binding.
_Avoid_: exposing dashboard externally by default, confusing with Hermes dashboard

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

**Discord HIL Gate**:
The human-in-the-loop clarification checkpoint Hermes uses before acting on ambiguous or risky Discord requests. Hermes uses the externally installed mattpocock `grill-me` skill to ask one question at a time, then waits for explicit approval before entering the Workspace Lifecycle.
_Avoid_: automatic execution from vague Discord prompts, local custom grill skill

**Approval Summary**:
The final Discord message Hermes posts after HIL clarification and before execution. It records the goal, scope/non-goals, target workspace or repo, expected changes, verification, and completion mode for human approval.
_Avoid_: implicit approval, informal "I'll do it" messages

**Antigravity delegated implementation**:
A supervised implementation flow where Hermes creates an isolated remote git worktree, starts Antigravity CLI as an implementation worker through the `antigravity-worker` MCP toolset or manual tmux path, and then verifies the resulting diff, checks, logs, and completion note before any merge or operational application.
_Avoid_: unattended Antigravity automation, gateway-owned Antigravity task

**New repository HIL gate**:
The approval checkpoint Hermes must use before creating a new GitHub repository, cloning a new service workspace, or changing deployment/provider configuration for a standalone product or service. Hermes may infer that a new repository is appropriate, but must ask the human to approve owner, repo name, visibility, stack, deployment target, and delegation mode before taking creation or setup actions.
_Avoid_: automatic repo creation, implicit product workspace setup

**Source ledger**:
The durable evidence list for research-based tasks. Each entry records source URL, title, publisher, retrieval time, relevance, and trust note.
_Avoid_: links section, references dump

**Review-required completion**:
A terminal task state for work that is implemented or drafted but needs human review before merge, gateway restart, key/auth/config change, or recurring automation.
_Avoid_: done when human action is still required
