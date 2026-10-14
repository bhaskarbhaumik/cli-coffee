"""The hotkey help popup, and the renderable that floats it over the dashboard.

Rich has no notion of layers, so :class:`Overlay` composites by hand: it
renders the dashboard to lines, renders the popup to lines, and splices the
popup into the middle of them cell by cell. Everything outside the popup's
rectangle is the dashboard exactly as it would otherwise have been drawn.
"""

from __future__ import annotations

from rich import box
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.measure import Measurement
from rich.panel import Panel
from rich.segment import Segment
from rich.table import Table

from coffee.keys import HOTKEYS
from coffee.theme import get_palette

__all__ = ["Overlay", "hotkey_help_panel"]


def hotkey_help_panel() -> Panel:
    """A small bordered table of the dashboard's hotkeys."""
    palette = get_palette()
    table = Table.grid(padding=(0, 2))
    table.add_column(style=f"bold {palette.accent_cyan}", no_wrap=True, justify="right")
    table.add_column(style=palette.text_primary, no_wrap=True)
    for keys, description in HOTKEYS:
        table.add_row(keys, description)
    return Panel(
        table,
        title=f"[bold {palette.accent_yellow}]\uf11c  hotkeys[/]",
        subtitle=f"[{palette.text_dim}]Esc to close[/]",
        border_style=palette.border_primary,
        box=box.ROUNDED,
        expand=False,
        padding=(1, 2),
    )


class Overlay:
    """Draw *popup* centred on top of *base*.

    If the popup is taller than the base, the base is padded with blank lines
    so the popup is never clipped; if it is wider than the screen, it is
    squeezed to fit.
    """

    __slots__ = ("base", "popup")

    def __init__(self, base: RenderableType, popup: RenderableType) -> None:
        self.base = base
        self.popup = popup

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        options = options.reset_height()

        base_lines = console.render_lines(self.base, options, pad=True)

        popup_width = min(Measurement.get(console, options, self.popup).maximum, width)
        popup_lines = console.render_lines(self.popup, options.update_width(popup_width), pad=True)

        height = max(len(base_lines), len(popup_lines))
        base_lines.extend([Segment(" " * width)] for _ in range(height - len(base_lines)))

        top = (height - len(popup_lines)) // 2
        left = (width - popup_width) // 2
        new_line = Segment.line()

        for row, line in enumerate(base_lines):
            index = row - top
            if 0 <= index < len(popup_lines):
                before, _, after = Segment.divide(line, [left, left + popup_width, width])
                line = [*before, *popup_lines[index], *after]
            yield from line
            yield new_line
