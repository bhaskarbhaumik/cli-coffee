"""Theme detection and the light/dark palettes."""

from __future__ import annotations

import subprocess

import pytest

from coffee import theme
from coffee.theme import DARK_THEME, LIGHT_THEME, ColorPalette, ThemeManager, detect_theme


def _no_macos_probe(monkeypatch):
    """Make the macOS `defaults read` probe unavailable, so env vars decide."""
    monkeypatch.setattr(theme.sys, "platform", "linux")


def test_the_two_palettes_define_every_token():
    tokens = set(ColorPalette.__dataclass_fields__)
    for palette in (DARK_THEME, LIGHT_THEME):
        assert {f for f in tokens if getattr(palette, f)} == tokens


def test_colorfgbg_light_background(monkeypatch):
    monkeypatch.setenv("COLORFGBG", "0;15")
    assert detect_theme() == "light"


def test_colorfgbg_dark_background(monkeypatch):
    monkeypatch.setenv("COLORFGBG", "15;0")
    assert detect_theme() == "dark"


def test_malformed_colorfgbg_falls_through(monkeypatch):
    monkeypatch.setenv("COLORFGBG", "default;default")
    _no_macos_probe(monkeypatch)
    monkeypatch.setenv("LIGHT_MODE", "1")
    assert detect_theme() == "light"


def test_macos_appearance_is_consulted(monkeypatch):
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setattr(theme.sys, "platform", "darwin")
    monkeypatch.setattr(
        theme.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "Dark\n", ""),
    )
    assert detect_theme() == "dark"

    monkeypatch.setattr(
        theme.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "does not exist"),
    )
    assert detect_theme() == "light"


def test_a_hanging_defaults_probe_does_not_hang_us(monkeypatch):
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setattr(theme.sys, "platform", "darwin")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("defaults", 1)

    monkeypatch.setattr(theme.subprocess, "run", timeout)
    monkeypatch.delenv("DARK_MODE", raising=False)
    monkeypatch.delenv("LIGHT_MODE", raising=False)
    assert detect_theme() == "dark"  # the documented fallback


def test_default_is_dark(monkeypatch):
    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.delenv("DARK_MODE", raising=False)
    monkeypatch.delenv("LIGHT_MODE", raising=False)
    _no_macos_probe(monkeypatch)
    assert detect_theme() == "dark"


@pytest.mark.parametrize("name", ["light", "LIGHT", " Light "])
def test_forcing_is_case_and_space_insensitive(name):
    assert ThemeManager(name).palette is LIGHT_THEME


@pytest.mark.parametrize("name", ["auto", "", None, "chartreuse"])
def test_unrecognised_force_values_mean_auto_detect(name, monkeypatch):
    monkeypatch.setenv("COLORFGBG", "0;15")
    manager = ThemeManager(name)
    assert not manager.is_forced
    assert manager.current_theme_name == "light"


def test_a_pinned_theme_never_refreshes(monkeypatch):
    manager = ThemeManager("dark")
    monkeypatch.setenv("COLORFGBG", "0;15")  # would otherwise detect light
    assert manager.has_theme_changed() is False
    assert manager.refresh_theme() is False
    assert manager.palette is DARK_THEME


def test_refresh_swaps_the_palette_once(monkeypatch):
    monkeypatch.setenv("COLORFGBG", "15;0")
    manager = ThemeManager()
    assert manager.palette is DARK_THEME

    monkeypatch.setenv("COLORFGBG", "0;15")
    assert manager.has_theme_changed() is True
    assert manager.refresh_theme() is True
    assert manager.palette is LIGHT_THEME
    assert manager.refresh_theme() is False  # nothing left to change
