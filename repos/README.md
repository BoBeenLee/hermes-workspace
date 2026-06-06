# Repos

Use this directory as an inventory area for project-specific notes or local checkouts that remote Hermes agents work on.

Do not commit cloned third-party repositories here unless they are intentionally part of this repository. Prefer adding a small README or `.env` profile under `projects/` that points at the remote checkout path.

Example layout:

```text
repos/
  landing-page/
    README.md       # describes remote checkout, deploy command, and Discord thread
projects/
  bobeen.env        # remote Hermes target
```
