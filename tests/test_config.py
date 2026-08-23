"""Config loading is deliberately forgiving: it reports problems, never raises."""

from __future__ import annotations

from coffee.config import DEFAULT_REFRESH, DEFAULT_TZ, Config


def test_missing_file_yields_defaults(tmp_path):
    cfg = Config.load(tmp_path / "nope.toml")
    assert not cfg.exists
    assert cfg.errors == []
    assert cfg.tz == DEFAULT_TZ
    assert cfg.refresh == DEFAULT_REFRESH
    assert cfg.caffeinate is True


def test_values_are_read(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
        [display]
        tz = "UTC"
        secondary_tz = "Europe/Berlin"
        refresh = 8
        clear_screen = false
        theme = "light"
        splash = "~/art.aa"

        [intervals]
        power = 60
        network = 120
        theme = 2

        [power]
        configure_on_start = false
        caffeinate = false
        """,
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.exists and cfg.errors == []
    assert (cfg.tz, cfg.secondary_tz, cfg.refresh) == ("UTC", "Europe/Berlin", 8)
    assert cfg.clear_screen is False
    assert cfg.theme == "light"
    assert cfg.splash_path is not None and cfg.splash_path.is_absolute()
    assert (cfg.power_interval, cfg.network_interval, cfg.theme_interval) == (60, 120, 2)
    assert cfg.configure_on_start is False and cfg.caffeinate is False


def test_bad_types_are_reported_and_defaulted(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """
        [display]
        tz = 42
        refresh = "fast"
        theme = "neon"
        """,
        encoding="utf-8",
    )
    cfg = Config.load(path)
    assert cfg.tz == DEFAULT_TZ
    assert cfg.refresh == DEFAULT_REFRESH
    assert cfg.theme == "auto"
    assert len(cfg.errors) == 3


def test_out_of_range_refresh_is_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[display]\nrefresh = 0\n", encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.refresh == DEFAULT_REFRESH
    assert any("refresh" in e for e in cfg.errors)


def test_unparseable_toml_is_reported(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not = = toml", encoding="utf-8")
    cfg = Config.load(path)
    assert cfg.exists
    assert cfg.errors
    assert cfg.tz == DEFAULT_TZ


def test_template_round_trips(tmp_path):
    path = tmp_path / "config.toml"
    wrote, message = Config(path=path).write_template()
    assert wrote, message

    cfg = Config.load(path)
    assert cfg.errors == []
    assert cfg.tz == DEFAULT_TZ

    wrote_again, message = Config(path=path).write_template()
    assert not wrote_again and "already exists" in message
    assert Config(path=path).write_template(force=True)[0]
