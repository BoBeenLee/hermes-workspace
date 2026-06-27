---
type: Skill
title: Discord
description: Repo-local skill guidance for Discord operations and Hermes Discord thread triage.
resource: repo://hermes-workspace/knowledge/skills/discord.md
tags: [hermes, skill, discord]
timestamp: 2026-06-27T00:00:00+09:00
source_path: skills/discord.SKILL.md
---

# Discord

Use the generic `message` tool with `channel: "discord"`. There is no provider-specific Discord tool exposed to the agent.

This skill has two jobs:

- operate Discord messages, reactions, reads, searches, polls, pins, and threads through `message`
- route Hermes Discord requests through the workspace's triage and human-in-the-loop safety rules

## Tool Contract

Every `message` call for Discord includes:

```json
{
  "channel": "discord",
  "action": "..."
}
```

Prefer explicit IDs over names or inferred targets:

- `guildId`
- `channelId`
- `messageId`
- `userId`
- optional `accountId` for multi-account setups

Use targets this way:

- Send-like actions: `to: "channel:<id>"` or `to: "user:<id>"`
- Message-specific actions: `channelId: "<id>"` plus `messageId: "<id>"`
- If the action accepts either `to` or `channelId`, prefer `channelId` for message-specific work and `to` for send/read/search-like work.

Respect configured action gates such as `channels.discord.actions.*`. Some deployments keep higher-risk actions off by default, including roles, moderation, presence, and channel management. If the tool reports that an action is gated or disabled, say so and ask the user to enable it rather than trying alternate channels.

## Safety Defaults

- Never print, request, or store Discord tokens.
- Do not impersonate the user or claim to be a human.
- Confirm before destructive or public-impacting actions such as deleting messages, bulk posting, moderation, role changes, channel changes, or presence changes.
- Keep messages short, conversational, and low ceremony unless the user asks for a formal post.
- Do not use markdown tables in Discord comments; they are hard to read on mobile.
- Prefer a few small replies over one wall of text for live clarification.
- If a Discord request would change files, remote config, auth, keys, deployment, recurring automation, or gateway state, use the Hermes HIL gate before acting.

## Hermes Discord Triage

Use this path when the user gives a Discord URL or asks whether Hermes is working on a Discord request.

Discord message links usually look like:

```text
https://discord.com/channels/<guild_id>/<channel_id>/<message_or_thread_id>
```

For Hermes gateway logs, the useful value is usually the final ID in the link. Treat it as the thread/chat ID unless logs prove otherwise.

Run from the Hermes workspace on the control host:

```bash
bin/hermes-remote is-working <thread_id>
bin/hermes-remote tail-thread <thread_id>
```

Interpret state with [Discord Thread Triage](../workflows/discord-thread-triage.md):

- Recent inbound message without a later response usually means Hermes may still be working.
- A live Hermes worker process beyond the gateway process usually means work is active.
- Kanban `running` tasks mean work is active.
- `response ready` followed by `Sending response`, no extra worker, and Kanban `running 0` usually means the request is done.
- Errors in logs mean the request failed or is incomplete until verified.

When asking Hermes to start work from Discord, post from the user's Discord account and mention `@Bob Hermes`. Do not use a bot account or webhook for this activation path.

## Hermes HIL Gate

Use the human-in-the-loop gate when a Discord request is ambiguous, broad, risky, or may trigger durable changes.

Apply the gate when any of these are unclear:

- goal or success criteria
- target workspace, repo, branch, artifact, or host
- read-only versus write scope
- file, script, remote config, auth, key, deployment, gateway, or recurring automation impact
- whether Antigravity should be delegated work
- whether a standalone service, app, site, tool, or repository may be needed
- whether current market, pricing, legal, product, or policy claims need web verification

During the gate:

1. Ask one question at a time in the original Discord thread.
2. Include Hermes' recommended answer with each question.
3. Do not edit files, change remote config, restart the gateway, create repositories, deploy, change auth/keys, or start Antigravity.
4. After clarification, post an Approval Summary.
5. Start the Workspace Lifecycle flow only after explicit approval.

Approval Summary format:

```text
h2. Approval Summary

* Goal: ...
* Scope: ...
* Non-goals: ...
* Target workspace/repo: ...
* Expected changes: ...
* Verification: ...
* Completion mode: done | review-required
```

Use `review-required` for script changes, remote config changes, gateway changes, key/auth changes, recurring automation changes, new repos, deployment setup, provider configuration, and Antigravity delegation.

## Common Actions

Send a message:

```json
{
  "action": "send",
  "channel": "discord",
  "to": "channel:123",
  "message": "hello",
  "silent": true
}
```

Send with media:

```json
{
  "action": "send",
  "channel": "discord",
  "to": "channel:123",
  "message": "see attachment",
  "media": "file:///tmp/example.png"
}
```

Read recent messages:

```json
{
  "action": "read",
  "channel": "discord",
  "to": "channel:123",
  "limit": 20
}
```

React:

```json
{
  "action": "react",
  "channel": "discord",
  "channelId": "123",
  "messageId": "456",
  "emoji": ":white_check_mark:"
}
```

Edit:

```json
{
  "action": "edit",
  "channel": "discord",
  "channelId": "123",
  "messageId": "456",
  "message": "fixed typo"
}
```

Delete:

```json
{
  "action": "delete",
  "channel": "discord",
  "channelId": "123",
  "messageId": "456"
}
```

Create a poll:

```json
{
  "action": "poll",
  "channel": "discord",
  "to": "channel:123",
  "pollQuestion": "Lunch?",
  "pollOption": ["Pizza", "Sushi", "Salad"],
  "pollMulti": false,
  "pollDurationHours": 24
}
```

Pin:

```json
{
  "action": "pin",
  "channel": "discord",
  "channelId": "123",
  "messageId": "456"
}
```

Create a thread from a message:

```json
{
  "action": "thread-create",
  "channel": "discord",
  "channelId": "123",
  "messageId": "456",
  "threadName": "bug triage"
}
```

Search:

```json
{
  "action": "search",
  "channel": "discord",
  "guildId": "999",
  "query": "release notes",
  "channelIds": ["123", "456"],
  "limit": 10
}
```

Set presence, if enabled:

```json
{
  "action": "set-presence",
  "channel": "discord",
  "activityType": "playing",
  "activityName": "Hermes triage",
  "status": "online"
}
```

## Discord Writing Style

- Use direct, conversational language.
- Lead with the answer or current status.
- Name the next action plainly.
- For HIL questions, include the recommended answer in the same message.
- For status reports, include only the evidence needed: thread ID, latest state, relevant log signal, and next step.
- For code or command output, use short fenced blocks only when monospace formatting helps. Otherwise keep identifiers plain.

## Completion Notes

When reporting back outside Discord, include:

- what Discord action was taken, or why it was not taken
- target channel/thread/message IDs used
- whether a gate or approval was required
- any follow-up the user needs to approve
