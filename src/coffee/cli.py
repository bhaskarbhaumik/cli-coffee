"""Argument parsing and command dispatch for ``coffee``.

Running ``coffee`` with no sub-command starts the live dashboard — the way the
original script behaved, and the way muscle memory expects.  Everything else is
a sub-command hanging off that.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytz
from rich.box import ROUNDED
from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich_argparse_plus import RichHelpFormatterPlus

from coffee import __version__, ui
from coffee.config import CONFIG_PATH, TEMPLATE, Config
from coffee.console import make_console, make_error_console
from coffee.context import Context
from coffee.pmset import PmsetResult
from coffee.privilege import SUDO, XLOG, Backend, Escalator
from coffee.theme import LIGHT_THEME, get_palette, get_theme, set_theme

PROG = "coffee"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

PANELS = ("computer", "network", "power", "time", "splash")

EPILOG = """\
Examples:
  coffee                       the live dashboard — press any key to quit
  coffee run --tz UTC          the dashboard, on UTC
  coffee show power network    render single panels once and exit
  coffee power status          what pmset currently says
  coffee power on              apply the awake-friendly pmset settings
  coffee power off             put back whatever `coffee power on` replaced
  coffee doctor                check escalation, tooling and configuration
"""


class HelpFormatter(RichHelpFormatterPlus):
    """rich-argparse-plus, minus its automatic ``(default: …)`` suffix.

    Every default worth knowing is spelled out in the help text already, and the
    generated suffix reads backwards for ``store_false`` flags
    (``--no-caffeinate … (default: True)``).  The formatter appends it inside
    ``_escape_params_and_expand_help``, so hiding the default for the length of
    that one call is the only place to intercept it.
    """

    def _escape_params_and_expand_help(self, action: argparse.Action) -> Text:
        default = action.default
        action.default = argparse.SUPPRESS
        try:
            return super()._escape_params_and_expand_help(action)
        finally:
            action.default = default


def get_version() -> str:
    """The installed version, or a dev marker in a source checkout."""
    return __version__


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────


def _add_global_options(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """Global flags, accepted both before and after the sub-command.

    When *suppress* is true the flags default to ``argparse.SUPPRESS`` so a
    sub-parser copy never overwrites a value the top-level parser already set.
    """

    def d(value: object) -> object:
        return argparse.SUPPRESS if suppress else value

    run = parser.add_argument_group("run control")
    run.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        default=d(False),
        help="print each privileged command instead of running it",
    )
    run.add_argument(
        "-y",
        "--yes",
        dest="assume_yes",
        action="store_true",
        default=d(False),
        help="answer yes to every confirmation prompt",
    )
    run.add_argument(
        "--escalate",
        choices=("auto", "xlog", "sudo"),
        default=d("auto"),
        help="which root backend to use (default: auto — xlog, then sudo)",
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "-v", "--verbose", action="count", default=d(0), help="show more detail; repeatable"
    )
    out.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=d(False),
        help="suppress everything but errors",
    )
    out.add_argument("--no-color", action="store_true", default=d(False), help="disable colour")
    out.add_argument(
        "--width", type=int, metavar="COLS", default=d(None), help="force the output width"
    )
    out.add_argument(
        "--theme",
        choices=("auto", "light", "dark"),
        default=d(None),
        help="pin the palette instead of following the system appearance",
    )

    cfg = parser.add_argument_group("configuration")
    cfg.add_argument(
        "--config", metavar="FILE", default=d(None), help=f"config file (default: {CONFIG_PATH})"
    )


def _add_dashboard_options(parser: argparse.ArgumentParser, *, suppress: bool = False) -> None:
    """Flags that only make sense for the live dashboard.

    Accepted before *and* after ``run``; *suppress* keeps the sub-parser copy
    from clobbering a value the top-level parser already captured.
    """

    def d(value: object) -> object:
        return argparse.SUPPRESS if suppress else value

    group = parser.add_argument_group("dashboard")
    group.add_argument(
        "--tz",
        metavar="ZONE",
        default=d(None),
        help="primary timezone (default: $TZ, then the config file)",
    )
    group.add_argument(
        "-r",
        "--refresh",
        type=int,
        metavar="N",
        default=d(None),
        help="live refreshes per second (default: 4)",
    )
    group.add_argument(
        "--no-clear",
        dest="clear_screen",
        action="store_false",
        default=d(None),
        help="do not clear the screen on start or on resize",
    )
    group.add_argument(
        "--no-power",
        dest="configure_power",
        action="store_false",
        default=d(None),
        help="do not touch pmset on start",
    )
    group.add_argument(
        "--no-caffeinate",
        dest="caffeinate",
        action="store_false",
        default=d(None),
        help="render the dashboard without holding the machine awake",
    )
    group.add_argument(
        "--splash",
        action="store_true",
        default=d(False),
        help="show the ASCII-art splash in place of the computer panel",
    )


def build_parser() -> argparse.ArgumentParser:
    """The full multi-level parser."""
    HelpFormatter.choose_theme("the_lawn")

    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Keep an Apple Silicon Mac awake, with style — a live dashboard of "
            "machine, network, battery and clock that holds off sleep for as "
            "long as it runs."
        ),
        epilog=EPILOG,
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {get_version()}")
    _add_global_options(parser, suppress=False)
    _add_dashboard_options(parser)

    inherited = argparse.ArgumentParser(add_help=False, formatter_class=HelpFormatter)
    _add_global_options(inherited, suppress=True)

    subs = parser.add_subparsers(dest="command", metavar="COMMAND")

    def sub(name: str, help_: str, **kw: object) -> argparse.ArgumentParser:
        return subs.add_parser(
            name,
            help=help_,
            description=kw.pop("description", help_),  # type: ignore[arg-type]
            parents=[inherited],
            formatter_class=HelpFormatter,
            **kw,  # type: ignore[arg-type]
        )

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub(
        "run",
        "start the live dashboard (the default)",
        description=(
            "Start the live dashboard. Applies the awake-friendly pmset "
            "settings, holds the machine awake with caffeinate(8), and renders "
            "until a key is pressed."
        ),
    )
    _add_dashboard_options(p_run, suppress=True)
    p_run.set_defaults(_handler=cmd_run)

    # ── show ─────────────────────────────────────────────────────────────────
    p_show = sub(
        "show",
        "render one or more panels once and exit",
        description="Draw the named panels a single time. Changes nothing.",
        epilog="Panels: " + ", ".join(PANELS),
    )
    p_show.add_argument(
        "panels",
        nargs="*",
        metavar="PANEL",
        default=[],
        help="which panels to draw (default: all but splash)",
    )
    p_show.add_argument(
        "--rows", action="store_true", help="stack the panels vertically instead of side by side"
    )
    p_show.set_defaults(_handler=cmd_show)

    # ── power ────────────────────────────────────────────────────────────────
    p_power = sub(
        "power",
        "inspect or change the macOS power settings",
        description=(
            "The six pmset settings the dashboard applies: sleep, disksleep, "
            "displaysleep, womp, ring and powernap. Writing them needs root, "
            "which comes from xlog when available and sudo otherwise."
        ),
    )
    power_subs = p_power.add_subparsers(dest="power_action", metavar="ACTION")

    pp_status = power_subs.add_parser(
        "status",
        help="show the current pmset values",
        description="Show the current pmset values.",
        parents=[inherited],
        formatter_class=HelpFormatter,
    )
    pp_status.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    pp_status.add_argument(
        "--all",
        dest="show_all",
        action="store_true",
        help="show every pmset setting, not just the six coffee touches",
    )

    power_subs.add_parser(
        "on",
        help="apply the awake-friendly settings",
        description=(
            "Apply the awake-friendly settings, snapshotting the current values "
            "first so `coffee power off` can put them back."
        ),
        parents=[inherited],
        formatter_class=HelpFormatter,
    )

    pp_off = power_subs.add_parser(
        "off",
        help="restore the settings coffee replaced",
        description=(
            "Restore the values recorded by the last `coffee power on`. With "
            "--defaults, hand every power setting back to macOS instead."
        ),
        parents=[inherited],
        formatter_class=HelpFormatter,
    )
    pp_off.add_argument(
        "--defaults",
        action="store_true",
        help="run `pmset -a restoredefaults` instead of restoring the snapshot",
    )

    p_power.set_defaults(_handler=cmd_power, power_action=None)

    # ── theme ────────────────────────────────────────────────────────────────
    p_theme = sub(
        "theme",
        "show the detected theme and its palette",
        description="Report which palette coffee would draw with, and preview it.",
    )
    p_theme.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    p_theme.set_defaults(_handler=cmd_theme)

    # ── doctor ───────────────────────────────────────────────────────────────
    p_doctor = sub(
        "doctor",
        "check escalation, tooling and configuration",
        description="Verify that coffee can do its job before you rely on it.",
    )
    p_doctor.set_defaults(_handler=cmd_doctor)

    # ── config ───────────────────────────────────────────────────────────────
    p_config = sub("config", "inspect or create the configuration file")
    config_subs = p_config.add_subparsers(dest="config_action", metavar="ACTION")
    for name, helptext in (
        ("show", "print the effective configuration"),
        ("path", "print the config file path"),
        ("init", "write a commented template config file"),
        ("edit", "open the config file in $EDITOR"),
    ):
        cp = config_subs.add_parser(
            name, help=helptext, description=helptext, formatter_class=HelpFormatter
        )
        if name == "init":
            cp.add_argument("--force", action="store_true", help="overwrite an existing file")
    p_config.set_defaults(_handler=cmd_config, config_action=None)

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────


def build_context(args: argparse.Namespace) -> Context:
    """Assemble the context every handler is given."""
    cfg = Config.load(getattr(args, "config", None))

    theme = getattr(args, "theme", None) or cfg.theme
    set_theme(None if theme == "auto" else theme)

    width = getattr(args, "width", None)
    console = make_console(
        no_color=bool(getattr(args, "no_color", False)),
        width=width,
    )

    escalate = getattr(args, "escalate", "auto") or "auto"
    escalator = Escalator(
        prefer={"xlog": Backend.XLOG, "sudo": Backend.SUDO}.get(escalate),
        allow_sudo=escalate != "xlog",
        dry_run=bool(getattr(args, "dry_run", False)),
    )

    return Context(
        console=console,
        error_console=make_error_console(width=width),
        escalator=escalator,
        config=cfg,
        dry_run=bool(getattr(args, "dry_run", False)),
        assume_yes=bool(getattr(args, "assume_yes", False)),
        quiet=bool(getattr(args, "quiet", False)),
        verbose=int(getattr(args, "verbose", 0) or 0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────


def cmd_run(ctx: Context, args: argparse.Namespace) -> int:
    """Start the live dashboard."""
    from coffee.dashboard import run_dashboard

    tz = getattr(args, "tz", None) or os.environ.get("TZ") or ctx.config.tz
    for zone, label in ((tz, "--tz"), (ctx.config.secondary_tz, "secondary_tz")):
        if zone not in pytz.all_timezones_set:
            ctx.console.print(ui.notice(f"unknown timezone for {label}: {zone}", kind="error"))
            return EXIT_USAGE

    refresh = getattr(args, "refresh", None)
    if refresh is not None and not 1 <= refresh <= 60:
        ctx.console.print(ui.notice("--refresh must be between 1 and 60", kind="error"))
        return EXIT_USAGE

    if not ctx.is_macos:
        ctx.warn("⚠️  coffee targets macOS; power management and system_profiler will not work")

    return run_dashboard(
        ctx,
        tz=tz,
        refresh=refresh,
        clear_screen=getattr(args, "clear_screen", None),
        configure_power=getattr(args, "configure_power", None),
        caffeinate=getattr(args, "caffeinate", None),
        use_splash=bool(getattr(args, "splash", False)),
    )


def cmd_show(ctx: Context, args: argparse.Namespace) -> int:
    """Render one or more panels once."""
    from coffee.computer import get_computer_panel, regenerate_computer_cache
    from coffee.network import get_network_panel
    from coffee.power import get_power_data, get_power_visual
    from coffee.splash import get_splash_panel

    requested: list[str] = list(getattr(args, "panels", []) or [])
    unknown = [p for p in requested if p not in PANELS and p != "all"]
    if unknown:
        ctx.console.print(
            ui.notice(
                f"unknown panel: {', '.join(unknown)} — pick from {', '.join(PANELS)} or all",
                kind="error",
            )
        )
        return EXIT_USAGE
    if not requested or "all" in requested:
        requested = ["computer", "network", "power", "time"]

    builders = {
        "computer": lambda: get_computer_panel(regenerate_computer_cache()),
        "network": get_network_panel,
        "power": lambda: get_power_visual(get_power_data()),
        "splash": lambda: get_splash_panel(ctx.config.splash_path),
        "time": lambda: _time_panel_now(ctx),
    }

    panels = []
    failed = False
    seen: set[str] = set()
    for name in requested:
        if name in seen:
            continue
        seen.add(name)
        try:
            panels.append(builders[name]())
        except Exception as exc:
            failed = True
            ctx.console.print(ui.notice(f"{name}: {exc}", kind="error"))

    if not panels:
        return EXIT_FAILED

    if getattr(args, "rows", False):
        for panel in panels:
            ctx.console.print(panel)
    else:
        ctx.console.print(Columns(panels))
    return EXIT_FAILED if failed else EXIT_OK


def _time_panel_now(ctx: Context) -> Panel:
    """The clock panel for this instant — used by ``coffee show time``."""
    import time
    from datetime import datetime

    import psutil

    from coffee.clock import build_time_panel

    tz = os.environ.get("TZ") or ctx.config.tz
    now = datetime.now(pytz.timezone(tz))
    process = psutil.Process(os.getpid())
    return build_time_panel(
        now=now,
        secondary=now.astimezone(pytz.timezone(ctx.config.secondary_tz)),
        up_for=time.time() - psutil.boot_time(),
        memory_mb=process.memory_info().rss / 1024**2,
        tz=tz,
    )


def cmd_power(ctx: Context, args: argparse.Namespace) -> int:
    """Inspect or change the macOS power settings."""
    from coffee import pmset

    action = getattr(args, "power_action", None) or "status"

    if not ctx.is_macos:
        ctx.console.print(ui.notice("pmset is macOS-only", kind="error"))
        return EXIT_FAILED

    if action == "status":
        return _power_status(ctx, args)

    if action == "on":
        try:
            current = pmset.read_settings()
        except pmset.PmsetError as exc:
            ctx.console.print(ui.notice(str(exc), kind="error"))
            return EXIT_FAILED
        commands = pmset.awake_commands()
        if ctx.dry_run:
            ctx.console.print(
                ui.command_panel([ctx.escalator.wrap(c) for c in commands], title="power on")
            )
            return EXIT_OK
        if not _ensure_root(ctx):
            return EXIT_FAILED
        saved = pmset.save_snapshot(current)
        results = pmset.apply_awake_settings(ctx.escalator)
        return _report_pmset(ctx, results, done="awake-friendly settings applied", saved=saved)

    # off
    if getattr(args, "defaults", False):
        if ctx.dry_run:
            ctx.console.print(
                ui.command_panel(
                    [r.argv for r in pmset.restore_macos_defaults(ctx.escalator, dry_run=True)],
                    title="power off --defaults",
                )
            )
            return EXIT_OK
        if not _confirm(ctx, "Hand every power setting back to macOS defaults?"):
            ctx.console.print(ui.notice("Aborted.", kind="warn"))
            return EXIT_INTERRUPTED
        if not _ensure_root(ctx):
            return EXIT_FAILED
        return _report_pmset(
            ctx, pmset.restore_macos_defaults(ctx.escalator), done="macOS power defaults restored"
        )

    snapshot = pmset.load_snapshot()
    if not snapshot:
        ctx.console.print(
            ui.notice(
                f"no snapshot at [bold]{pmset.STATE_PATH}[/bold] — run "
                "[bold]coffee power on[/bold] first, or "
                "[bold]coffee power off --defaults[/bold] to reset to macOS defaults.",
                kind="warn",
            )
        )
        return EXIT_FAILED

    if ctx.dry_run:
        ctx.console.print(
            ui.command_panel(
                [r.argv for r in pmset.restore_previous(ctx.escalator, snapshot, dry_run=True)],
                title="power off",
            )
        )
        return EXIT_OK
    if not _ensure_root(ctx):
        return EXIT_FAILED
    return _report_pmset(
        ctx, pmset.restore_previous(ctx.escalator, snapshot), done="previous settings restored"
    )


def _power_status(ctx: Context, args: argparse.Namespace) -> int:
    """Render the current pmset values."""
    from coffee import pmset

    try:
        settings = pmset.read_settings()
    except pmset.PmsetError as exc:
        ctx.console.print(ui.notice(str(exc), kind="error"))
        return EXIT_FAILED

    show_all = bool(getattr(args, "show_all", False))
    keys = [k for k, _ in pmset.AWAKE_SETTINGS]
    wanted = {"AC Power", "Battery Power", "UPS Power"}
    sources = [s for s in settings if s in wanted] or list(settings)

    if getattr(args, "json", False):
        payload = {
            source: (
                settings[source]
                if show_all
                else {k: v for k, v in settings[source].items() if k in keys}
            )
            for source in sources
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return EXIT_OK

    palette = get_palette()
    table = Table(
        show_header=True,
        show_edge=False,
        show_lines=False,
        box=ROUNDED,
        border_style=palette.border_secondary,
        padding=(0, 1),
    )
    table.add_column("setting", style=palette.accent_cyan, no_wrap=True)
    for source in sources:
        table.add_column(source, style=palette.accent_magenta, justify="center", no_wrap=True)

    rows = sorted({k for s in sources for k in settings[s]}) if show_all else keys
    awake = dict(pmset.AWAKE_SETTINGS)
    for key in rows:
        cells = []
        for source in sources:
            value = settings[source].get(key, "—")
            if not show_all and key in awake and value == awake[key]:
                value = f"[{palette.status_success}]{value}[/{palette.status_success}]"
            cells.append(str(value))
        table.add_row(key, *cells)

    ctx.console.print()
    ctx.console.print(
        Panel(
            table,
            title=f"[{palette.text_highlight}]\uf0e7[/{palette.text_highlight}]  "
            f"[{palette.accent_green}]pmset[/{palette.accent_green}]",
            subtitle=Text(
                "green = as coffee wants it" if not show_all else "",
                style=palette.text_dim,
            ),
            subtitle_align="right",
            border_style=palette.border_primary,
            expand=False,
            padding=(0, 1),
        )
    )
    snapshot = pmset.load_snapshot()
    if snapshot:
        ctx.say(ui.notice(f"snapshot on disk: [bold]{pmset.STATE_PATH}[/bold]", kind="info"))
    return EXIT_OK


def _report_pmset(
    ctx: Context,
    results: Sequence[PmsetResult],
    *,
    done: str,
    saved: Path | None = None,
) -> int:
    """Summarise a batch of pmset writes."""
    failures = [r for r in results if not r.ok]
    for result in failures:
        ctx.console.print(ui.notice(f"{' '.join(result.argv)} — {result.message}", kind="error"))
    if failures:
        return EXIT_FAILED
    message = done
    if saved is not None:
        message += f" (previous values saved to [bold]{saved}[/bold])"
    ctx.say(ui.notice(message, kind="ok"))
    return EXIT_OK


def _ensure_root(ctx: Context) -> bool:
    """Acquire root once, up front, explaining the failure if it does not work."""
    if ctx.escalator.prime(interactive=sys.stdin.isatty()):
        return True
    ctx.console.print(
        ui.notice(
            "could not obtain root — "
            f"{ctx.escalator.report().detail}. Try [bold]coffee doctor[/bold].",
            kind="error",
        )
    )
    return False


def _confirm(ctx: Context, question: str) -> bool:
    """Ask before something irreversible, unless ``--yes`` or non-interactive."""
    if ctx.assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        answer = ctx.console.input(f"{question} [dim](y/N)[/dim] ")
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().lower() in {"y", "yes"}


def cmd_theme(ctx: Context, args: argparse.Namespace) -> int:
    """Show the detected theme and preview its palette."""
    theme = get_theme()
    palette = theme.palette

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "theme": theme.current_theme_name,
                    "forced": theme.is_forced,
                    "palette": {
                        field: getattr(palette, field)
                        for field in type(palette).__dataclass_fields__
                    },
                },
                indent=2,
            )
        )
        return EXIT_OK

    swatch = Table(
        show_header=True,
        show_edge=False,
        box=ROUNDED,
        border_style=palette.border_secondary,
        padding=(0, 1),
    )
    swatch.add_column("token", style=palette.accent_cyan, no_wrap=True)
    swatch.add_column("style", style=palette.text_dim, no_wrap=True)
    swatch.add_column("sample", no_wrap=True)
    for field in type(palette).__dataclass_fields__:
        style = getattr(palette, field)
        swatch.add_row(field, style, f"[{style}]▉▉▉ sample[/{style}]")

    origin = "pinned" if theme.is_forced else "detected"
    ctx.console.print()
    ctx.console.print(
        Panel(
            swatch,
            title=f"[{palette.text_highlight}]\uf1fc[/{palette.text_highlight}]  "
            f"[{palette.accent_green}]{theme.current_theme_name} theme[/{palette.accent_green}]",
            subtitle=Text(
                f"{origin} — {'light' if palette is LIGHT_THEME else 'dark'} palette",
                style=palette.text_dim,
            ),
            subtitle_align="right",
            border_style=palette.border_primary,
            expand=False,
            padding=(0, 1),
        )
    )
    return EXIT_OK


def cmd_doctor(ctx: Context, args: argparse.Namespace) -> int:
    """Check escalation, tooling and configuration."""
    rows: list[tuple[str, bool | None, str]] = []

    rows.append(("platform", ctx.is_macos, f"{platform.system()} {ctx.macos_version} ({ctx.arch})"))
    rows.append(
        (
            "apple silicon",
            ctx.is_apple_silicon,
            "arm64" if ctx.is_apple_silicon else f"{ctx.arch} — coffee targets Apple Silicon",
        )
    )
    rows.append(("python", True, f"{platform.python_version()} at {sys.executable}"))
    rows.append(("coffee", True, f"{get_version()} at {shutil.which(PROG) or sys.argv[0]}"))

    rep = ctx.escalator.report()
    rows.append(("root escalation", rep.backend is not Backend.NONE, rep.detail))
    rows.append(
        (
            "xlog",
            rep.xlog_works if rep.xlog_present else False,
            f"{XLOG} runs commands as uid 0"
            if rep.xlog_works
            else (
                f"{XLOG} present but not usable" if rep.xlog_present else f"{XLOG} not installed"
            ),
        )
    )
    rows.append(
        ("sudo", rep.sudo_present, f"{SUDO} present" if rep.sudo_present else f"{SUDO} missing")
    )

    for tool in ("system_profiler", "pmset", "caffeinate"):
        path = shutil.which(tool)
        rows.append((tool, path is not None, path or "not found on PATH"))

    cfg = ctx.config
    if cfg.errors:
        rows.append(("config", False, f"{cfg.path}: " + "; ".join(cfg.errors)))
    elif cfg.exists:
        rows.append(("config", True, f"loaded {cfg.path}"))
    else:
        rows.append(("config", None, f"none at {cfg.path} — using defaults (coffee config init)"))

    for label, zone in (("timezone", cfg.tz), ("secondary timezone", cfg.secondary_tz)):
        known = zone in pytz.all_timezones_set
        rows.append((label, known, zone if known else f"{zone} — unknown timezone"))

    theme = get_theme()
    rows.append(
        (
            "theme",
            True,
            f"{theme.current_theme_name} ({'pinned' if theme.is_forced else 'detected'})",
        )
    )

    splash = cfg.splash_path
    if splash is not None:
        rows.append(("splash art", splash.is_file(), str(splash)))

    from coffee import pmset

    rows.append(
        (
            "pmset snapshot",
            None if not pmset.STATE_PATH.exists() else True,
            str(pmset.STATE_PATH) if pmset.STATE_PATH.exists() else "none saved yet",
        )
    )

    # Not a failure — plenty of legitimate uses pipe doctor into a file.
    stdin_tty = sys.stdin.isatty()
    rows.append(
        (
            "terminal",
            True if stdin_tty else None,
            "interactive — press any key to quit the dashboard"
            if stdin_tty
            else "stdin is not a tty; the dashboard cannot be quit with a keypress",
        )
    )

    ctx.console.print()
    ctx.console.print(ui.check_panel(rows))
    return EXIT_FAILED if any(row[1] is False for row in rows) else EXIT_OK


def cmd_config(ctx: Context, args: argparse.Namespace) -> int:
    """Inspect or create the configuration file."""
    action = getattr(args, "config_action", None) or "show"
    cfg = ctx.config

    if action == "path":
        print(cfg.path)
        return EXIT_OK

    if action == "init":
        ok, message = cfg.write_template(force=bool(getattr(args, "force", False)))
        ctx.console.print(
            ui.notice(
                f"wrote [bold]{message}[/bold]" if ok else message, kind="ok" if ok else "warn"
            )
        )
        return EXIT_OK if ok else EXIT_FAILED

    if action == "edit":
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        if not cfg.path.exists():
            cfg.write_template()
        try:
            return subprocess.call([*editor.split(), str(cfg.path)])
        except OSError as exc:
            ctx.console.print(ui.notice(f"could not launch {editor}: {exc}", kind="error"))
            return EXIT_FAILED

    # show
    from rich.syntax import Syntax

    palette = get_palette()
    if cfg.exists:
        body = Syntax(
            cfg.path.read_text(encoding="utf-8"),
            "toml",
            theme="ansi_dark",
            line_numbers=True,
            background_color="default",
        )
        subtitle = str(cfg.path)
    else:
        body = Syntax(TEMPLATE, "toml", theme="ansi_dark", background_color="default")
        subtitle = f"{cfg.path} does not exist — this is the default template"

    ctx.console.print()
    ctx.console.print(
        Panel(
            body,
            title=f"[{palette.text_highlight}]\uf013[/{palette.text_highlight}]  "
            f"[{palette.accent_green}]config[/{palette.accent_green}]",
            subtitle=Text(subtitle, style=palette.text_dim),
            subtitle_align="right",
            border_style=palette.border_primary,
            box=ROUNDED,
            padding=(1, 1),
            expand=False,
        )
    )
    if ctx.verbose:
        effective = Table(show_header=False, show_edge=False, box=None, padding=(0, 1))
        effective.add_column(style=palette.accent_cyan)
        effective.add_column(style=palette.accent_magenta)
        for key, value in cfg.as_dict().items():
            effective.add_row(key, str(value))
        ctx.console.print(
            Panel(effective, title="effective", border_style=palette.border_secondary, expand=False)
        )
    if cfg.errors:
        ctx.console.print(ui.notice("; ".join(cfg.errors), kind="warn"))
    return EXIT_OK


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* and dispatch. Bare ``coffee`` starts the dashboard."""
    parser = build_parser()
    args = parser.parse_args(argv)

    ctx = build_context(args)
    handler = getattr(args, "_handler", cmd_run)

    try:
        return handler(ctx, args)
    except KeyboardInterrupt:
        ctx.console.print()
        ctx.console.print(ui.notice("Interrupted.", kind="warn"))
        return EXIT_INTERRUPTED
    except BrokenPipeError:  # piping into head(1)
        return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
