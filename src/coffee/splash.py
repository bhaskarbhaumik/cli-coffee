"""Splash panel — ASCII art read from disk.

The art lives outside the package on purpose, so it can be swapped without a
reinstall.  ``~/etc/coffee.aa`` is the historical location and remains the
default; ``display.splash`` in the config file overrides it.
"""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

__all__ = ["DEFAULT_ART_PATH", "FALLBACK_ART", "Splash", "get_splash_panel"]

DEFAULT_ART_PATH = Path.home() / "etc" / "coffee.aa"

#: Drawn when the art file is missing, so the panel never renders empty.
FALLBACK_ART = "\n".join(
    (
        r"      )  (    ",
        r"     (   ) )  ",
        r"      ) ( (   ",
        r"    _______)_ ",
        r" .-'---------|",
        r"( C|/\/\/\/\/|",
        r" '-./\/\/\/\/|",
        r"   '_________'",
        r"    '-------'",
    )
)


class Splash:
    """Renders a splash ASCII-art panel."""

    __slots__ = ("ascii_art_path",)

    def __init__(self, ascii_art_path: Path | None = None) -> None:
        """Initialise the splash.

        Args:
            ascii_art_path: Where to read the art from. Defaults to
                :data:`DEFAULT_ART_PATH`.
        """
        self.ascii_art_path = (
            Path(ascii_art_path).expanduser() if ascii_art_path else DEFAULT_ART_PATH
        )

    def get_splash_panel(self) -> Panel:
        """The splash panel — themed art, themed fallback, or a themed error."""
        from coffee.theme import get_palette

        palette = get_palette()

        try:
            ascii_art = self.ascii_art_path.read_text(encoding="utf-8").rstrip()
        except FileNotFoundError:
            return Panel(
                FALLBACK_ART,
                title="[yellow]\uf0f4[/yellow]  [yellow]Coffee[/yellow]",
                border_style="yellow",
                expand=False,
            )
        except (OSError, UnicodeDecodeError) as exc:
            return Panel(
                f"[dim red]Error loading ASCII art:\n{exc}[/dim red]",
                title="[red]\uf071[/red]  [red]Splash Error[/red]",
                border_style="red",
                expand=False,
            )

        return Panel(
            ascii_art,
            title=f"[{palette.text_highlight}]\uf0f4[/{palette.text_highlight}]  "
            f"[{palette.accent_green}]Coffee[/{palette.accent_green}]",
            border_style=palette.border_primary,
            expand=False,
        )


def get_splash_panel(ascii_art_path: Path | None = None) -> Panel:
    """Build a splash panel, reading from *ascii_art_path* or the default."""
    return Splash(ascii_art_path=ascii_art_path).get_splash_panel()
