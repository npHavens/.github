# npHavens/.github agent notes

Start with the README. This repository is public, and every calling repo runs the
reusable workflow from `main`, so a merge here changes every repo's review at once.

## Merge gate

This repository's own pull requests get no Claude or Codex review: it has no caller
workflow, by the maintainer's choice. Before asking a maintainer to merge, CI passes. When
asking, report the CI result. A maintainer merges; agents do not.

After a change to `claude-review-reusable.yml` or `review/review-standard.md` merges, the
author confirms the next review on an open PR in each calling repo. Reviews don't run on
closed or merged PRs. Calling repos first run a change after it merges, so one can break
until that check.

Prefer bug fixes, and ship any other improvement as its own small PR. A change to what
callers provide must keep every existing caller working at each step:

- Permissions: add them to every caller first. Remove them from callers only after the reusable workflow stops needing them.
- New secrets or inputs: declare them in the reusable workflow as optional, pass them from every caller, then depend on them.
- Removed secrets or inputs: make them optional and stop using them in the reusable workflow, drop them from every caller, then remove them.
- Triggers or the job-level `if:`: make the reusable workflow accept the old and new callers, update every caller, then remove the old handling.

## Code Review Rules

### Calling repos

- Flag any change that can break an existing caller before every caller has been updated: the steps above, a renamed `gate` or `review` job (branch protection in a calling repo can require `claude-review / review`), or a changed secret name.
- Flag a change that reads review rules from the PR instead of the calling repo's default branch, or the shared standard from anywhere but this workflow's own commit (`job.workflow_repository` at `job.workflow_sha`).

### Public repository

- Flag names of private repositories, local file paths, run IDs, tokens or session URLs. This repository is public and must stay generic: it describes "calling repos", not specific ones.
- Flag any community health file: `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `SUPPORT`, `GOVERNANCE`, `FUNDING.yml`, issue or pull request templates, at the root, in `docs/` or in `.github/`. GitHub uses a public `.github` repository's copies as defaults for every repo that has none of its own.
