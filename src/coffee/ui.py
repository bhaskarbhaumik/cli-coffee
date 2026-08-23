"""Shared renderables for the non-dashboard sub-commands.

The dashboard panels live in their own modules and must not change; this is
only the chrome around ``doctor``, ``config`` and ``power``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from coffee.theme import get_palette

__all__ = ["check_panel", "command_panel", "notice"]

Kind = Literal["ok", "warn", "error", "info"]

_GLYPHS: dict[Kind, str] = {
    "ok": "\uf058",  # check-circle
    "warn": "\uf071",  # warning triangle
    "error": "\uf057",  # times-circle
    "info": "\uf05a",  # info-circle
}


def _kind_color(kind: Kind) -> str:
    palette = get_palette()
    return {
        "ok": palette.status_success,
        "warn": palette.status_warning,
        "error": palette.status_error,
        "info": palette.status_info,
    }[kind]


def notice(message: str, *, kind: Kind = "info") -> Panel:
    """A one-line status message in a bordered panel."""
    color = _kind_color(kind)
    return Panel(
        f"[{color}]{_GLYPHS[kind]}[/{color}]  {message}",
        border_style=color,
        box=box.ROUNDED,
        expand=False,
        padding=(0, 1),
    )


def check_panel(
    rows: Sequence[tuple[str, bool | None, str]],
    *,
    title: str = "doctor",
    key_header: str = "check",
) -> Panel:
    """A three-column pass/fail/unknown table, used by ``coffee doctor``.

    Each row is ``(label, ok, detail)`` where ``ok`` may be ``None`` for
    "neither good nor bad".
    """
    palette = get_palette()

    table = Table(
        show_header=True,
        show_edge=False,
        show_lines=False,
        box=box.MINIMAL,
        pad_edge=False,
        padding=(0, 1),
        border_style=palette.border_secondary,
    )
    table.add_column(key_header, style=palette.accent_cyan, no_wrap=True)
    table.add_column("", no_wrap=True, justify="center")
    table.add_column("detail", style=palette.text_secondary, overflow="fold")

    for label, ok, detail in rows:
        if ok is True:
            mark = f"[{palette.status_success}]\U000f012c[/{palette.status_success}]"  # 󰄬
        elif ok is False:
            mark = f"[{palette.status_error}]\U000f0156[/{palette.status_error}]"  # 󰅖
        else:
            mark = f"[{palette.text_dim}]\U000f01a8[/{palette.text_dim}]"  # 󰆨
        table.add_row(label, mark, detail)

    return Panel(
        table,
        title=f"[{palette.text_highlight}]\uf0f4[/{palette.text_highlight}]  "
        f"[{palette.accent_green}]{title}[/{palette.accent_green}]",
        border_style=palette.border_primary,
        expand=False,
        padding=(0, 1),
    )


def command_panel(commands: Sequence[Sequence[str]], *, title: str) -> Panel:
    """List commands verbatim — used by ``--dry-run``."""
    palette = get_palette()
    body = Text()
    for index, argv in enumerate(commands):
        if index:
            body.append("\n")
        body.append("$ ", style=palette.text_dim)
        body.append(" ".join(argv), style=palette.accent_magenta)
    if not commands:
        body.append("nothing to run", style=palette.text_dim)
    return Panel(
        body,
        title=f"[{palette.text_highlight}]\uf120[/{palette.text_highlight}]  "
        f"[{palette.accent_green}]{title}[/{palette.accent_green}]",
        border_style=palette.border_primary,
        expand=False,
        padding=(0, 1),
    )
