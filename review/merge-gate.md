# Merge gate

Every repo that calls the shared review workflow follows this gate. A repo's `AGENTS.md`
links here and lists only its own exceptions (see [Per-repo exceptions](#per-repo-exceptions)).

Before asking a maintainer to merge a pull request:

1. CI passes.
2. Codex has reviewed the final head commit and is clean, or its findings are answered. If it does not start on its own, comment `@codex review`. Keep that phrase out of PR descriptions, where it starts a Codex cloud task instead of a review. Codex is paused at its usage limit as of November 14, 2026: don't comment `@codex review` and don't wait for it, but if Codex does post a review on the final head commit, its findings must be answered.
3. The Claude review has run once, its summary starts "Claude review finished" or "Claude review posted", and its High and Medium findings are fixed or answered. A finding the summary counts as without a severity label counts as Medium. Answer Low findings in one batched reply or move them to a follow-up issue; don't reply to each one or push only to answer them. The review runs automatically only when a PR is opened or marked ready, and other pushes are not re-reviewed automatically. A re-review is an owner, member or collaborator comment whose first words are exactly `@claude review`; its findings follow the same rules. Request one when:
   - the run did not complete, or its summary says it is stale;
   - a later push meets a re-review trigger the repo's `AGENTS.md` lists;
   - a later push is otherwise substantial, after asking a maintainer.
4. A PR that edits its repo's caller (`.github/workflows/claude-review.yml`) also needs a run started by an owner, member or collaborator comment whose first words are exactly `@claude review`, because its automatic run uses the PR's own copy of that file. It must also show a successful automatic run on the final head commit before merge, since only that run uses the PR's copy: after a later push, mark the PR draft, then ready, but not with `GITHUB_TOKEN`, whose events don't start workflows. This is the one case that still needs the flip, and the findings from that run follow item 3's rules.
5. Any check the repo's `AGENTS.md` adds, such as live tests, has run, or the PR says plainly which are still needed.

Reviews don't run on closed or merged PRs, and a comment there is refused. A caller or shared workflow change first runs in full after it merges. No separate check follows: the next PR's review shows whether it works, and item 3 holds that PR until one completes.

When asking for the merge, report the CI and Claude results (and Codex's, when Codex is running) and how each finding was handled. A maintainer merges; agents do not. A local `/code-review high` is optional. Fork PRs don't get the Claude review, so a maintainer decides how to review them.

## Per-repo exceptions

A repo's `AGENTS.md` keeps a "Merge gate" section that links here and lists only what differs for that repo, for example:

- extra re-review triggers for item 3, such as changes to the areas its Code Review Rules cover;
- its merge method, if it allows only one;
- extra checks for item 5.

### Re-review cap

No limit on re-reviews is set here yet. If one is adopted, for every repo or for some, it goes in this section, and a repo-specific cap goes in that repo's "Merge gate" section.
