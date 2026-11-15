# npHavens/.github

Shared pull request review tooling for npHavens repositories:

- [`.github/workflows/claude-review-reusable.yml`](.github/workflows/claude-review-reusable.yml):
  the Claude review job. It runs the built-in `/code-review high` on a pull request and
  posts each finding as an inline comment labeled `[High]`, `[Medium]` or `[Low]`, then a
  summary comment. Calling repos run it from a small caller workflow.
- [`review/merge-gate.md`](review/merge-gate.md): the merge gate every calling repo follows
  before a maintainer merges.
- [`review/review-standard.md`](review/review-standard.md): the review standard the
  reviewer applies in every calling repo, together with that repo's own Code Review Rules.

Calling repos use `@main`, not a pinned commit, by the maintainer's choice: a merge here
reaches all of them at once with no bump PR in each, and a bad merge breaks all of them at
once. A change that needs more from callers, such as a new permission, secret or input, is
held back until every caller has been updated (the steps are in `AGENTS.md`), so a caller
copied from here keeps working. `main` requires a pull request and passing CI, applies those
rules to admins, and blocks force pushes and deletion. This repository has no caller, so its own pull requests get CI but no review.

## Calling the review from a repo

1. Copy [the caller](review/claude-review.yml) unchanged to
   `.github/workflows/claude-review.yml`.
2. Add a `CLAUDE_CODE_OAUTH_TOKEN` repository secret.
3. Put the repo's own review rules under a "Code Review Rules" heading in the root
   `AGENTS.md`, a nested `AGENTS.md`, or a `CODE_REVIEW.md` an `AGENTS.md` points to.
   The job restores `AGENTS.md`, `CLAUDE.md`, `CLAUDE.local.md` and `CODE_REVIEW.md` from
   the default branch at any depth, so a pull request cannot rewrite its own review rules.
   Rules kept anywhere else would be read from the pull request.
4. Give the repo's `AGENTS.md` a "Merge gate" section that links to the shared merge gate
   and lists only the repo's exceptions.
5. Open the pull request. Its automatic review is the live run that shows the caller works
   (merge gate item 4).

Same-repo pull requests are reviewed when opened or marked ready, and an owner, member or
collaborator can request another review on an open pull request with a comment that starts
`@claude review`. Closed and merged pull requests are never reviewed. Fork
pull requests are never reviewed, because the reviewer holds a token that can write to the
repo's pull requests.

## Tests

```sh
python3 -m unittest discover -s Tests -p 'test_*.py'
```

The tests run the workflow's own shell steps against a stubbed `gh`, so they need only
`bash`, `jq` and Python 3. CI runs them on every pull request and on pushes to `main`.

## Community health files

This repository has none, on purpose. GitHub uses a public `.github` repository's
`CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `SUPPORT`, `GOVERNANCE`, `FUNDING.yml` and
issue or pull request templates as defaults for every repo of the account that lacks its
own, so adding one here would change those repos.
