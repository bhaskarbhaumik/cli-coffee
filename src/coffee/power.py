"""Battery and AC-charger panel, backed by a cached ``system_profiler`` call.

``system_profiler -json SPPowerDataType`` takes the better part of a second, so
the result is cached under ``~/.cache/system_profile`` and only refreshed every
:data:`CACHE_TTL` seconds.  The panel's "Last Updated" line reports the age of
that cache, not the age of the render.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table

from coffee.theme import get_palette

__all__ = [
    "BAR_CHARS",
    "CACHE_DIR",
    "CACHE_FILE",
    "CACHE_TTL",
    "PowerError",
    "PowerManager",
    "get_bar",
    "get_power_data",
    "get_power_visual",
    "is_mac",
    "last_updated",
    "safe_get",
]

# Configuration constants
BAR_CHARS: list[str] = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
CACHE_DIR = Path.home() / ".cache" / "system_profile"
CACHE_FILE = CACHE_DIR / "cached.system_profile.SPPowerDataType.json"
CACHE_TTL = 300  # 5 minutes
WIDTH_FACTOR = 10
MIN_HEIGHT = 1
MAX_HEIGHT = 4

_PROFILER_TIMEOUT = 30

#: When the cache backing the last render was written.  Module state because the
#: panel renders it and the manager owns it.
cache_mtime: float = 0.0


class PowerError(RuntimeError):
    """Power data could not be collected."""


class PowerManager:
    """Fetches and caches ``SPPowerDataType``."""

    __slots__ = ("cache_dir", "cache_file", "cache_ttl")

    def __init__(
        self,
        *,
        cache_file: Path | None = None,
        cache_ttl: int = CACHE_TTL,
    ) -> None:
        self.cache_file: Path = cache_file or CACHE_FILE
        self.cache_dir: Path = self.cache_file.parent
        self.cache_ttl: int = cache_ttl
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create the cache directory; a read-only home is not fatal."""
        with contextlib.suppress(OSError):
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_mac() -> bool:
        """Whether this is macOS."""
        return sys.platform == "darwin"

    def is_cache_stale(self) -> bool:
        """Whether the cache is missing or older than :attr:`cache_ttl`."""
        global cache_mtime
        try:
            cache_mtime = self.cache_file.stat().st_mtime
        except OSError:
            return True
        return (time.time() - cache_mtime) > self.cache_ttl

    def get_cache(self) -> dict[str, Any]:
        """The cached payload, or ``{}`` when it is missing or corrupt."""
        try:
            with open(self.cache_file, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def write_cache(self, power_info: dict[str, Any]) -> None:
        """Write *power_info* to the cache. A failed write is not fatal."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(power_info), encoding="utf-8")
            tmp.replace(self.cache_file)
        except OSError:
            pass

    def get_power_info(self) -> dict[str, Any]:
        """Run ``system_profiler`` and reshape its output.

        Raises:
            PowerError: if ``system_profiler`` is unavailable or fails.
        """
        try:
            result = subprocess.run(
                ["system_profiler", "-json", "SPPowerDataType"],
                capture_output=True,
                text=True,
                check=True,
                timeout=_PROFILER_TIMEOUT,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise PowerError("system_profiler not found — are you on macOS?") from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise PowerError(f"system_profiler failed: {exc}") from exc

        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PowerError(f"could not parse system_profiler output: {exc}") from exc

        sections = {
            "spbattery_information": "battery",
            "sppower_information": "power",
            "sppower_ac_charger_information": "ac_charger",
            "sppower_hwconfig_information": "ups",
        }
        power: dict[str, Any] = {}
        for entry in raw.get("SPPowerDataType", []):
            key = sections.get(entry.get("_name", ""))
            if key is None:
                continue
            entry.pop("_name", None)
            power[key] = entry
        return power

    def get_power_data(self) -> dict[str, Any]:
        """Power data, from the cache when it is fresh enough."""
        global cache_mtime

        if not self.is_cache_stale():
            return self.get_cache()

        power_info = self.get_power_info()
        self.write_cache(power_info)
        cache_mtime = time.time()
        return power_info


def get_bar(percentage: int, height: int = 1, is_charging: bool = False) -> str:
    """Draw the battery gauge.

    Args:
        percentage: Charge level, clamped to 0-100.
        height: Rows of fill, clamped to 1-4.
        is_charging: Picks the charging vs. discharging fill colour.

    Returns:
        A multi-line string with Rich markup.
    """
    palette = get_palette()

    percentage = max(0, min(100, percentage))
    height = max(MIN_HEIGHT, min(MAX_HEIGHT, height))

    width = WIDTH_FACTOR * height
    cap_width = int(float(height - 1) * 2.0 / 3.0) + 1

    battery_outline = palette.battery_outline
    battery_fill = (
        palette.battery_fill_charging if is_charging else palette.battery_fill_discharging
    )

    bat = f"  [{battery_outline}]╭{'─' * width}╮[/{battery_outline}]\n"

    w1 = int(percentage * width / 100)
    w2 = percentage % 10
    w3 = width - w1 - 1

    for _ in range(height):
        if percentage == 100:
            bat += (
                f"  [{battery_outline}]│[/{battery_outline}]"
                f"[{battery_fill}]{'█' * width}[/{battery_fill}]"
                f"[{battery_outline}]│{'█' * cap_width}[/{battery_outline}]\n"
            )
        else:
            fill_char = BAR_CHARS[min(w2, len(BAR_CHARS) - 1)]
            bat += (
                f"  [{battery_outline}]│[/{battery_outline}]"
                f"[{battery_fill}]{'█' * w1}{fill_char}{' ' * w3}[/{battery_fill}]"
                f"[{battery_outline}]│{'█' * cap_width}[/{battery_outline}]\n"
            )

    bat += f"  [{battery_outline}]╰{'─' * width}╯[/{battery_outline}]"
    return bat


def safe_get(data: Any, *keys: str, default: Any = None) -> Any:
    """Walk a nested mapping, returning *default* the moment a key is missing."""
    current = data
    for key in keys:
        try:
            current = current[key]
        except (KeyError, TypeError, AttributeError, IndexError):
            return default
    return current


def last_updated() -> float:
    """Epoch seconds for the cache backing the most recent :func:`get_power_data`."""
    return cache_mtime


def get_power_visual(
    power_info: dict[str, Any], height: int = 1, updated_at: float | None = None
) -> Panel:
    """Build the battery panel.

    Args:
        power_info: The payload from :func:`get_power_data`.
        height: Rows of battery fill.
        updated_at: Epoch seconds shown as "Last Updated"; defaults to the
            module's cache timestamp.
    """
    palette = get_palette()
    stamp = cache_mtime if updated_at is None else updated_at

    charge = safe_get(
        power_info,
        "battery",
        "sppower_battery_charge_info",
        "sppower_battery_state_of_charge",
        default=0,
    )
    try:
        battery_percent = int(charge)
    except (ValueError, TypeError):
        battery_percent = 0

    battery_charging = (
        safe_get(
            power_info,
            "battery",
            "sppower_battery_charge_info",
            "sppower_battery_is_charging",
            default="FALSE",
        )
        == "TRUE"
    )

    battery_warning = (
        safe_get(
            power_info,
            "battery",
            "sppower_battery_charge_info",
            "sppower_battery_at_warn_level",
            default="FALSE",
        )
        == "TRUE"
    )

    battery_icon = (
        f"[{palette.status_error}][/{palette.status_error}]"
        if battery_warning
        else f"[{palette.status_success}][/{palette.status_success}]"
    )
    battery_info = get_bar(battery_percent, height, is_charging=battery_charging)

    charging_glyph = (
        f"[bold {palette.status_success}]\U000f008f[/bold {palette.status_success}]"
        if battery_charging
        else f"[dim {palette.status_error}]\U000f008c[/dim {palette.status_error}]"
    )

    if height > 1:
        battery_info += (
            f"\n{battery_icon} Battery is charged at "
            f"[{palette.accent_yellow}]{battery_percent}%[/{palette.accent_yellow}]"
        )
        battery_info += (
            f"\n{charging_glyph} Battery is currently [{palette.accent_yellow}]"
            f"{'charging' if battery_charging else 'discharging'}[/{palette.accent_yellow}]"
        )
    else:
        battery_info += (
            f"\n {battery_icon} [{palette.accent_yellow}]{battery_percent}%"
            f"[/{palette.accent_yellow}] Charged"
        )
        battery_info += (
            f"\n {charging_glyph} [{palette.accent_yellow}]"
            f"{'Charging' if battery_charging else 'Discharging'}[/{palette.accent_yellow}]"
        )

    rule_width = 22
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stamp))
    power_updated = (
        f"{battery_info}\n[{palette.border_primary}]{'─' * rule_width}[/{palette.border_primary}]\n"
    )
    power_updated += (
        f"[{palette.accent_yellow}][/{palette.accent_yellow}] [bold]Last Updated[/bold]\n"
        f"  [{palette.text_dim}]{ts}[/{palette.text_dim}]"
    )

    # ── battery health ───────────────────────────────────────────────────────
    health_status = safe_get(
        power_info,
        "battery",
        "sppower_battery_health_info",
        "sppower_battery_health",
        default="Unknown",
    )
    health_status_display = (
        f"[{palette.status_success}]\U000f1211[/{palette.status_success}] Good"
        if health_status == "Good"
        else f"[{palette.status_error}]\U000f0083[/{palette.status_error}] {health_status}"
    )
    max_capacity = safe_get(
        power_info,
        "battery",
        "sppower_battery_health_info",
        "sppower_battery_health_maximum_capacity",
        default="N/A",
    )
    cycle_count = safe_get(
        power_info,
        "battery",
        "sppower_battery_health_info",
        "sppower_battery_cycle_count",
        default="N/A",
    )

    battery_health_info_str = (
        f"[{palette.accent_yellow}][/{palette.accent_yellow}] [bold]Battery Health[/bold]\n"
        f"  [dim][{palette.accent_blue}]\U000f0091[/{palette.accent_blue}] Status........[/dim]"
        f"{health_status_display}\n"
        f"  [dim][{palette.accent_blue}]\U000f17e0[/{palette.accent_blue}] Max Capacity..[/dim]"
        f"[{palette.accent_magenta}]{max_capacity}[/{palette.accent_magenta}]\n"
        f"  [dim][{palette.accent_blue}]\U000f1834[/{palette.accent_blue}] Cycle Count...[/dim]"
        f"[{palette.accent_magenta}]{cycle_count}[/{palette.accent_magenta}]"
    )

    # ── AC charger ───────────────────────────────────────────────────────────
    charger_connected = (
        safe_get(power_info, "ac_charger", "sppower_battery_charger_connected", default="FALSE")
        == "TRUE"
    )
    charger_status = (
        f"[{palette.status_success}]\U000f06a5[/{palette.status_success}] Yes"
        if charger_connected
        else f"[{palette.status_error}]\U000f06a6[/{palette.status_error}] No"
    )
    charger_watts = safe_get(power_info, "ac_charger", "sppower_ac_charger_watts", default="N/A")

    ac_charger_info = (
        f"[{palette.accent_yellow}][/{palette.accent_yellow}] [bold]AC Charger[/bold]\n"
        f"  [dim][{palette.accent_blue}]\U000f0425[/{palette.accent_blue}] Connected?..[/dim] "
        f"{charger_status}\n"
        f"  [dim][{palette.accent_blue}][/{palette.accent_blue}] Wattage.....[/dim] "
        f"[{palette.accent_magenta}]{charger_watts} Watts[/{palette.accent_magenta}]"
    )

    battery_table = Table(
        show_header=False,
        show_lines=False,
        show_edge=False,
        expand=False,
        border_style=palette.border_primary,
    )
    battery_table.add_column("Battery Info", overflow="none", justify="left")
    battery_table.add_column("Power Source", overflow="none", justify="left")

    hr = f"[{palette.border_primary}]{'─' * 26}[/{palette.border_primary}]"
    battery_table.add_row(power_updated, f"{battery_health_info_str}\n{hr}\n{ac_charger_info}")

    return Panel(
        battery_table,
        title=f"[{palette.text_highlight}][/{palette.text_highlight}]  "
        f"[{palette.accent_green}]Battery Status[/{palette.accent_green}]",
        border_style=palette.border_primary,
        padding=(0, 1),
        expand=False,
    )


# ── convenience wrappers ─────────────────────────────────────────────────────
def is_mac() -> bool:
    """Whether this is macOS."""
    return PowerManager.is_mac()


def get_power_data() -> dict[str, Any]:
    """Power data via a throwaway :class:`PowerManager`."""
    return PowerManager().get_power_data()


def get_power_panel(height: int = 1) -> Panel:
    """Fetch and render the battery panel in one call."""
    return get_power_visual(get_power_data(), height)
