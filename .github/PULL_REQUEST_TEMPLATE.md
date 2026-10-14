<!--
Thanks for the pull request. Delete any section that does not apply.
See CONTRIBUTING.md for setup and house style.
-->

## What this changes

<!-- One or two sentences. The diff says what; say why. -->

Closes #

## Type

- [ ] `fix` — a bug fix
- [ ] `feat` — new behaviour
- [ ] `docs` — documentation only
- [ ] `refactor` / `perf` — no behaviour change
- [ ] `build` / `ci` / `chore` — tooling and packaging
- [ ] `test` — tests only

## Display impact

The rendered output of the panels is a hard contract. Pick one:

- [ ] **No visual change.** `make parity` still passes (or skips — see below).
- [ ] **Deliberate visual change.** Before/after is below, the parity reference
      is updated in this PR, and there is a `### Changed` entry in the changelog.

<details>
<summary>Before / after (only for a deliberate visual change)</summary>

```
before:


after:

```

</details>

## Privileged commands

- [ ] Does not touch anything that runs as root.
- [ ] Adds or changes a privileged command. If so: it is built as an argv and
      passed through `Escalator.wrap()`, `--dry-run` prints it without running
      it, and `coffee doctor` reports it when it is unavailable.

## Checks

- [ ] `make ci` passes locally (version-check, ruff, compile, tests, smoke).
- [ ] `make parity` passes, or skips because no reference checkout is present
      — note which:
- [ ] Tests added or updated for the change.
- [ ] `CHANGELOG.md` updated under `[Unreleased]`.
- [ ] Added myself to `AUTHORS.md` (first-time contributors).

## Anything a reviewer should know

<!-- Trade-offs you made, things you were unsure about, what you did not do. -->
