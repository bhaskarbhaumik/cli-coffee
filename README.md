# coffee

Keep an Apple Silicon Mac awake, with style.

`coffee` draws a live terminal dashboard — machine identity, network interfaces,
battery health and a big ASCII clock — and holds the machine awake for as long
as it runs. It is the packaged, hardened successor to a single-file script, and
**the display is byte-for-byte what it always was**: a parity test suite renders
every panel through both implementations and diffs the styled output.

```
╭──────────  Computer Info ──────────╮ ╭──── 󰛳  Network Interfaces ────╮ ╭─────  Battery Status ─────╮ ╭──  Sunday, August 23, 2026 ──╮
│  MacBook Pro [Mac16,8]             │ │ Interface Type │ en  │ IPv4   │ │  ╭──────────╮ │ Health    │ │  ▄▄▄▄▄ ▄▄▄▄▄   ▄▄▄▄▄ ▄   ▄   │
│ 󰻾  Model.... Z1FE000NKLL/A         │ │ ───────────────┼─────┼─────── │ │  │████████  │ │ 󰂑 Good    │ │  █   █     █ ▄ █   █ █   █   │
│   Chip..... Apple M4 Pro           │ │ Wi-Fi          │ en0 │ n/a    │ │  ╰──────────╯ │ 󱟠 100%    │ │ ————  U p t i m e  ————      │
╰────────────────────────────────────╯ ╰──────────────────────────────╯ ╰───────────────────────────╯ ╰──────────────────────────────╯
```

## Install

```sh
make install                      # → ~/.local/bin/coffee
make install DESTDIR=/usr/local/bin
```

`make install` builds a wheel, installs it with `uv tool install`, and links the
launcher into `DESTDIR` (default `~/.local/bin`). `make verify` confirms the
result runs and that `DESTDIR` is on your `PATH`.

For day-to-day hacking, `make install-symlink` writes a launcher that runs
straight out of this checkout instead.

Requires macOS on Apple Silicon, Python 3.14+ and [uv](https://docs.astral.sh/uv/).

## Use

```sh
coffee                            # the live dashboard — press any key to quit
coffee run --tz UTC               # …on a different timezone
coffee run --no-caffeinate        # …without holding the machine awake

coffee show                       # render every panel once and exit
coffee show power network         # …or just these
coffee show splash --rows         # stacked instead of side by side

coffee power status               # what pmset currently says
coffee power on                   # apply the awake-friendly settings
coffee power off                  # put back whatever `coffee power on` replaced
coffee power off --defaults       # hand everything back to macOS

coffee doctor                     # check escalation, tooling and configuration
coffee theme                      # which palette is active, and a preview
coffee config init                # write ~/.config/coffee/config.toml
```

Every sub-command accepts `--dry-run`, so you can see exactly which privileged
commands would run before letting them:

```
$ coffee --dry-run power on
╭─────────────────────   power on ──────────────────────╮
│ $ /usr/local/sbin/xlog /usr/bin/pmset -a sleep 0       │
│ $ /usr/local/sbin/xlog /usr/bin/pmset -a disksleep 0   │
│ $ /usr/local/sbin/xlog /usr/bin/pmset -a displaysleep 0│
│ $ /usr/local/sbin/xlog /usr/bin/pmset -a womp 1        │
│ $ /usr/local/sbin/xlog /usr/bin/pmset -a ring 0        │
│ $ /usr/local/sbin/xlog /usr/bin/pmset -a powernap 0    │
╰────────────────────────────────────────────────────────╯
```

## How it stays awake

Two mechanisms, both applied when the dashboard starts:

1. **`pmset`** — six settings that stop the machine, its disks and its display
   from going to sleep, and stop Power Nap and ring-wake from interfering:

   | setting        | value | effect                                 |
   | -------------- | ----- | -------------------------------------- |
   | `sleep`        | `0`   | never sleep the system                 |
   | `disksleep`    | `0`   | never spin the disks down              |
   | `displaysleep` | `0`   | never sleep the display                |
   | `womp`         | `1`   | allow wake for network access          |
   | `ring`         | `0`   | do not wake on modem ring              |
   | `powernap`     | `0`   | no background work while nominally idle|

2. **`caffeinate -dimsu`** — a child process that asserts the display, idle,
   disk and system-sleep locks for as long as `coffee` is running, and is
   terminated when it exits.

The `pmset` settings outlive the process, so `coffee power on` snapshots the
previous values to `~/.local/state/coffee/pmset-snapshot.json` first, and
`coffee power off` writes them back — per power source, using `pmset -b`/`-c`,
rather than guessing at macOS defaults.

## Root access

Writing `pmset` needs root. `coffee` gets it in this order:

1. **`/usr/local/sbin/xlog`** — a set-uid helper that grants password-less root.
2. **`/usr/bin/sudo`** — prompts for a password, once.

Credentials are acquired *before* anything starts drawing (`sudo -v`), and every
later call uses `sudo -n`, so a password prompt can never appear mid-render and
scribble over the live dashboard. `--escalate xlog|sudo` pins the backend;
`coffee doctor` reports which one is actually available:

```
$ coffee doctor
 root escalation    󰄬  /usr/local/sbin/xlog grants password-less root
 xlog               󰄬  /usr/local/sbin/xlog runs commands as uid 0
 sudo               󰄬  /usr/bin/sudo present
```

If neither backend works, `coffee` says so and keeps drawing — the dashboard
itself needs no privileges at all.

## Configuration

Everything has a default that reproduces the original behaviour; the file only
exists so a machine can pin something without a shell alias.

```sh
coffee config init      # write the commented template
coffee config show      # the effective settings
coffee config edit      # open it in $EDITOR
coffee config path      # just print the path
```

```toml
# ~/.config/coffee/config.toml
[display]
tz = "America/New_York"     # $TZ overrides this
secondary_tz = "Asia/Kolkata"
refresh = 4                 # live refreshes per second
clear_screen = true
theme = "auto"              # or "light" / "dark"
# splash = "~/etc/coffee.aa"

[intervals]
power = 300                 # seconds between battery re-reads
network = 3600
theme = 5

[power]
configure_on_start = true
caffeinate = true
```

A malformed config never stops `coffee` from starting — bad keys are reported by
`coffee doctor` and `coffee config show`, and fall back to their defaults.

## Theming

The palette follows the system appearance and re-checks every five seconds, so
switching macOS between light and dark re-skins the running dashboard without a
restart. `--theme light|dark` pins it; `coffee theme` previews every token.

## Development

```sh
make venv sync        # create .venv and install the project
make test             # compile, unit tests, and a read-only smoke run
make parity           # diff every panel against the reference implementation
make lint fmt         # ruff
make build            # wheel + sdist into dist/
```

`make parity` needs a checkout of the original script. It defaults to
`~/Code/personal/coffee` and skips cleanly when that is absent; point
`COFFEE_REFERENCE` elsewhere to override.

### Layout

| module         | what it owns                                             |
| -------------- | -------------------------------------------------------- |
| `cli.py`       | the multi-level parser and command dispatch              |
| `dashboard.py` | the live loop, keypress handling and caffeinate lifecycle |
| `clock.py`     | ASCII digits, uptime counter, the clock panel            |
| `computer.py`  | machine identity, cached                                 |
| `network.py`   | interface table, terse and full                          |
| `power.py`     | battery gauge and health, cached                         |
| `splash.py`    | ASCII-art panel                                          |
| `pmset.py`     | the six settings, snapshots and restores                 |
| `privilege.py` | xlog → sudo escalation                                   |
| `theme.py`     | the two palettes and light/dark detection                |
| `config.py`    | the TOML file, read forgivingly                          |

### Repository management

```sh
make repo             # create the private GitHub repo and wire up origin
make commit MSG="…"   # stage everything and commit
make push             # push, setting upstream on the first push
make status           # git status plus the current remote
make release          # test, build, tag and publish a GitHub release
```

## Licence

MIT — see [LICENSE](LICENSE).
