"""Machine-identity panel: model, chip, kernel, memory, host and disk usage.

Hardware and software facts do not change while ``coffee`` runs, so the
underlying ``system_profiler`` call happens exactly once, at start-up, and the
result is written to ``~/.cache/system_profile`` for the next run to read.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.table import Table

from coffee.theme import get_palette

__all__ = [
    "CACHE_DIR",
    "CACHE_FILE",
    "ComputerError",
    "ComputerManager",
    "get_computer_data",
    "get_computer_panel",
    "is_mac",
    "regenerate_computer_cache",
    "safe_get",
]

CACHE_DIR = Path.home() / ".cache" / "system_profile"
CACHE_FILE = CACHE_DIR / "cached.system_profile.computer_info.json"

DATA_TYPES = (
    "SPHardwareDataType",
    "SPMemoryDataType",
    "SPStorageDataType",
    "SPSoftwareDataType",
)

DISK_BAR_LENGTH = 24
_PROFILER_TIMEOUT = 30

#: When the cache backing the last render was read or written.
cache_mtime: float = 0.0


class ComputerError(RuntimeError):
    """Computer data could not be collected."""


class ComputerManager:
    """Fetches and caches the machine's hardware/software profile."""

    __slots__ = ("cache_dir", "cache_file")

    def __init__(self, *, cache_file: Path | None = None) -> None:
        self.cache_file: Path = cache_file or CACHE_FILE
        self.cache_dir: Path = self.cache_file.parent
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create the cache directory; a read-only home is not fatal."""
        with contextlib.suppress(OSError):
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def is_mac() -> bool:
        """Whether this is macOS."""
        return sys.platform == "darwin"

    def get_cache(self) -> dict[str, Any]:
        """The cached profile, or ``{}`` when it is missing or corrupt."""
        global cache_mtime
        try:
            cache_mtime = self.cache_file.stat().st_mtime
            with open(self.cache_file, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def write_cache(self, computer_info: dict[str, Any]) -> None:
        """Write *computer_info* to the cache. A failed write is not fatal."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(computer_info, indent=2), encoding="utf-8")
            tmp.replace(self.cache_file)
        except OSError:
            pass

    def get_computer_info(self) -> dict[str, Any]:
        """Run ``system_profiler`` for every data type in :data:`DATA_TYPES`.

        Raises:
            ComputerError: if ``system_profiler`` is unavailable or fails.
        """
        try:
            result = subprocess.run(
                ["system_profiler", "-json", *DATA_TYPES],
                capture_output=True,
                text=True,
                check=True,
                timeout=_PROFILER_TIMEOUT,
                stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise ComputerError("system_profiler not found — are you on macOS?") from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise ComputerError(f"system_profiler failed: {exc}") from exc

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ComputerError(f"could not parse system_profiler output: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def regenerate_cache(self) -> dict[str, Any]:
        """Refresh the cache from ``system_profiler`` and return the new data."""
        global cache_mtime
        computer_info = self.get_computer_info()
        self.write_cache(computer_info)
        cache_mtime = time.time()
        return computer_info

    def get_data(self, *, refresh: bool = True) -> dict[str, Any]:
        """Fresh data by default; the cache (falling back to fresh) otherwise."""
        if refresh:
            return self.regenerate_cache()
        return self.get_cache() or self.regenerate_cache()


def safe_get(data: Any, *keys: str | int, default: Any = None) -> Any:
    """Walk a nested mapping or sequence, returning *default* on the first miss."""
    current = data
    for key in keys:
        try:
            current = current[key]
        except (KeyError, TypeError, AttributeError, IndexError):
            return default
    return current


def _cpu_display(number_processors: Any) -> str:
    """Turn ``"proc 12:8:4"`` into ``"12 [󱐋 8 + 󱗁 4]"``, or pass the value through."""
    text = str(number_processors)
    match = re.search(r"proc\s+(\d+):(\d+):(\d+)", text)
    if not match:
        return text
    total, performance, efficiency = match.groups()
    return f"{total} [\U000f140b {performance} + \U000f15c1 {efficiency}]"


def get_computer_panel(computer_info: dict[str, Any] | None = None) -> Panel:
    """Build the machine-identity panel.

    Args:
        computer_info: A profile from :func:`regenerate_computer_cache`. When
            omitted, the on-disk cache is used.
    """
    palette = get_palette()

    if computer_info is None:
        computer_info = ComputerManager().get_cache()

    # ── hardware ─────────────────────────────────────────────────────────────
    hardware = safe_get(computer_info, "SPHardwareDataType", 0, default={})
    machine_model = safe_get(hardware, "machine_model", default="Unknown")
    machine_name = safe_get(hardware, "machine_name", default="Unknown")
    model_number = safe_get(hardware, "model_number", default="N/A")
    serial_number = safe_get(hardware, "serial_number", default="N/A")
    boot_rom_version = safe_get(hardware, "boot_rom_version", default="N/A")
    chip_type = safe_get(hardware, "chip_type", default="N/A")
    cpu_display = _cpu_display(safe_get(hardware, "number_processors", default="N/A"))
    physical_memory = safe_get(hardware, "physical_memory", default="N/A")

    memory_type = safe_get(computer_info, "SPMemoryDataType", 0, "dimm_type", default="Unknown")

    # ── software ─────────────────────────────────────────────────────────────
    software = safe_get(computer_info, "SPSoftwareDataType", 0, default={})
    os_version = safe_get(software, "os_version", default="N/A")
    kernel_version = safe_get(software, "kernel_version", default="N/A")
    host_name = safe_get(software, "local_host_name", default="N/A")
    user_name = re.sub(r"\s+\(.*$", "", str(safe_get(software, "user_name", default="N/A")))
    login_name = os.getenv("USER", "N/A")

    # ── storage ──────────────────────────────────────────────────────────────
    storage = safe_get(computer_info, "SPStorageDataType", 0, default={})
    disk_type = safe_get(storage, "physical_drive", "medium_type", default="Unknown")
    if disk_type != "Unknown":
        disk_type = str(disk_type).upper()
    disk_filesystem = safe_get(storage, "file_system", default="Unknown")

    size_bytes = safe_get(storage, "size_in_bytes", default=0) or 0
    free_bytes = safe_get(storage, "free_space_in_bytes", default=0) or 0
    total_size = size_bytes / (1024**3) if size_bytes else 0
    free_size = free_bytes / (1024**3) if free_bytes else 0

    if total_size > 0:
        used_percentage = ((total_size - free_size) / total_size) * 100
        filled = int(DISK_BAR_LENGTH * used_percentage / 100)
        filled = max(0, min(DISK_BAR_LENGTH, filled))
        disk_bar = "█" * filled + "░" * (DISK_BAR_LENGTH - filled)
    else:
        disk_bar = "░" * DISK_BAR_LENGTH

    # ── layout ───────────────────────────────────────────────────────────────
    table = Table(
        show_header=False,
        show_lines=False,
        show_edge=False,
        expand=False,
        border_style=palette.border_primary,
        padding=(0, 1),
    )
    table.add_column("Left", overflow="none", justify="left")
    table.add_column("Right", overflow="none", justify="left")

    blue = palette.accent_blue
    magenta = palette.accent_magenta

    # Glyphs are spelled as escapes on purpose: they are Nerd Font private-use
    # codepoints that no editor renders reliably, and a silent transcription
    # slip would quietly change what the panel looks like.
    left_content = (
        f"[{blue}][/{blue}]  {machine_name} "
        f"[{palette.text_dim}][{machine_model}][/{palette.text_dim}]\n"
        f"[{blue}]\U000f0efe[/{blue}]  [dim]Model....[/dim] [{magenta}]{model_number}[/{magenta}]\n"
        f"[{blue}][/{blue}]  [dim]Serial...[/dim] [{magenta}]{serial_number}[/{magenta}]\n"
        f"[{blue}][/{blue}]  [dim]Firmware.[/dim] [{magenta}]{boot_rom_version}[/{magenta}]\n"
        f"[{blue}]\U000f1913[/{blue}]  [dim]Chip.....[/dim] [{magenta}]{chip_type}[/{magenta}]\n"
        f"[{blue}][/{blue}]  [dim]CPU......[/dim] [{magenta}]{cpu_display}[/{magenta}]\n"
        f"[{blue}]\U000f0697[/{blue}]  [dim]Kernel...[/dim] [{magenta}]{kernel_version}[/{magenta}]\n"
        f"[{blue}][/{blue}]  [dim]OS.......[/dim] [{magenta}]{os_version}[/{magenta}]"
    )

    right_content = (
        f"[{blue}]\U000f035b[/{blue}]  [dim]Memory.[/dim] "
        f"[{magenta}]{physical_memory} ({memory_type})[/{magenta}]\n"
        f"[{blue}][/{blue}]  [dim]Host...[/dim] [{magenta}]{host_name}[/{magenta}]\n"
        f"[{blue}][/{blue}]  [dim]User...[/dim] [{magenta}]{user_name}[/{magenta}]\n"
        f"[{blue}]\U000f0342[/{blue}]  [dim]Login..[/dim] [{magenta}]{login_name}[/{magenta}]\n"
        f"[{blue}]\U000f01bc[/{blue}]  [dim]Disk...[/dim] "
        f"[{magenta}]{disk_type} ({disk_filesystem})[/{magenta}]\n"
        f"[{blue}]\U000f0aa9[/{blue}]  [dim]Total..[/dim] [{magenta}]{total_size:.2f} GB[/{magenta}]\n"
        f"[{blue}]\U000f1624[/{blue}]  [dim]Free...[/dim] [{magenta}]{free_size:.2f} GB[/{magenta}]\n"
        f"[{blue}]{disk_bar}[/{blue}]"
    )

    table.add_row(left_content, right_content)

    return Panel(
        table,
        title=f"[{palette.text_highlight}]\uf0a6[/{palette.text_highlight}]  "
        f"[{palette.accent_green}]Computer Info[/{palette.accent_green}]",
        border_style=palette.border_primary,
        expand=False,
    )


# ── convenience wrappers ─────────────────────────────────────────────────────
def is_mac() -> bool:
    """Whether this is macOS."""
    return ComputerManager.is_mac()


def regenerate_computer_cache() -> dict[str, Any]:
    """Refresh the on-disk profile cache and return the new data."""
    return ComputerManager().regenerate_cache()


def get_computer_data(*, refresh: bool = True) -> dict[str, Any]:
    """Machine profile, refreshed by default."""
    return ComputerManager().get_data(refresh=refresh)
