"""The hotkey state machine and the help popup."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from coffee.dashboard import Dashboard, _Screen
from coffee.keys import HOTKEYS, Action
from coffee.overlay import Overlay, hotkey_help_panel


def _plain(renderable: object, width: int) -> list[str]:
    console = Console(width=width, color_system=None, file=io.StringIO(), record=True)
    console.print(renderable)
    return console.export_text().splitlines()


# ── the popup ────────────────────────────────────────────────────────────────
def test_help_panel_lists_every_hotkey(render):
    text = render(hotkey_help_panel())
    for keys, description in HOTKEYS:
        assert keys in text
        assert description in text
    assert "Esc to close" in text


def test_overlay_centres_the_popup_and_leaves_the_rest_alone():
    base = Text("\n".join("x" * 40 for _ in range(11)))
    popup = Panel("hi", expand=False)  # 6 wide, 3 tall
    lines = _plain(Overlay(base, popup), width=40)

    assert len(lines) == 11
    assert all(len(line) == 40 for line in lines)
    assert lines[:4] == ["x" * 40] * 4
    assert lines[7:] == ["x" * 40] * 4
    assert lines[4] == "x" * 17 + "╭────╮" + "x" * 17
    assert lines[5] == "x" * 17 + "│ hi │" + "x" * 17
    assert lines[6] == "x" * 17 + "╰────╯" + "x" * 17


def test_overlay_grows_rather_than_clipping_a_tall_popup():
    lines = _plain(Overlay(Text("x" * 20), Panel("a\nb\nc", expand=False)), width=20)
    assert len(lines) == 5
    assert lines[0].startswith("x" * 7 + "╭")


def test_overlay_squeezes_a_popup_wider_than_the_screen():
    lines = _plain(Overlay(Text("x" * 10), Panel("y" * 30, expand=False)), width=10)
    assert all(len(line) == 10 for line in lines)


# ── the dashboard's reaction to each key ─────────────────────────────────────
@pytest.fixture
def dashboard():
    ctx = SimpleNamespace(warn=lambda message: None, config=SimpleNamespace(splash_path=None))
    board = Dashboard(
        ctx=ctx,
        console=Console(file=io.StringIO()),
        tz="UTC",
        secondary_tz="UTC",
        refresh_per_second=4,
        clear_screen=False,
        power_interval=300,
        network_interval=3600,
        theme_interval=5,
        configure_power=False,
        caffeinate=False,
    )
    return board


@pytest.fixture
def screen():
    return _Screen(
        computer_data={},
        leading=Panel("computer"),
        power=Panel("power"),
        network=Panel("network"),
        last_power_update=0.0,
        last_network_update=0.0,
        time=Panel("time"),
    )


@pytest.fixture(autouse=True)
def _no_real_refresh(monkeypatch):
    def fake(self, screen):
        screen.leading = Panel("refreshed")

    monkeypatch.setattr(Dashboard, "refresh_all", fake)


@pytest.mark.parametrize("action", [Action.QUIT, Action.ESCAPE])
def test_quit_and_escape_stop_the_dashboard(dashboard, screen, action):
    dashboard.handle(action, screen)
    assert dashboard._stop.is_set()


def test_q_quits_even_with_the_popup_open(dashboard, screen):
    screen.help = True
    dashboard.handle(Action.QUIT, screen)
    assert dashboard._stop.is_set()


def test_any_other_key_opens_the_popup_and_escape_closes_it(dashboard, screen):
    dashboard.handle(Action.HELP, screen)
    assert screen.help
    dashboard.handle(Action.HELP, screen)  # a second stray key keeps it open
    assert screen.help

    dashboard.handle(Action.ESCAPE, screen)
    assert not screen.help
    assert not dashboard._stop.is_set()  # closing the popup is not quitting

    dashboard.handle(Action.ESCAPE, screen)
    assert dashboard._stop.is_set()


def test_refresh_rebuilds_the_panels_without_quitting(dashboard, screen):
    dashboard.handle(Action.REFRESH, screen)
    assert not dashboard._stop.is_set()
    assert screen.leading.renderable == "refreshed"


def test_without_the_popup_the_frame_is_the_original_layout(dashboard, screen, render):
    """The display contract: no keypress, no change."""
    original = Align.right(Columns([screen.leading, screen.network, screen.power, screen.time]))
    assert render(dashboard.frame(screen)) == render(original)


def test_with_the_popup_the_frame_is_an_overlay(dashboard, screen, render):
    screen.help = True
    frame = dashboard.frame(screen)
    assert isinstance(frame, Overlay)
    assert "hotkeys" in render(frame)
