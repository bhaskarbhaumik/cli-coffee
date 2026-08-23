"""Shared fixtures.

The theme is process-global, so every test that renders anything pins it to
dark first — otherwise the suite would pass or fail depending on whether the
machine running it happens to be in light mode.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from coffee.theme import set_theme


@pytest.fixture(autouse=True)
def _pinned_theme():
    """Pin the palette for the duration of each test, then reset to auto."""
    set_theme("dark")
    yield
    set_theme(None)


@pytest.fixture
def render():
    """Render a Rich renderable to styled text at a fixed width."""

    def _render(renderable: object, width: int = 200) -> str:
        console = Console(
            width=width,
            record=True,
            color_system="truecolor",
            force_terminal=True,
            file=io.StringIO(),
        )
        console.print(renderable)
        return console.export_text(styles=True)

    return _render
