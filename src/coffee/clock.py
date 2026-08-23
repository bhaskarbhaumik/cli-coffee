"""The big-clock panel: ASCII time, uptime counter and a second timezone.

Five rows of half-block characters per glyph, assembled column by column.  Only
the characters that actually appear in ``%I:%M:%S %p`` and in the uptime line
are defined — anything else falls back to a blank cell.
"""

from __future__ import annotations

import re
from datetime import datetime

from rich.panel import Panel

from coffee.theme import get_palette

__all__ = [
    "DATE_FORMAT",
    "DIGITS_5",
    "TIME_FORMAT",
    "UPTIME_HDR",
    "UPTIME_STR",
    "build_time_panel",
    "generate_ascii_time",
    "get_uptime_str",
    "n2s",
]

DATE_FORMAT = "%A, %B %d, %Y"
TIME_FORMAT = "%I:%M:%S %p"

SPACE_2 = "  "
SPACE_5 = "     "

#: ASCII-art glyphs, five rows tall.
DIGITS_5: dict[str, list[str]] = {
    "0": ["▄▄▄▄▄", "█   █", "█   █", "█▄▄▄█", SPACE_5],
    "1": ["  ▄  ", " ▀█  ", "  █  ", "▄▄█▄▄", SPACE_5],
    "2": ["▄▄▄▄▄", "    █", "█▀▀▀▀", "█▄▄▄▄", SPACE_5],
    "3": ["▄▄▄▄▄", "    █", "▀▀▀▀█", "▄▄▄▄█", SPACE_5],
    "4": ["▄   ▄", "█   █", "▀▀▀▀█", "    █", SPACE_5],
    "5": ["▄▄▄▄▄", "█    ", "▀▀▀▀█", "▄▄▄▄█", SPACE_5],
    "6": ["▄▄▄▄▄", "█    ", "█▀▀▀█", "█▄▄▄█", SPACE_5],
    "7": ["▄▄▄▄▄", "    █", "    █", "    █", SPACE_5],
    "8": ["▄▄▄▄▄", "█   █", "█▀▀▀█", "█▄▄▄█", SPACE_5],
    "9": ["▄▄▄▄▄", "█   █", "▀▀▀▀█", "▄▄▄▄█", SPACE_5],
    "A": [SPACE_5, "▄▄▄▄ ", "█  █ ", "█▄▄█▄", SPACE_5],
    "M": [SPACE_5, "▄▄ ▄▄", "█ █ █", "█ █ █", SPACE_5],
    "P": [SPACE_5, "▄▄▄▄▄", "█   █", "█▄▄▄█", "█    "],
    "-": [SPACE_5, SPACE_5, "▄▄▄▄▄", SPACE_5, SPACE_5],
    "+": [SPACE_5, "  ▄  ", "▄▄█▄▄", "  █  ", SPACE_5],
    ":": [" ", "▄", " ", "▀", " "],
    " ": [SPACE_2, SPACE_2, SPACE_2, SPACE_2, SPACE_2],
}

GLYPH_ROWS = 5

UPTIME_HDR = "————————  U p t i m e  ———————"
UPTIME_STR = "days   hours  minutes  seconds"
IST_HDR = "——————  I S T  🇮🇳  —————"

_PADDED = re.compile(r"^(0*)($|[1-9]\d*$)")


def n2s(n: int, d: int) -> str:
    """Zero-pad *n* to *d* digits, dimming the leading zeros.

    Args:
        n: The number to format.
        d: Total width, zero padded.

    Returns:
        A Rich-markup string.
    """
    palette = get_palette()
    padded = f"{n:0{d}d}"
    match = _PADDED.match(padded)
    if not match:  # pragma: no cover - the pattern matches every zero-padded int
        return f"[{palette.accent_cyan}]{padded}[/{palette.accent_cyan}]"
    out = ""
    if match.group(1):
        out += f"[{palette.text_dim}]{match.group(1)}[/{palette.text_dim}]"
    if match.group(2):
        out += f"[{palette.accent_cyan}]{match.group(2)}[/{palette.accent_cyan}]"
    return out


def get_uptime_str(up_for: float) -> str:
    """Format *up_for* seconds as the four-column uptime line."""
    up_for = max(0.0, float(up_for))
    days = int(up_for // 86400)
    hours = int((up_for % 86400) // 3600)
    minutes = int((up_for % 3600) // 60)
    seconds = int(up_for % 60)
    return f"{n2s(days, 4)}     {n2s(hours, 2)}      {n2s(minutes, 2)}       {n2s(seconds, 2)}  "


def generate_ascii_time(time_str: str) -> str:
    """Render *time_str* as five rows of block characters."""
    rows: list[str] = []
    for row in range(GLYPH_ROWS):
        segments = [" "]
        for char in time_str:
            glyph = DIGITS_5.get(char, DIGITS_5[" "])
            segments.append(glyph[row] if row < len(glyph) else " ")
            segments.append(" ")
        rows.append("".join(segments))
    return "\n".join(rows)


def build_time_panel(
    *,
    now: datetime,
    secondary: datetime,
    up_for: float,
    memory_mb: float,
    tz: str,
) -> Panel:
    """Assemble the clock panel.

    Args:
        now: Local time, in the primary timezone.
        secondary: The same instant in the secondary timezone.
        up_for: Seconds since boot.
        memory_mb: This process's resident size, shown in the subtitle.
        tz: The primary timezone name, shown in the subtitle.
    """
    palette = get_palette()

    big_time = generate_ascii_time(now.strftime(TIME_FORMAT))
    date_str = now.strftime(DATE_FORMAT)
    uptime = get_uptime_str(up_for)
    ist_str = secondary.strftime(TIME_FORMAT)
    ist_dt_str = secondary.strftime(DATE_FORMAT)

    return Panel(
        (
            f"{big_time}\n"
            f"[dim {palette.accent_green}]{UPTIME_HDR}  {IST_HDR}[/dim {palette.accent_green}]\n"
            f"[{palette.accent_cyan}]{uptime}[/{palette.accent_cyan}]       "
            f"[{palette.text_primary}]{ist_str}[/{palette.text_primary}]\n"
            f"[{palette.text_dim}]{UPTIME_STR}[/{palette.text_dim}]  "
            f"[{palette.text_highlight}]{ist_dt_str}[/{palette.text_highlight}]"
        ),
        expand=False,
        border_style=palette.border_primary,
        title=f"\uf0f4  [{palette.text_highlight}]{date_str}[/{palette.text_highlight}]",
        title_align="center",
        subtitle=f"[{palette.text_dim}]\U000f035b {memory_mb:.2f} MB[/{palette.text_dim}] — "
        f"[{palette.text_dim}]\U000f124a {tz}[/{palette.text_dim}]",
        subtitle_align="right",
    )
