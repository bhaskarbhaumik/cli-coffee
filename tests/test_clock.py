"""The big-clock panel is the piece most sensitive to accidental drift."""

from __future__ import annotations

import re
from datetime import datetime

import pytest
import pytz

from coffee.clock import (
    DIGITS_5,
    GLYPH_ROWS,
    build_time_panel,
    generate_ascii_time,
    get_uptime_str,
    n2s,
)


def test_every_glyph_is_five_rows():
    for char, glyph in DIGITS_5.items():
        assert len(glyph) == GLYPH_ROWS, char


def test_every_glyph_row_is_a_constant_width():
    for char, glyph in DIGITS_5.items():
        widths = {len(row) for row in glyph}
        assert len(widths) == 1, f"{char!r} has ragged rows: {widths}"


def test_ascii_time_is_five_rows_of_equal_width():
    rows = generate_ascii_time("12:34:56 PM").split("\n")
    assert len(rows) == GLYPH_ROWS
    assert len({len(r) for r in rows}) == 1


def test_unknown_characters_fall_back_to_blank():
    assert generate_ascii_time("§") == generate_ascii_time(" ")


def _plain(markup: str) -> list[str]:
    """Strip Rich tags and return the remaining whitespace-separated fields."""
    return re.sub(r"\[[^\]]*\]", "", markup).split()


@pytest.mark.parametrize(
    ("seconds", "expect"),
    [
        (0, ["0000", "00", "00", "00"]),
        (59, ["0000", "00", "00", "59"]),
        (60, ["0000", "00", "01", "00"]),
        (86_399, ["0000", "23", "59", "59"]),
        (86_400, ["0001", "00", "00", "00"]),
        (1_234_567, ["0014", "06", "56", "07"]),
        (359_999_999, ["4166", "15", "59", "59"]),
    ],
)
def test_uptime_components(seconds, expect):
    assert _plain(get_uptime_str(seconds)) == expect


def test_uptime_clamps_negative_input():
    """A clock skew must not render a negative day count."""
    assert get_uptime_str(-5) == get_uptime_str(0)


def test_n2s_dims_only_the_leading_zeros():
    styled = n2s(7, 4)
    assert "000" in styled
    assert styled.count("#666666") == 2  # opening and closing tag for the zeros
    assert styled.endswith("[/bold cyan]")


def test_n2s_all_zeros_is_entirely_dim():
    assert "bold cyan" not in n2s(0, 4)


def test_time_panel_carries_both_timezones(render):
    tz = pytz.timezone("America/New_York")
    now = datetime.fromtimestamp(1_700_000_000, tz)
    panel = build_time_panel(
        now=now,
        secondary=now.astimezone(pytz.timezone("Asia/Kolkata")),
        up_for=90_061,
        memory_mb=12.5,
        tz="America/New_York",
    )
    text = render(panel)
    assert "U p t i m e" in text
    assert "I S T" in text
    assert "12.50 MB" in text
    assert "America/New_York" in text
    assert "Tuesday, November 14, 2023" in text
