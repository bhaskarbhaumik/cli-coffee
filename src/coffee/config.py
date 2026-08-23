"""Configuration file handling.

``coffee`` runs perfectly well with no config at all; every value here has a
default that reproduces the original script's behaviour exactly.  The file
exists so a machine can pin a timezone, a refresh rate or an ASCII-art path
without wrapping the command in a shell alias.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

__all__ = ["CONFIG_PATH", "TEMPLATE", "Config"]


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg).expanduser() if xdg else Path.home() / ".config"


CONFIG_PATH = _config_home() / "coffee" / "config.toml"

#: Defaults, kept in one place so the template and the dataclass cannot drift.
DEFAULT_TZ = "America/New_York"
DEFAULT_SECONDARY_TZ = "Asia/Kolkata"
DEFAULT_REFRESH = 4
DEFAULT_POWER_INTERVAL = 300
DEFAULT_NETWORK_INTERVAL = 3600
DEFAULT_THEME_INTERVAL = 5

TEMPLATE = f"""\
# ~/.config/coffee/config.toml
#
# Every key is optional.  Delete a line to fall back to the default shown.

[display]
# Primary timezone for the big clock.  $TZ overrides this.
tz = "{DEFAULT_TZ}"
# Secondary timezone shown beside the uptime counter.
secondary_tz = "{DEFAULT_SECONDARY_TZ}"
# Live refreshes per second.
refresh = {DEFAULT_REFRESH}
# Clear the screen on start and on terminal resize.
clear_screen = true
# "auto" follows the macOS appearance setting; "light" or "dark" pin it.
theme = "auto"
# Path to the splash ASCII art used by `coffee show splash`.
# splash = "~/etc/coffee.aa"

[intervals]
# Seconds between refreshes of each slow-moving panel.
power = {DEFAULT_POWER_INTERVAL}
network = {DEFAULT_NETWORK_INTERVAL}
theme = {DEFAULT_THEME_INTERVAL}

[power]
# Apply the awake-friendly pmset settings when the dashboard starts.
configure_on_start = true
# Hold the machine awake with caffeinate(8) for as long as coffee runs.
caffeinate = true
"""


@dataclass(slots=True)
class Config:
    """Effective configuration, merged from the file and the built-in defaults."""

    tz: str = DEFAULT_TZ
    secondary_tz: str = DEFAULT_SECONDARY_TZ
    refresh: int = DEFAULT_REFRESH
    clear_screen: bool = True
    theme: str = "auto"
    splash: str | None = None

    power_interval: int = DEFAULT_POWER_INTERVAL
    network_interval: int = DEFAULT_NETWORK_INTERVAL
    theme_interval: int = DEFAULT_THEME_INTERVAL

    configure_on_start: bool = True
    caffeinate: bool = True

    path: Path = CONFIG_PATH
    exists: bool = False
    errors: list[str] = field(default_factory=list)

    # ── loading ──────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Read *path* (or the default location). Never raises — bad files are reported."""
        target = Path(path).expanduser() if path else CONFIG_PATH
        cfg = cls(path=target)

        if not target.is_file():
            return cfg
        cfg.exists = True

        try:
            data: dict[str, Any] = tomllib.loads(target.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            cfg.errors.append(f"could not read config: {exc}")
            return cfg

        display = _table(data, "display", cfg.errors)
        cfg.tz = _str(display, "tz", cfg.tz, cfg.errors)
        cfg.secondary_tz = _str(display, "secondary_tz", cfg.secondary_tz, cfg.errors)
        cfg.refresh = _int(display, "refresh", cfg.refresh, cfg.errors, minimum=1, maximum=60)
        cfg.clear_screen = _bool(display, "clear_screen", cfg.clear_screen, cfg.errors)
        cfg.theme = _str(display, "theme", cfg.theme, cfg.errors)
        splash = display.get("splash")
        if splash is not None:
            if isinstance(splash, str):
                cfg.splash = splash
            else:
                cfg.errors.append("display.splash must be a string")

        intervals = _table(data, "intervals", cfg.errors)
        cfg.power_interval = _int(intervals, "power", cfg.power_interval, cfg.errors, minimum=1)
        cfg.network_interval = _int(
            intervals, "network", cfg.network_interval, cfg.errors, minimum=1
        )
        cfg.theme_interval = _int(intervals, "theme", cfg.theme_interval, cfg.errors, minimum=1)

        power = _table(data, "power", cfg.errors)
        cfg.configure_on_start = _bool(
            power, "configure_on_start", cfg.configure_on_start, cfg.errors
        )
        cfg.caffeinate = _bool(power, "caffeinate", cfg.caffeinate, cfg.errors)

        if cfg.theme not in ("auto", "light", "dark"):
            cfg.errors.append(
                f'display.theme must be "auto", "light" or "dark" (got {cfg.theme!r})'
            )
            cfg.theme = "auto"

        return cfg

    # ── writing ──────────────────────────────────────────────────────────────
    def write_template(self, *, force: bool = False) -> tuple[bool, str]:
        """Write the commented template to :attr:`path`.

        Returns:
            ``(wrote_it, message)`` — the message is the path on success, or
            an explanation on failure.
        """
        if self.path.exists() and not force:
            return False, f"{self.path} already exists — pass --force to overwrite"
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(TEMPLATE, encoding="utf-8")
        except OSError as exc:
            return False, f"could not write {self.path}: {exc}"
        return True, str(self.path)

    def as_dict(self) -> dict[str, Any]:
        """The effective settings, minus bookkeeping fields."""
        skip = {"path", "exists", "errors"}
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name not in skip}

    @property
    def splash_path(self) -> Path | None:
        """The configured splash path, expanded — or ``None`` when unset."""
        return Path(self.splash).expanduser() if self.splash else None


# ── small, forgiving readers ─────────────────────────────────────────────────
def _table(data: dict[str, Any], name: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(name, {})
    if isinstance(value, dict):
        return value
    errors.append(f"[{name}] must be a table")
    return {}


def _str(table: dict[str, Any], key: str, default: str, errors: list[str]) -> str:
    value = table.get(key, default)
    if isinstance(value, str):
        return value
    errors.append(f"{key} must be a string")
    return default


def _bool(table: dict[str, Any], key: str, default: bool, errors: list[str]) -> bool:
    value = table.get(key, default)
    if isinstance(value, bool):
        return value
    errors.append(f"{key} must be true or false")
    return default


def _int(
    table: dict[str, Any],
    key: str,
    default: int,
    errors: list[str],
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{key} must be an integer")
        return default
    if minimum is not None and value < minimum:
        errors.append(f"{key} must be >= {minimum}")
        return default
    if maximum is not None and value > maximum:
        errors.append(f"{key} must be <= {maximum}")
        return default
    return value
