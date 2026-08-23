"""macOS power-management settings, via ``pmset(8)``.

The dashboard has always applied the same six settings on start-up; that list
is :data:`AWAKE_SETTINGS` and it has not changed.  What is new is that the
previous values are snapshotted first, so ``coffee power off`` can put them
back instead of guessing at macOS defaults.

Every privileged call goes through :class:`~coffee.privilege.Escalator`, so it
runs under ``xlog`` when that is available and falls back to ``sudo``.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from coffee.privilege import Escalator

__all__ = [
    "AWAKE_SETTINGS",
    "SOURCE_FLAGS",
    "STATE_PATH",
    "PmsetError",
    "PmsetResult",
    "apply_awake_settings",
    "awake_commands",
    "load_snapshot",
    "read_settings",
    "restore_macos_defaults",
    "restore_previous",
    "save_snapshot",
]

PMSET = "/usr/bin/pmset"

#: The settings the dashboard applies, in the order it has always applied them.
AWAKE_SETTINGS: tuple[tuple[str, str], ...] = (
    ("sleep", "0"),
    ("disksleep", "0"),
    ("displaysleep", "0"),
    ("womp", "1"),
    ("ring", "0"),
    ("powernap", "0"),
)

#: ``pmset -g custom`` section headings mapped to the flag that writes them back.
SOURCE_FLAGS: dict[str, str] = {
    "AC Power": "-c",
    "Battery Power": "-b",
    "UPS Power": "-u",
}

_COMMAND_TIMEOUT = 30


def _state_home() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    return Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"


STATE_PATH = _state_home() / "coffee" / "pmset-snapshot.json"


class PmsetError(RuntimeError):
    """A ``pmset`` invocation failed."""


@dataclass(slots=True)
class PmsetResult:
    """The outcome of one ``pmset`` write."""

    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def message(self) -> str:
        """The most useful line of output, for error reporting."""
        text = (self.stderr or self.stdout).strip()
        return text.splitlines()[0] if text else f"exit status {self.returncode}"


# ── reading ──────────────────────────────────────────────────────────────────
def read_settings() -> dict[str, dict[str, str]]:
    """Read ``pmset -g custom`` into ``{source: {setting: value}}``.

    Needs no privileges.

    Raises:
        PmsetError: if ``pmset`` is missing or fails.
    """
    try:
        proc = subprocess.run(
            [PMSET, "-g", "custom"],
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PmsetError(f"{PMSET} not found — are you on macOS?") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise PmsetError(f"could not run pmset: {exc}") from exc

    if proc.returncode != 0:
        raise PmsetError((proc.stderr or proc.stdout).strip() or "pmset -g custom failed")

    sources: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in proc.stdout.splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")):
            heading = raw.strip().rstrip(":")
            current = sources.setdefault(heading, {})
            continue
        if current is None:
            continue
        parts = raw.split()
        if len(parts) >= 2:
            current[parts[0]] = parts[1]
    return sources


# ── writing ──────────────────────────────────────────────────────────────────
def awake_commands() -> list[list[str]]:
    """The unprivileged argv for each awake setting, in order."""
    return [[PMSET, "-a", key, value] for key, value in AWAKE_SETTINGS]


def _run(escalator: Escalator, argv: list[str]) -> PmsetResult:
    wrapped = escalator.wrap(argv)
    try:
        proc = subprocess.run(
            wrapped,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError as exc:
        return PmsetResult(wrapped, 127, "", str(exc))
    except (OSError, subprocess.SubprocessError) as exc:
        return PmsetResult(wrapped, 1, "", str(exc))
    return PmsetResult(wrapped, proc.returncode, proc.stdout, proc.stderr)


def apply_awake_settings(escalator: Escalator, *, dry_run: bool = False) -> list[PmsetResult]:
    """Apply :data:`AWAKE_SETTINGS`. Returns one result per command.

    Failures are reported, not raised — a machine that refuses ``womp`` should
    still get the other five settings, exactly as the original script behaved.
    """
    results: list[PmsetResult] = []
    for argv in awake_commands():
        if dry_run:
            results.append(PmsetResult(escalator.wrap(argv), 0, "", ""))
            continue
        results.append(_run(escalator, argv))
    return results


def restore_previous(
    escalator: Escalator, snapshot: dict[str, dict[str, str]], *, dry_run: bool = False
) -> list[PmsetResult]:
    """Write the settings recorded in *snapshot* back, per power source."""
    results: list[PmsetResult] = []
    for source, settings in snapshot.items():
        flag = SOURCE_FLAGS.get(source)
        if flag is None:
            continue
        for key, _ in AWAKE_SETTINGS:
            if key not in settings:
                continue
            argv = [PMSET, flag, key, settings[key]]
            if dry_run:
                results.append(PmsetResult(escalator.wrap(argv), 0, "", ""))
            else:
                results.append(_run(escalator, argv))
    return results


def restore_macos_defaults(escalator: Escalator, *, dry_run: bool = False) -> list[PmsetResult]:
    """Hand every power setting back to macOS via ``pmset -a restoredefaults``."""
    argv = [PMSET, "-a", "restoredefaults"]
    if dry_run:
        return [PmsetResult(escalator.wrap(argv), 0, "", "")]
    return [_run(escalator, argv)]


# ── snapshots ────────────────────────────────────────────────────────────────
def save_snapshot(settings: dict[str, dict[str, str]], *, path: Path | None = None) -> Path | None:
    """Persist the awake-relevant subset of *settings*. Returns the path, or None on failure."""
    target = path or STATE_PATH
    keys = {key for key, _ in AWAKE_SETTINGS}
    trimmed = {
        source: {k: v for k, v in values.items() if k in keys}
        for source, values in settings.items()
        if source in SOURCE_FLAGS
    }
    trimmed = {source: values for source, values in trimmed.items() if values}
    if not trimmed:
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(trimmed, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        return None
    return target


def load_snapshot(*, path: Path | None = None) -> dict[str, dict[str, str]]:
    """Read a previously saved snapshot. Returns ``{}`` when there is none."""
    target = path or STATE_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        source: {str(k): str(v) for k, v in values.items()}
        for source, values in data.items()
        if isinstance(values, dict)
    }
