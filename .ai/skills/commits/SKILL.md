---
name: commits
description: >-
  Use whenever you write a git commit message in this repo — before running
  `git commit`, drafting a message for the user, or squashing/rewording. Commit
  subjects MUST use a Conventional Commits type prefix (feat, fix, chore,
  refactor, docs, style, test, perf, ci, build, revert). Covers the allowed
  types, when each applies, and the subject/body format. Invoke before composing
  any commit message.
---

# Commit messages

For consistency, every commit message subject starts with one of the types
below, in the form:

```text
<type>: <short imperative summary>
```

Keep the summary in the imperative mood ("add", not "added"/"adds") and under
~72 characters. Add a blank line and a body when the change needs explanation
(what and why, not how); bullet points are fine for multi-part changes.

## Commit message types

```text
feat:       a new feature is introduced with the changes
fix:        a bug fix has occurred
chore:      changes that do not relate to a fix or feature and don't modify source or test files (for example bumping dependencies in pyproject.toml / uv.lock)
refactor:   refactored code that neither fixes a bug nor adds a feature
docs:       updates to documentation such as the README, CLAUDE.md, or the .ai/ skills and rules
style:      changes that do not affect the meaning of the code, likely related to formatting such as whitespace or import ordering (ruff format / ruff --fix)
test:       including new or correcting previous tests
perf:       performance improvements
ci:         continuous integration related
build:      changes that affect the build system or external dependencies (Dockerfile, docker-compose, pyproject build config)
revert:     reverts a previous commit
```

## Picking the type

- Pick the type that matches the **primary intent** of the change.
- A new user-facing capability is `feat:`; correcting broken behavior is `fix:`.
- Dependency bumps that don't touch source/tests are `chore:`; if they change the
  build system (Dockerfile, compose, packaging), prefer `build:`.
- Pure formatting (`ruff format`, whitespace, import ordering) is `style:`;
  moving/renaming code with no behavior change is `refactor:`.
- Markdown docs — README, CLAUDE.md, `.ai/` skills and rules — are `docs:`.

## Examples

```text
feat: add cookie-based JWT auth for web clients
fix: prevent logout when refresh token is still valid
chore: bump django to 5.2.1 in uv.lock
refactor: extract token delivery into authentication.utils
docs: document social sign-in env vars in README
style: apply ruff formatting across apps
test: cover enumeration-safe registration flow
```
