"""Display parity against the reference implementation.

``coffee`` was rewritten from a single-file script into a package on the
explicit condition that *nothing about the display changes*.  This module
renders both implementations with identical inputs and compares the styled
output byte for byte.

The reference checkout is not vendored, so every test here skips when it is
absent — set ``COFFEE_REFERENCE`` to point at a copy of it.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import pytest
import pytz

REFERENCE = Path(
    os.environ.get("COFFEE_REFERENCE", Path.home() / "Code" / "personal" / "coffee")
).expanduser()
REFERENCE_PKG = REFERENCE / "src" / "coffee"

pytestmark = pytest.mark.skipif(
    not REFERENCE_PKG.is_dir(),
    reason=f"reference implementation not found at {REFERENCE_PKG} (set COFFEE_REFERENCE)",
)


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    """Import the reference package under a name that cannot clash with ours."""
    root = tmp_path_factory.mktemp("reference")
    shutil.copytree(REFERENCE_PKG, root / "refcoffee", ignore=shutil.ignore_patterns("__pycache__"))
    sys.path.insert(0, str(root))
    try:
        import refcoffee.computer
        import refcoffee.main
        import refcoffee.network
        import refcoffee.power
        import refcoffee.splash
        import refcoffee.theme  # noqa: F401

        # `refcoffee/__init__.py` rebinds `main` from the module to the function,
        # so reach for the modules through sys.modules rather than attributes.
        yield {
            name.split(".", 1)[1]: mod
            for name, mod in sys.modules.items()
            if name.startswith("refcoffee.")
        }
    finally:
        sys.path.remove(str(root))


@pytest.fixture(autouse=True)
def _matching_themes(reference):
    """Pin both implementations to the dark palette."""
    from coffee.theme import set_theme

    set_theme("dark")
    ref_theme = reference["theme"]
    ref_theme._theme_manager = ref_theme.ThemeManager(force_theme="dark")
    yield
    ref_theme._theme_manager = None


# ── panels ───────────────────────────────────────────────────────────────────
def test_computer_panel_is_identical(reference, render):
    from coffee.computer import get_computer_panel, regenerate_computer_cache

    data = regenerate_computer_cache()
    assert render(reference["computer"].get_computer_panel(data)) == render(
        get_computer_panel(data)
    )


def test_computer_panel_is_identical_with_no_data(reference, render):
    from coffee.computer import get_computer_panel

    assert render(reference["computer"].get_computer_panel({})) == render(get_computer_panel({}))


@pytest.mark.parametrize("height", [1, 2, 3, 4])
def test_power_panel_is_identical(reference, render, height):
    from coffee import power

    data = power.get_power_data()
    # The panel prints the cache timestamp; freeze it on both sides.
    power.cache_mtime = reference["power"].cache_mtime = 1_700_000_000.0
    assert render(reference["power"].get_power_visual(data, height)) == render(
        power.get_power_visual(data, height)
    )


@pytest.mark.parametrize("percentage", [0, 1, 9, 10, 55, 99, 100])
@pytest.mark.parametrize("charging", [False, True])
def test_battery_bar_is_identical(reference, percentage, charging):
    from coffee.power import get_bar

    assert reference["power"].get_bar(percentage, 1, charging) == get_bar(percentage, 1, charging)


@pytest.mark.parametrize("details", ["terse", "all"])
def test_network_panel_is_identical(reference, render, details):
    from coffee.network import get_network_panel

    assert render(reference["network"].get_network_panel(details)) == render(
        get_network_panel(details)
    )


def test_splash_fallback_is_identical(reference, render, tmp_path):
    from coffee.splash import get_splash_panel

    missing = tmp_path / "absent.aa"
    assert render(reference["splash"].get_splash_panel(missing)) == render(
        get_splash_panel(missing)
    )


def test_splash_art_is_identical(reference, render):
    from coffee.splash import get_splash_panel

    art = Path(__file__).resolve().parent.parent / "etc" / "coffee.aa"
    assert art.is_file(), art
    assert render(reference["splash"].get_splash_panel(art)) == render(get_splash_panel(art))


# ── the clock, which the reference builds inline inside main() ───────────────
@pytest.fixture(scope="module")
def reference_time_panel(reference):
    """Exec the reference's ``panel_time = Panel(...)`` statement verbatim."""
    source = (REFERENCE_PKG / "main.py").read_text(encoding="utf-8")
    fragment = textwrap.dedent(
        re.search(r"( *)panel_time = Panel\(\n.*?\n\1\)\n", source, re.S).group(0)
    )
    main = reference["main"]
    theme = reference["theme"]

    def build(now, secondary, up_for, memory_mb, tz):
        from rich.panel import Panel

        namespace = {
            "Panel": Panel,
            "palette": theme.get_palette(),
            "big_time": main.generate_ascii_time(now.strftime(main.TIME_FORMAT)),
            "UPTIME_HDR": main.UPTIME_HDR,
            "UPTIME_STR": main.UPTIME_STR,
            "uptime": main.get_uptime_str(up_for),
            "ist_str": secondary.strftime(main.TIME_FORMAT),
            "ist_dt_str": secondary.strftime(main.DATE_FORMAT),
            "date_str": now.strftime(main.DATE_FORMAT),
            "memory_mb": memory_mb,
            "tz": tz,
        }
        exec(fragment, namespace)
        return namespace["panel_time"]

    return build


@pytest.mark.parametrize(
    ("stamp", "up_for"),
    [
        (1_700_000_000.0, 0),
        (1_700_003_723.5, 1_234_567.0),
        (1_723_456_789.0, 86_399.0),
        (1_700_000_000.0, 359_999_999.0),
        (1_700_040_000.0, 3_600.0),
    ],
)
def test_time_panel_is_identical(reference_time_panel, render, stamp, up_for):
    from coffee.clock import build_time_panel

    tz = "America/New_York"
    now = datetime.fromtimestamp(stamp, pytz.timezone(tz))
    secondary = now.astimezone(pytz.timezone("Asia/Kolkata"))

    assert render(reference_time_panel(now, secondary, up_for, 33.33, tz)) == render(
        build_time_panel(now=now, secondary=secondary, up_for=up_for, memory_mb=33.33, tz=tz)
    )


# ── the text helpers behind the clock ────────────────────────────────────────
@pytest.mark.parametrize(
    "text", ["12:34:56 AM", "01:02:03 PM", "00:00:00 AM", "11:59:59 PM", "-+: ", "09:08:07 PM"]
)
def test_ascii_time_is_identical(reference, text):
    from coffee.clock import generate_ascii_time

    assert reference["main"].generate_ascii_time(text) == generate_ascii_time(text)


@pytest.mark.parametrize(("n", "width"), [(0, 4), (7, 2), (1234, 4), (59, 2), (100, 2), (9999, 4)])
def test_n2s_is_identical(reference, n, width):
    from coffee.clock import n2s

    assert reference["main"].n2s(n, width) == n2s(n, width)


@pytest.mark.parametrize("seconds", [0, 1, 59, 60, 3599, 86_399, 86_400, 1_234_567, 359_999_999])
def test_uptime_string_is_identical(reference, seconds):
    from coffee.clock import get_uptime_str

    assert reference["main"].get_uptime_str(seconds) == get_uptime_str(seconds)


def test_the_awake_pmset_settings_are_unchanged(reference):
    """The six settings the dashboard applies are part of the contract."""
    from coffee.pmset import AWAKE_SETTINGS

    reference_settings = [tuple(cmd[2:]) for cmd in reference["main"].PMSET_COMMANDS]
    assert reference_settings == [("-a", key, value) for key, value in AWAKE_SETTINGS]
