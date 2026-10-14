# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
as scoped in [VERSION.md](VERSION.md) — the public API is the command-line
surface and the rendered display, not the Python modules.

## [Unreleased]

## [0.2.0] - 2026-10-13

### Added

- **Dashboard hotkeys.** `r`/`R` refreshes every panel immediately, bypassing
  the battery cache and the refresh timers. `q`/`Q` quits. Any other key floats
  a hotkey help popup over the centre of the panels; `Esc` closes it, or quits
  when no popup is open. Arrow and function keys (escape *sequences*) and
  Alt+key are told apart from a bare `Esc`, so they open the help instead of
  quitting. The README lists the keys.
- `coffee.keys` (key decoding and the reader thread) and `coffee.overlay`
  (the popup, and a renderable that composites it over the dashboard).
- `AUTHORS.md`, `VERSION.md` and this changelog.
- Contributor documentation: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
  (Contributor Covenant 2.1) and `SECURITY.md`, with private vulnerability
  reporting enabled on the repository.
- GitHub issue forms (bug report, feature request) and a pull-request template.
- `ci` workflow — ruff on Linux, then compile, unit tests, smoke run and a
  wheel build on an Apple Silicon macOS runner.
- `release` workflow — building and publishing artefacts when a `v*` tag is
  pushed.
- `claude` and `claude-code-review` workflows, for `@claude` mentions on issues
  and pull requests and for automated review of incoming changes.
- Dependabot, keeping GitHub Actions and Python dependencies current.
- Secret scanning with push protection, Dependabot security updates and
  private vulnerability reporting, enabled on the repository.
- `.editorconfig` and a `.pre-commit-config.yaml` running ruff plus the usual
  whitespace and syntax hooks.
- `CITATION.cff`, so the repository can be cited.
- `make version-check`, which fails when `VERSION.md` and `pyproject.toml`
  disagree; wired into `make ci`.
- `make pre-commit` and `make hooks`, to run and install the hooks.
- `scripts/check_glyph_escapes.py` and `make glyphs` — a guard that fails when
  a Nerd Font glyph is written as a literal character instead of a `\uXXXX`
  escape. These are Private Use Area codepoints that no editor renders
  reliably, so a literal one can be substituted or dropped by a tool and
  change the display with nothing visible in the diff. `--fix` rewrites them.
  Runs in `make lint`, in CI, and as a pre-commit hook.

### Changed

- **Only `q`, `Q` and `Esc` quit the dashboard.** Previously any key did; a
  stray keypress now opens the help instead of ending the session. `Ctrl-C`
  and `SIGTERM` still quit. With no popup open, the display is unchanged.
- The keyboard reader stops when the dashboard exits instead of being left
  blocked in `read()`, so it can no longer swallow the first keystroke typed
  at the shell afterwards.
- `coffee doctor` and `--help` describe the hotkeys rather than "press any key
  to quit".
- `README.md` now opens with status badges and points at the new documents.
- The fourteen glyphs still written as literals in `computer.py` and `power.py`
  are now escapes. Purely textual: decoding the escapes reproduces the previous
  source byte for byte, and the rendered panels are unchanged.

### Fixed

- `coffee doctor` no longer exits non-zero just because `xlog` is not
  installed. Falling back to `sudo` is a supported configuration, and the
  "root escalation" row already reports the overall verdict; a missing `xlog`
  is now informational and only a present-but-broken one is a failure.

## [0.1.0] - 2026-08-23

First release. A rewrite of the original single-file `coffee` script into a
package, with the display held constant: `tests/test_parity.py` renders every
panel through both implementations and diffs the styled output byte for byte.

### Added

- **Multi-level sub-commands.** Bare `coffee` still starts the live dashboard.
  `run`, `show`, `power`, `theme`, `doctor` and `config` hang off it, and the
  global flags (`--dry-run`, `--escalate`, `--theme`, `--config`, `--quiet`,
  `--verbose`, `--no-color`, `--width`) are accepted before *and* after the
  sub-command.
- **`coffee show`** — render any of the `computer`, `network`, `power`, `time`
  and `splash` panels once and exit, side by side or `--rows`.
- **`coffee power`** — `status` reports the current `pmset` values per power
  source, as a table or `--json`. `on` applies the six awake-friendly settings.
  `off` restores the values that `on` replaced, or `--defaults` hands
  everything back to macOS.
- **`coffee doctor`** — checks platform, architecture, Python, escalation
  backend, the three system tools, the config file, both timezones, the theme
  and the pmset snapshot.
- **`coffee config`** — `show`, `path`, `init` and `edit` for a TOML file at
  `~/.config/coffee/config.toml`, read forgivingly: a malformed key is reported
  and falls back to its default rather than stopping start-up.
- **`coffee theme`** — reports the active palette and previews every token.
- **Root escalation** through `/usr/local/sbin/xlog`, falling back to
  `/usr/bin/sudo`. Credentials are primed once up front, so a password prompt
  can never appear mid-render; every later call uses `sudo -n`.
- **Settings snapshots.** `coffee power on` records the previous `pmset` values
  to `~/.local/state/coffee/pmset-snapshot.json` before changing anything, so
  they can be restored exactly instead of guessed at.
- A GNU Makefile covering build, `DESTDIR`-overridable deployment, linting,
  tests and `gh`/`git` repository management.
- A test suite of 133 cases, 51 of them display-parity checks against the
  original implementation.

### Changed

- Library code raises typed errors (`PowerError`, `NetworkError`,
  `ComputerError`, `PmsetError`) instead of calling `sys.exit()`, so one failing
  panel degrades to a placeholder rather than taking the dashboard down.
- Caches are written atomically, and an unwritable cache directory is no longer
  fatal.
- Network interfaces keep their numeric service order; a non-numeric order is
  parked at the end rather than raising when it meets an integer.

### Fixed

- The terminal is taken out of cbreak mode on every exit path. Previously a
  `Ctrl-C` or a signal left the reader thread blocked in `read()` and the tty
  unusable.
- `caffeinate` is terminated, waited for, and killed if it will not go, rather
  than being left running when the dashboard exits.
- `SIGINT` and `SIGTERM` end the render loop cleanly instead of skipping the
  cleanup entirely.
- `--help` no longer prints a second, generated `(default: …)` after the one
  written by hand — and no longer claimed `(default: True)` for `--no-*` flags.

### Security

- Privileged commands are built as argument vectors and never passed through a
  shell.
- Every subprocess runs with an explicit timeout and `stdin=DEVNULL`.

[Unreleased]: https://github.com/bhaskarbhaumik/cli-coffee/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/bhaskarbhaumik/cli-coffee/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bhaskarbhaumik/cli-coffee/releases/tag/v0.1.0
