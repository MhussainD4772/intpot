# Changelog fragments

Every user-facing change gets a fragment file here instead of an edit to
`CHANGELOG.md`. At release time `towncrier` assembles them into a dated section and
deletes them, so nobody hand-edits the changelog and nobody resolves a merge conflict
in it.

## Adding one

Name the file `<pr-number>.<type>.md`, where type is one of `added`, `changed`,
`deprecated`, `removed`, or `fixed`:

```
changelog.d/45.fixed.md
```

Write one sentence describing what changed **for someone using intpot** — not what you
did to the code. Say what the behavior was before if that makes it clearer. Markdown
works, and the PR link is appended automatically, so don't add one:

```markdown
Async tools now run correctly under `intpot serve --cli` — the coroutine was
previously returned unawaited instead of executed.
```

If a change genuinely isn't user-facing (refactors, CI, formatting, test-only work),
skip the fragment and add the `skip-changelog` label to the PR.

## Previewing

```bash
make changelog-draft
```

This renders what the next release section will look like without touching anything.
