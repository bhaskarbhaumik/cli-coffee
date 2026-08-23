"""Colour palettes and light/dark detection.

Every panel asks :func:`get_palette` for its colours, so flipping the system
appearance while ``coffee`` is running re-skins the whole dashboard without a
restart.  The two palettes below are the visual contract — changing a value
here changes what the user sees, so they are kept verbatim.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal

ThemeName = Literal["light", "dark"]

#: How long a detection result is trusted before we shell out again.
_DETECT_TTL = 1.0
_DETECT_TIMEOUT = 1.0


@dataclass(frozen=True, slots=True)
class ColorPalette:
    """Colour palette for a theme variant (light or dark)."""

    # Text colors
    text_primary: str
    text_secondary: str
    text_dim: str
    text_highlight: str

    # Accent colors
    accent_cyan: str
    accent_green: str
    accent_yellow: str
    accent_magenta: str
    accent_red: str
    accent_blue: str

    # Background colors
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str

    # UI element colors
    border_primary: str
    border_secondary: str

    # Status colors
    status_success: str
    status_warning: str
    status_error: str
    status_info: str

    # Battery specific
    battery_outline: str
    battery_fill_charging: str
    battery_fill_discharging: str
    battery_background: str

    # Table specific
    table_row_even: str
    table_row_odd: str


#: Dark theme palette (optimised for dark terminals).
DARK_THEME = ColorPalette(
    # Text colors
    text_primary="#ffffff",
    text_secondary="#cccccc",
    text_dim="#666666",
    text_highlight="#ffff00",
    # Accent colors
    accent_cyan="bold cyan",
    accent_green="green",
    accent_yellow="yellow",
    accent_magenta="magenta",
    accent_red="red",
    accent_blue="blue",
    # Background colors
    bg_primary="#1a1a1a",
    bg_secondary="#2a2a2a",
    bg_tertiary="#202030",
    # UI element colors
    border_primary="dim green",
    border_secondary="#336633",
    # Status colors
    status_success="green",
    status_warning="yellow",
    status_error="red",
    status_info="cyan",
    # Battery specific
    battery_outline="#666666",
    battery_fill_charging="green on #333333",
    battery_fill_discharging="white on #333333",
    battery_background="#333333",
    # Table specific (subtle alternating backgrounds for dark terminals)
    table_row_even="on grey11",  # Very dark gray
    table_row_odd="on grey19",  # Slightly lighter dark gray
)


#: Light theme palette (high contrast, optimised for light terminals).
LIGHT_THEME = ColorPalette(
    # Text colors
    text_primary="#000000",
    text_secondary="#333333",
    text_dim="#999999",
    text_highlight="#0066cc",
    # Accent colors
    accent_cyan="bold #006699",
    accent_green="#006600",
    accent_yellow="#996600",
    accent_magenta="#990099",
    accent_red="#cc0000",
    accent_blue="#0066cc",
    # Background colors
    bg_primary="#ffffff",
    bg_secondary="#f5f5f5",
    bg_tertiary="#e8e8e8",
    # UI element colors
    border_primary="#006633",
    border_secondary="#339966",
    # Status colors
    status_success="#006600",
    status_warning="#cc6600",
    status_error="#cc0000",
    status_info="#0066cc",
    # Battery specific
    battery_outline="#666666",
    battery_fill_charging="#006600 on #cccccc",
    battery_fill_discharging="#333333 on #cccccc",
    battery_background="#cccccc",
    # Table specific (subtle alternating backgrounds for light terminals)
    table_row_even="on grey93",  # Very light gray
    table_row_odd="on grey85",  # Slightly darker light gray
)

PALETTES: dict[ThemeName, ColorPalette] = {"dark": DARK_THEME, "light": LIGHT_THEME}


def _normalise(name: str | None) -> ThemeName | None:
    """Coerce arbitrary user input into a known theme name, or ``None`` for auto."""
    if not name:
        return None
    lowered = name.strip().lower()
    if lowered in ("light", "dark"):
        return lowered  # type: ignore[return-value]
    return None


def detect_theme() -> ThemeName:
    """Detect whether the terminal is light or dark.

    Tried in order: ``COLORFGBG`` (set by several terminals), the macOS
    appearance setting, then ``DARK_MODE`` / ``LIGHT_MODE``.  Falls back to
    ``"dark"``, which is what most terminals actually use.
    """
    # 1) COLORFGBG is "foreground;background"; backgrounds 0-6 are dark, 7-15 light.
    colorfgbg = os.environ.get("COLORFGBG", "")
    if colorfgbg:
        parts = colorfgbg.split(";")
        if len(parts) >= 2:
            try:
                return "light" if int(parts[-1]) >= 7 else "dark"
            except ValueError:
                pass

    # 2) macOS appearance. `defaults read` exits non-zero in light mode.
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=_DETECT_TIMEOUT,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        else:
            return "dark" if result.returncode == 0 and "Dark" in result.stdout else "light"

    # 3) Explicit overrides.
    if os.environ.get("DARK_MODE") == "1":
        return "dark"
    if os.environ.get("LIGHT_MODE") == "1":
        return "light"

    return "dark"


class ThemeManager:
    """Owns the active palette and re-detects it on demand."""

    __slots__ = ("_current", "_forced", "_palette")

    def __init__(self, force_theme: str | None = None) -> None:
        """Initialise the manager.

        Args:
            force_theme: Pin a specific theme (``"light"`` or ``"dark"``).
                Anything else — including ``None`` and ``"auto"`` — auto-detects.
        """
        self._forced: ThemeName | None = _normalise(force_theme)
        self._current: ThemeName = self._forced or detect_theme()
        self._palette: ColorPalette = PALETTES[self._current]

    # ── state ────────────────────────────────────────────────────────────────
    @property
    def palette(self) -> ColorPalette:
        """The palette every panel should draw with."""
        return self._palette

    @property
    def current_theme_name(self) -> ThemeName:
        """``"light"`` or ``"dark"`` — never ``None``."""
        return self._current

    @property
    def is_forced(self) -> bool:
        """True when the theme was pinned rather than detected."""
        return self._forced is not None

    @property
    def is_light_theme(self) -> bool:
        return self._current == "light"

    @property
    def is_dark_theme(self) -> bool:
        return self._current == "dark"

    # ── refresh ──────────────────────────────────────────────────────────────
    def has_theme_changed(self) -> bool:
        """Whether a fresh detection would differ from the active theme."""
        if self._forced is not None:
            return False
        return detect_theme() != self._current

    def refresh_theme(self) -> bool:
        """Re-detect and swap the palette. Returns True when the theme changed."""
        if self._forced is not None:
            return False
        detected = detect_theme()
        if detected == self._current:
            return False
        self._current = detected
        self._palette = PALETTES[detected]
        return True

    def get_styled_text(self, text: str, color: str) -> str:
        """Wrap *text* in Rich markup for *color*."""
        return f"[{color}]{text}[/{color}]"


# ── module-level convenience API ─────────────────────────────────────────────
_theme_manager: ThemeManager | None = None


def get_theme() -> ThemeManager:
    """The process-wide theme manager, created on first use."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager(os.environ.get("COFFEE_THEME"))
    return _theme_manager


def set_theme(theme: str | None) -> ThemeManager:
    """Pin the theme (``"light"``/``"dark"``) or reset to auto-detection."""
    global _theme_manager
    _theme_manager = ThemeManager(force_theme=theme)
    return _theme_manager


def check_theme_change() -> bool:
    """Whether the system theme has drifted from the active one."""
    return get_theme().has_theme_changed()


def refresh_theme() -> bool:
    """Re-detect the theme, swapping palettes if it changed."""
    return get_theme().refresh_theme()


def get_palette() -> ColorPalette:
    """The active colour palette."""
    return get_theme().palette


# ── styling helpers ──────────────────────────────────────────────────────────
def style_number(text: str, is_zero_padded: bool = False) -> str:
    """Style a number, dimming it when it is only zero padding."""
    palette = get_palette()
    color = palette.text_dim if is_zero_padded else palette.accent_cyan
    return f"[{color}]{text}[/{color}]"


def style_header(text: str) -> str:
    """Style a section header."""
    palette = get_palette()
    return f"[dim {palette.accent_green}]{text}[/dim {palette.accent_green}]"


def style_highlight(text: str) -> str:
    """Style highlighted text."""
    palette = get_palette()
    return f"[{palette.text_highlight}]{text}[/{palette.text_highlight}]"
