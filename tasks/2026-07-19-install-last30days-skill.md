# Install and verify last30days on Hermes

## Completion note

- Task type: `ops-change`
- HIL status: `skipped` - the request came directly from the user in Codex, not through Discord.
- Branch: `main`
- Worktree: `/Users/mac_al03241161/Documents/mygit/bbl-ai-lab/hermes-workspace`
- Completion mode: `review-required`

## Remote changes

- Target: SSH alias `bobeen`
- Installed source: `/Users/bobeenlee/.hermes/skills-src/last30days-skill`
- Installed skill link: `/Users/bobeenlee/.hermes/skills/research/last30days`
- Jarvis profile skill copy: `/Users/bobeenlee/.hermes/profiles/jarvis/skills/research/last30days`
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
- No API keys, browser-cookie settings, authentication settings, or recurring jobs were changed.
- No test one-shot or `last30days.py` processes remained after verification.

## Live research test

The installed Python engine was executed against `NousResearch Hermes Agent` for a seven-day window. The successful run completed in 87.4 seconds and returned:

- Reddit: 2 threads, 129 upvotes, 45 comments
- Hacker News: 1 story
- Jobs: 3 results, with partial coverage reported by the engine
- A valid `last30days v3.16.0` badge and source-coverage footer

The Python 3.13 runtime required `SSL_CERT_FILE=/etc/ssl/cert.pem` for standard-library HTTPS calls.

## Discord end-to-end test

The skill was enabled for the Jarvis Discord profile and invoked from the signed-in Discord desktop app on this Mac with `/skill`, selecting `last30days`, and passing `Hermes Agent --days=7`.

- Enabled the `skills` toolset for the Jarvis Discord platform.
- Persisted `SSL_CERT_FILE=/etc/ssl/cert.pem` in the Jarvis profile environment. Backup: `/Users/bobeenlee/.hermes/profiles/jarvis/.env.bak.20260719-174756`.
- Restarted only the Jarvis gateway; the default, content, preflight, and product gateways remained running.
- The first Jarvis profile installation used a symlink, but the Hermes Discord adapter resolves skill paths and excludes resolved paths outside the profile scan root. Replacing the Jarvis-profile symlink with a real directory copy increased the Discord registry from 94 to 95 skills and made `last30days` selectable through autocomplete.
- Jarvis executed `last30days.py` through the terminal tool and attached the 50 KB raw artifact `/Users/bobeenlee/Documents/Last30Days/hermes-agent-raw.md` to Discord.
- The raw artifact identified itself as `last30days v3.16.0`, covered 2026-07-12 through 2026-07-19, and contained 21 evidence items: GitHub 8, Hacker News 2, Jobs 5, Reddit 3, and YouTube 3. Jobs coverage was partial; web returned no results.
- The Jarvis compact prose incorrectly said 43 items even though the attached engine artifact reported 21. The attached raw result is the authoritative test output.
- The Jarvis gateway remained healthy under launchd after the run, and no `last30days.py` process remained.

## Known limitations

The installed engine works when invoked directly. Hermes one-shot natural-language attempts did not reach the engine:

1. The default `bin/hermes-remote run` path selected only the `computer_use` toolset, so the model reported that the runtime was unavailable.
2. A one-shot with `terminal,skills` still returned a synthetic report without calling the engine.
3. A one-shot with `--skills last30days` remained in the model phase for more than three minutes without starting `last30days.py` and was stopped.

- The one-shot behavior remains unchanged; Discord works because `/skill` injects the skill instructions and the Jarvis Discord profile has the required toolsets.
- Jarvis's model-generated compact synthesis misstated the total evidence count. Consumers should use the attached raw artifact's `Stats` and `Source Coverage` sections for exact counts.
- X/Twitter was unavailable because no X credentials were configured. No credentials were created or changed during this task.

## Rollback

After review, rollback can remove the default-profile symlink, the Jarvis-profile skill directory, and the pinned source clone; restore the Jarvis environment from `/Users/bobeenlee/.hermes/profiles/jarvis/.env.bak.20260719-174756`; disable the Jarvis Discord `skills` toolset; and restart only the Jarvis gateway.
