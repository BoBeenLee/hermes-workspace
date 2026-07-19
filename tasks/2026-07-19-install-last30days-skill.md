# Install and verify last30days on Hermes

## Completion note

- Task type: `ops-change`
- HIL status: `skipped` - the request came directly from the user in Codex, not through Discord.
- Branch: `codex/install-last30days-hermes`
- Worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Completion mode: `review-required`

## Remote changes

- Target: SSH alias `bobeen`
- Installed source: `/Users/bobeenlee/.hermes/skills-src/last30days-skill`
- Installed skill link: `/Users/bobeenlee/.hermes/skills/research/last30days`
- Version: `3.16.0`
- Pinned commit: `249c7a4c040558a903d6838dee31012980d4946d`
- Install method: repository clone plus skill-directory symlink, following the upstream [Hermes setup guide](https://github.com/mvanhorn/last30days-skill/blob/main/HERMES_SETUP.md).

The normal Hermes installer did not install the skill. It resolved a stale cached snapshot containing `AISA_API_KEY` references, and the Hermes security scanner blocked that snapshot with a `DANGEROUS` verdict. The current pinned upstream commit did not contain those references. Scanning the current skill directory with the same Hermes scanner returned `CAUTION`; the scanner's force policy allowed that verdict. The current source was therefore installed through the upstream documented clone-and-symlink alternative.

## Verification

- `bin/hermes-remote check-ssh`: passed.
- `bin/hermes-remote status`: Hermes Agent `v0.18.2` up to date; gateway remained running under launchd.
- `hermes skills list`: `last30days` reported as `research`, `local`, and `enabled`.
- Skill preflight: `Ready to research with safe defaults`.
- Preflight confirmed browser-cookie access was off and no local writes were planned.
- Available preflight sources: Reddit, YouTube, Hacker News, Polymarket, GitHub, and grounding.
- No API keys, browser-cookie settings, Hermes configuration, gateway configuration, or recurring jobs were changed.
- No test one-shot or `last30days.py` processes remained after verification.

## Live research test

The installed Python engine was executed against `NousResearch Hermes Agent` for a seven-day window. The successful run completed in 87.4 seconds and returned:

- Reddit: 2 threads, 129 upvotes, 45 comments
- Hacker News: 1 story
- Jobs: 3 results, with partial coverage reported by the engine
- A valid `last30days v3.16.0` badge and source-coverage footer

The Python 3.13 runtime required `SSL_CERT_FILE=/etc/ssl/cert.pem` for standard-library HTTPS calls. This variable was scoped to the test process only and was not persisted.

## Known limitation

The installed engine works when invoked directly. Hermes one-shot natural-language attempts did not reach the engine:

1. The default `bin/hermes-remote run` path selected only the `computer_use` toolset, so the model reported that the runtime was unavailable.
2. A one-shot with `terminal,skills` still returned a synthetic report without calling the engine.
3. A one-shot with `--skills last30days` remained in the model phase for more than three minutes without starting `last30days.py` and was stopped.

Persisting the CA path, changing default one-shot toolsets, changing the model, or restarting the gateway were intentionally left for separate review because they would expand the remote configuration or script-change scope.

## Rollback

After review, rollback can remove the skill symlink and its pinned source clone. No gateway restart or configuration rollback is otherwise required.
