"""Parser wiring and the read-only sub-commands."""

from __future__ import annotations

import pytest

from coffee import cli


def _parse(*argv):
    return cli.build_parser().parse_args(list(argv))


def test_bare_invocation_dispatches_to_the_dashboard():
    """Typing `coffee` alone must keep doing what it always did."""
    args = _parse()
    assert getattr(args, "_handler", cli.cmd_run) is cli.cmd_run


def test_every_subcommand_has_a_handler():
    for command in ("run", "show", "power", "theme", "doctor", "config"):
        assert _parse(command)._handler is not None


def test_global_flags_work_before_and_after_the_subcommand():
    assert _parse("--dry-run", "power", "on").dry_run is True
    assert _parse("power", "on", "--dry-run").dry_run is True


def test_a_subcommand_does_not_clobber_an_earlier_global_flag():
    """The sub-parser copies default to SUPPRESS precisely so this holds."""
    assert _parse("--dry-run", "doctor").dry_run is True
    assert _parse("--theme", "light", "show").theme == "light"


def test_dashboard_flags_work_before_and_after_run():
    assert _parse("--tz", "UTC", "run").tz == "UTC"
    assert _parse("run", "--tz", "UTC").tz == "UTC"
    assert _parse("--splash", "run").splash is True
    assert _parse("run", "--no-caffeinate").caffeinate is False


def test_unknown_flag_is_a_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        _parse("--definitely-not-a-flag")
    assert excinfo.value.code == cli.EXIT_USAGE


def test_help_does_not_repeat_the_default():
    """rich-argparse-plus appends `(default: …)`; the formatter suppresses it."""
    import re

    # Help is hard-wrapped to the terminal width, so compare on one long line.
    text = re.sub(r"\s+", " ", cli.build_parser().format_help())
    assert "(default: auto — xlog, then sudo)" in text  # ours, written by hand
    assert "(default: auto)" not in text  # theirs, appended automatically
    assert "(default: True)" not in text  # and the one that reads backwards


def test_version_flag_prints_the_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        _parse("--version")
    assert excinfo.value.code == cli.EXIT_OK
    assert cli.get_version() in capsys.readouterr().out


def test_unknown_panel_is_rejected():
    args = _parse("show", "nonsense")
    ctx = cli.build_context(args)
    assert cli.cmd_show(ctx, args) == cli.EXIT_USAGE


def test_unknown_timezone_is_rejected():
    args = _parse("run", "--tz", "Mars/Olympus_Mons")
    assert cli.cmd_run(cli.build_context(args), args) == cli.EXIT_USAGE


def test_out_of_range_refresh_is_rejected():
    args = _parse("run", "--refresh", "0")
    assert cli.cmd_run(cli.build_context(args), args) == cli.EXIT_USAGE


def test_config_path_prints_the_path(tmp_path, capsys):
    target = tmp_path / "config.toml"
    args = _parse("--config", str(target), "config", "path")
    assert cli.cmd_config(cli.build_context(args), args) == cli.EXIT_OK
    assert capsys.readouterr().out.strip() == str(target)


def test_config_init_then_show(tmp_path):
    target = tmp_path / "config.toml"
    init = _parse("--config", str(target), "config", "init")
    assert cli.cmd_config(cli.build_context(init), init) == cli.EXIT_OK
    assert target.is_file()

    show = _parse("--config", str(target), "config", "show")
    assert cli.cmd_config(cli.build_context(show), show) == cli.EXIT_OK


def test_config_init_refuses_to_overwrite(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text("[display]\n", encoding="utf-8")
    args = _parse("--config", str(target), "config", "init")
    assert cli.cmd_config(cli.build_context(args), args) == cli.EXIT_FAILED
    assert target.read_text(encoding="utf-8") == "[display]\n"


def test_theme_json_reports_the_pinned_palette(capsys):
    import json

    args = _parse("--theme", "light", "theme", "--json")
    assert cli.cmd_theme(cli.build_context(args), args) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["theme"] == "light"
    assert payload["forced"] is True
    assert payload["palette"]["text_primary"] == "#000000"


def test_theme_auto_is_not_forced(capsys):
    import json

    args = _parse("--theme", "auto", "theme", "--json")
    assert cli.cmd_theme(cli.build_context(args), args) == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["forced"] is False
