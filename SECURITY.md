# Security Policy

## Supported versions

`coffee` is pre-1.0. Only the latest release gets fixes.

| version | supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a vulnerability

**Please do not open a public issue.**

Use GitHub's private vulnerability reporting:

> [**Report a vulnerability**](https://github.com/bhaskarbhaumik/cli-coffee/security/advisories/new)

If that is unavailable to you, email
<4145672+bhaskarbhaumik@users.noreply.github.com> with `SECURITY` in the
subject.

Helpful to include: the version (`coffee --version`), your macOS and
architecture, which escalation backend is active (`coffee doctor`), and the
smallest reproduction you have. A description of the problem is enough — a
working exploit is not required and not wanted.

### What to expect

This is a personal project maintained in spare time, so no formal SLA — but
in practice:

- **Acknowledgement** within about a week.
- **An assessment** — whether it reproduces, and how severe — within two weeks.
- **A fix or a decision not to fix**, with reasoning, once assessed.
- **Credit** in the advisory and in [CHANGELOG.md](CHANGELOG.md), unless you
  would rather stay anonymous.

Please give a reasonable window before disclosing publicly.

## Threat model

`coffee` is a local, single-user CLI. It takes no network input, listens on
nothing, and parses no untrusted data from the network. The interesting
surface is that **it runs commands as root**.

### What runs as root

Exactly one thing: `/usr/bin/pmset`, with six fixed settings
(`sleep`, `disksleep`, `displaysleep`, `womp`, `ring`, `powernap`), plus
`pmset -a restoredefaults` when you explicitly ask for it. Nothing else is
escalated. `coffee power status` and the whole dashboard need no privileges at
all.

### How it gets root

1. `/usr/local/sbin/xlog` — a set-uid helper, if present and working.
2. `/usr/bin/sudo` — otherwise, prompting once.

`coffee` does not ship, install or modify `xlog`. If it is on your machine,
something else put it there, and **its security is its own**: a set-uid root
binary that runs arbitrary commands is a privilege-escalation primitive for
anything that can execute it. `coffee` only detects it (by running
`xlog /usr/bin/id -u` and checking for `0`) and uses it when it works. If you
would rather it did not, `--escalate sudo` pins the fallback.

### Design choices that matter here

- **No shell.** Every command is an explicit argument vector passed to
  `subprocess.run`. Nothing is interpolated into a shell string, so there is
  nothing to quote-escape.
- **Fixed commands.** The privileged argv are built from module-level
  constants and snapshot values that came from `pmset`'s own output — never
  from user-supplied text. Config and CLI input cannot reach them.
- **No blocking prompts.** Credentials are acquired once, up front, with
  `sudo -v`; every later call uses `sudo -n`. A password prompt cannot appear
  part-way through a render.
- **Timeouts and closed stdin.** Every subprocess has an explicit `timeout`
  and `stdin=subprocess.DEVNULL`.
- **Dry run.** `--dry-run` prints the exact privileged argv, wrapper included,
  and runs nothing.

### What it writes

| path                                            | contents                         |
| ----------------------------------------------- | -------------------------------- |
| `~/.config/coffee/config.toml`                  | your settings, if you create it  |
| `~/.cache/system_profile/*.json`                | cached `system_profiler` output  |
| `~/.local/state/coffee/pmset-snapshot.json`     | previous `pmset` values          |

All under your home directory, with your own permissions, written atomically.
The `system_profiler` cache contains your machine's serial number and model —
it is the same data `system_profiler` would give any local process, but worth
knowing before you paste it anywhere.

### Out of scope

- The security of `xlog` itself, or of any other set-uid helper on your system.
- An attacker who already has your user account: they can run `coffee`, and
  through it `pmset`, exactly as you can.
- Anything a `pmset` setting itself enables — `womp 1` allows wake-for-network
  by design, and that is the documented behaviour, not a vulnerability.

## Dependencies

Four runtime dependencies: `rich`, `rich-argparse-plus`, `psutil` and `pytz`.
Dependabot watches them and the GitHub Actions used in CI. Advisories against
any of them will be picked up there; feel free to report one anyway if you
spot it first.
