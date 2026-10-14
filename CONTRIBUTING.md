# Contributing

Thanks for taking a look. `coffee` is a small, single-purpose tool, so the bar
for a change is mostly "does it keep the display exactly as it is, and does it
make the thing more reliable".

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## The one rule

**The display is the contract.** `coffee` is a rewrite of a single-file script,
and the whole point of the rewrite was that nothing about the rendered output
changed. `tests/test_parity.py` enforces that: it renders every panel through
both implementations and diffs the styled output byte for byte.

If your change alters what a panel looks like, that is fine — but it has to be
deliberate:

1. Say so in the pull request, with a before/after.
2. Update the parity reference in the same commit.
3. Add a `### Changed` entry to [CHANGELOG.md](CHANGELOG.md).

If your change alters what a panel looks like *by accident*, the parity suite
will tell you. Listen to it.

## Getting set up

You need macOS on Apple Silicon, Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/bhaskarbhaumik/cli-coffee.git
cd cli-coffee
make venv sync          # create .venv and install the project
make hooks              # install the pre-commit hooks
make test               # compile + unit tests + a read-only smoke run
```

`make install-symlink` puts a launcher in `~/.local/bin` that runs straight out
of your checkout, so you can iterate without reinstalling.

### The parity suite

`make parity` needs a checkout of the original single-file script. It looks in
`~/Code/personal/coffee` by default and **skips cleanly when that is absent**,
so a fresh clone will show 51 skips. Point `COFFEE_REFERENCE` at a copy if you
have one:

```sh
COFFEE_REFERENCE=/path/to/original make parity
```

Those tests are the safety net for the one rule above. If you are touching a
panel and cannot run them, say so in the pull request and describe what you
checked by eye instead.

## Before you open a pull request

```sh
make ci     # version-check + ruff + compile + tests + smoke
```

That is exactly what the `ci` workflow runs, minus the macOS runner. Green
locally is usually green there.

Individually:

| command              | what it does                                        |
| -------------------- | --------------------------------------------------- |
| `make lint`          | ruff check                                           |
| `make fmt`           | ruff format, then ruff check --fix                   |
| `make check`         | byte-compile every module                            |
| `make pytest`        | the unit tests                                       |
| `make smoke`         | run the read-only sub-commands from source           |
| `make version-check` | `VERSION.md` and `pyproject.toml` agree              |
| `make pre-commit`    | every hook against every file                        |

## House style

- **Ruff** decides formatting and import order; 100-column lines. Don't argue
  with it, run `make fmt`.
- **Type hints everywhere**, with `from __future__ import annotations` at the
  top of each module.
- **Docstrings** on every public function, class and module. Say what the thing
  is for, not what the code obviously does.
- **Catch narrow exceptions.** `except Exception` appears in exactly one place
  — the panel wrapper in `dashboard.py`, where a dead panel must not take the
  dashboard with it — and it is commented as such.
- **No `sys.exit()` in library code.** Raise `PowerError`, `NetworkError`,
  `ComputerError` or `PmsetError`; the CLI layer decides the exit code.
- **Subprocesses** get an explicit argument vector (never a shell string), an
  explicit `timeout`, and `stdin=subprocess.DEVNULL`.
- **Nerd Font glyphs are written as escapes** (``, `\U000f035b`), not
  literal characters. They are private-use codepoints that no editor renders
  reliably, and a silent transcription slip would change the display. There is
  a comment to this effect in `computer.py`; please keep it true.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
feat: add a UPS panel
fix: stop caffeinate leaking when the dashboard is killed
docs: explain the escalation order
chore: bump ruff
```

`feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`. Use
the body to say *why*, not *what* — the diff already says what.

`make commit MSG="fix: …"` stages everything and commits; `make push` pushes
and sets upstream on the first push.

## Where things live

| module         | what it owns                                              |
| -------------- | --------------------------------------------------------- |
| `cli.py`       | the multi-level parser and command dispatch               |
| `dashboard.py` | the live loop, keypress handling, caffeinate lifecycle    |
| `clock.py`     | ASCII digits, uptime counter, the clock panel             |
| `computer.py`  | machine identity, cached                                   |
| `network.py`   | the interface table, terse and full                        |
| `power.py`     | the battery gauge and health, cached                       |
| `splash.py`    | the ASCII-art panel                                        |
| `pmset.py`     | the six settings, snapshots and restores                   |
| `privilege.py` | xlog → sudo escalation                                     |
| `theme.py`     | the two palettes and light/dark detection                  |
| `config.py`    | the TOML file, read forgivingly                            |
| `console.py`   | console factories                                          |
| `context.py`   | the runtime context handed to every command                |
| `ui.py`        | chrome for the non-dashboard sub-commands                  |

Panels live in their own modules and are rendered by `dashboard.py`. A new
panel means a new module, an entry in `PANELS` in `cli.py`, and a parity test.

## Anything touching root

`pmset` is the only thing that needs privileges, and it goes through
`privilege.Escalator` — never `subprocess` directly with `sudo` in the argv.
If you add a privileged command:

- build it as a list and pass it to `Escalator.wrap()`;
- make sure `--dry-run` prints it instead of running it;
- call `Escalator.prime()` once, before anything starts drawing;
- add it to `coffee doctor` if its absence should be reported.

## Reporting bugs

Use the [bug report form](https://github.com/bhaskarbhaumik/cli-coffee/issues/new?template=bug_report.yml).
`coffee doctor` output is the single most useful thing you can paste — it says
which escalation backend is live, which tools are present, and what the config
looks like.

For anything security-shaped, see [SECURITY.md](SECURITY.md) instead — please
don't open a public issue.
