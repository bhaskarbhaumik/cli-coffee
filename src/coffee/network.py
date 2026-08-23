"""Network-interface panel, from ``system_profiler -json SPNetworkDataType``.

Two detail levels:

``terse`` (the default)
    Wi-Fi first — always, showing ``n/a`` when it has no address — then every
    other interface that actually holds an IPv4.  Padded to six rows so the
    panel does not change height as interfaces come and go.

``all``
    Active interfaces in normal text, then inactive ones dimmed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Literal

from rich import box
from rich.panel import Panel
from rich.table import Table

from coffee.theme import get_palette

__all__ = [
    "Detail",
    "NetworkError",
    "NetworkInterface",
    "NetworkManager",
    "get_interfaces",
    "get_network_panel",
]

Detail = Literal["terse", "all"]

MIN_ROWS = 6
_PROFILER_TIMEOUT = 30


class NetworkError(RuntimeError):
    """Network data could not be collected."""


@dataclass(slots=True)
class NetworkInterface:
    """One row of the network table."""

    type: str
    name: str
    ipv4: str
    ipv6: str
    mac: str
    order: Any

    @property
    def active(self) -> bool:
        """Whether the interface currently holds an IPv4 address."""
        return bool(self.ipv4)


def get_interfaces() -> list[NetworkInterface]:
    """Every configured network service, sorted by macOS service order.

    Raises:
        NetworkError: if ``system_profiler`` is unavailable or unparseable.
    """
    try:
        output = subprocess.run(
            ["system_profiler", "SPNetworkDataType", "-json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=_PROFILER_TIMEOUT,
            stdin=subprocess.DEVNULL,
        ).stdout
    except FileNotFoundError as exc:
        raise NetworkError("system_profiler not found — are you on macOS?") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise NetworkError(f"system_profiler failed: {exc}") from exc

    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise NetworkError(f"could not parse system_profiler output: {exc}") from exc

    interfaces: list[NetworkInterface] = []
    for iface in data.get("SPNetworkDataType", []):
        ipv4_addresses = iface.get("IPv4", {}).get("Addresses", []) or []
        ipv6_addresses = iface.get("IPv6", {}).get("Addresses", []) or []
        mac_address = (
            iface.get("Ethernet", {}).get("MAC Address")
            or iface.get("Wi-Fi", {}).get("MAC Address")
            or "N/A"
        )
        interfaces.append(
            NetworkInterface(
                type=iface.get("_name", "Unknown"),
                name=iface.get("interface", "N/A"),
                ipv4=", ".join(ipv4_addresses),
                ipv6=", ".join(ipv6_addresses),
                mac=mac_address,
                order=iface.get("spnetwork_service_order", "N/A"),
            )
        )

    # macOS reports the service order as an int, but "N/A" sneaks in when a
    # service is half-configured. Keep the numeric ordering and park anything
    # non-numeric at the end, rather than letting int and str meet in a compare.
    def _order(iface: NetworkInterface) -> tuple[int, int, str]:
        if isinstance(iface.order, int) and not isinstance(iface.order, bool):
            return (0, iface.order, "")
        return (1, 0, str(iface.order))

    interfaces.sort(key=_order)
    return interfaces


class NetworkManager:
    """Thin object wrapper, kept for callers that prefer one."""

    __slots__ = ()

    def get_interfaces(self) -> list[NetworkInterface]:
        return get_interfaces()

    def get_network_panel(self, details: Detail = "terse") -> Panel:
        return get_network_panel(details=details)


def get_network_panel(details: Detail = "terse") -> Panel:
    """Render the network panel at the requested detail level."""
    palette = get_palette()
    interfaces = get_interfaces()

    active = [i for i in interfaces if i.active]
    inactive = [i for i in interfaces if not i.active]

    table = Table(
        collapse_padding=True,
        padding=[0, 1],
        pad_edge=False,
        show_header=True,
        show_footer=False,
        show_edge=False,
        show_lines=False,
        row_styles=[palette.table_row_even, palette.table_row_odd],
        box=box.MINIMAL,
        border_style=palette.border_secondary,
    )
    table.add_column("Interface Type", style=palette.accent_cyan, no_wrap=True)
    table.add_column("Interface", style=palette.accent_magenta, no_wrap=True, justify="center")
    table.add_column("IPv4 Address", style=palette.accent_green, no_wrap=True, justify="center")

    if details == "all":
        for index, iface in enumerate(active, start=1):
            table.add_row(
                iface.type,
                iface.name,
                iface.ipv4,
                style="none",
                end_section=(index == len(active)),
            )
        for iface in inactive:
            table.add_row(iface.type, iface.name, iface.ipv4, style="dim")
    else:  # terse
        wifi = next((i for i in interfaces if i.type == "Wi-Fi"), None)

        rows: list[tuple[str, str, str]] = []
        if wifi is not None:
            rows.append((wifi.type, wifi.name, wifi.ipv4 or "n/a"))
        for iface in active:
            if wifi is not None and iface.name == wifi.name:
                continue
            rows.append((iface.type, iface.name, iface.ipv4))

        for index, row in enumerate(rows):
            table.add_row(*row, end_section=(index == len(rows) - 1 and len(rows) >= MIN_ROWS))

        for _ in range(max(0, MIN_ROWS - len(rows))):
            table.add_row("", "", "")

    return Panel(
        table,
        title=f"[{palette.text_highlight}]\U000f06f3[/{palette.text_highlight}]  "
        f"[{palette.accent_green}]Network Interfaces[/{palette.accent_green}]",
        border_style=palette.border_primary,
        expand=False,
    )


def is_mac() -> bool:
    """Whether this is macOS."""
    return sys.platform == "darwin"
