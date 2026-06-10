# Discord Thread Triage

## Activation Rule

When asking Hermes to start work from Discord, post from the user's Discord account and mention `@Bob Hermes`. Do not use a bot account or webhook for this activation path, because Hermes is expected to react to the user-account mention.

Use this when a Discord message link looks like:

```text
https://discord.com/channels/<guild_id>/<channel_id>/<message_or_thread_id>
```

For Hermes gateway logs, the useful value is usually the thread/chat id. In Hermes logs it appears like:

```text
chat=<thread_id>
agent:main:discord:thread:<thread_id>:<thread_id>
```

Commands:

```bash
bin/hermes-remote is-working <thread_id>
bin/hermes-remote tail-thread <thread_id>
```

## Discord HIL Gate

Hermes should not start risky or underspecified work from Discord immediately. When a request is ambiguous or risky, use the externally installed mattpocock `grill-me` skill to clarify the request in the same Discord thread.

Use the gate when any of these are unclear or risky:

- goal, success criteria, target workspace, repo, or artifact
- whether the work is read-only or will change files, config, auth, keys, deployment, or recurring automation
- whether Antigravity should be delegated work
- whether a standalone service, app, site, tool, or repository may be needed
- whether current market, pricing, legal, product, or policy claims need web verification

Skip the gate for clear read-only status checks, log inspection, and simple incident triage.

During HIL:

- ask one question at a time with `grill-me`
- include Hermes' recommended answer with each question
- continue in the original Discord thread
- do not edit files, change remote config, restart the gateway, create repositories, deploy, change auth/keys, or start Antigravity

When clarification is complete, Hermes must post an Approval Summary before acting. The summary must include:

- goal
- scope and non-goals
- target workspace or repo
- expected changes, or state that the task is read-only
- verification commands or checks
- completion mode: `done` or `review-required`

Only after the user explicitly approves the Approval Summary may Hermes enter the Workspace Lifecycle flow. If the clarified task needs a standalone repo, continue with the New Repository HIL Gate in `docs/workspace-lifecycle.md` before creating or cloning anything.

Signs it is still working:

- a recent `inbound message` line without a later `response ready`
- a live `hermes` worker process beyond the gateway process
- a Kanban task in `running`

Signs it is done:

- `response ready` followed by `Sending response`
- no extra worker process
- Kanban counts show `running 0`
