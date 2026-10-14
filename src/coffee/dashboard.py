"""The live dashboard — four panels, refreshed forever, machine held awake.

Layout and cadence are the visual contract:

* ``Columns([computer, network, power, time])``, right-aligned;
* four refreshes a second, so the seconds digit never looks like it stutters;
* the battery panel re-reads every 5 minutes and the network panel every hour,
  because both cost a ``system_profiler`` call;
* the theme is re-checked every 5 seconds, and a change rebuilds every panel.

Hotkeys (see :mod:`coffee.keys`): ``r`` refreshes every panel, ``q`` or
``Esc`` quits, and any other key floats a hotkey help popup over the panels
until ``Esc`` closes it. With no popup open, the frame is exactly the
four-column layout above.
"""

from __future__ import annotations

import contextlib
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psutil
import pytz
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, RenderableType
from rich.live import Live
from rich.panel import Panel

from coffee.clock import build_time_panel
from coffee.computer import get_computer_panel, regenerate_computer_cache
from coffee.context import Context
from coffee.keys import Action, KeyboardWatcher
from coffee.network import get_network_panel
from coffee.overlay import Overlay, hotkey_help_panel
from coffee.pmset import apply_awake_settings
from coffee.power import get_power_data, get_power_visual
from coffee.splash import get_splash_panel
from coffee.theme import refresh_theme

__all__ = ["SECONDS_PER_YEAR", "Action", "Dashboard", "KeyboardWatcher", "run_dashboard"]

SECONDS_PER_YEAR = 31_536_000
SLEEP_INTERVAL = 0.4
CAFFEINATE_FLAGS = ["-dimsu", "-t", str(SECONDS_PER_YEAR)]
_CAFFEINATE_GRACE = 2.0


@dataclass(slots=True)
class _Screen:
    """The panels currently on screen, and when the expensive ones were fetched."""

    computer_data: dict[str, Any]
    leading: Panel
    power: Panel
    network: Panel
    last_power_update: float
    last_network_update: float
    time: Panel | None = None
    help: bool = False


@dataclass(slots=True)
class Dashboard:
    """Owns the panels, the refresh cadence and the awake-keeping side effects."""

    ctx: Context
    console: Console
    tz: str
    secondary_tz: str
    refresh_per_second: int
    clear_screen: bool
    power_interval: int
    network_interval: int
    theme_interval: int
    configure_power: bool
    caffeinate: bool
    use_splash: bool = False

    _stop: threading.Event = field(default_factory=threading.Event)
    _actions: queue.SimpleQueue[Action] = field(default_factory=queue.SimpleQueue)

    # ── side effects ─────────────────────────────────────────────────────────
    def stop(self) -> None:
        """Ask the render loop to finish at the end of this frame."""
        self._stop.set()

    def configure_power_settings(self) -> None:
        """Apply the awake-friendly ``pmset`` settings, reporting any that fail."""
        if not self.ctx.is_macos:
            print("⚠️  Power management settings only work on macOS")
            return
        for result in apply_awake_settings(self.ctx.escalator, dry_run=self.ctx.dry_run):
            if not result.ok:
                self.ctx.warn(
                    f"[bold red]⚠️  Failed to execute command {result.argv}: "
                    f"{result.message}[/bold red]"
                )

    def start_caffeinate(self) -> subprocess.Popen[bytes] | None:
        """Hold the machine awake. Returns the process, or None if it could not start."""
        if not self.ctx.is_macos:
            print("⚠️  caffeinate only works on macOS")
            return None
        if self.ctx.dry_run:
            return None
        try:
            return subprocess.Popen(["caffeinate", *CAFFEINATE_FLAGS])
        except FileNotFoundError as exc:
            self.ctx.warn(f"[bold red]⚠️  caffeinate command not found: {exc}[/bold red]")
        except (OSError, subprocess.SubprocessError) as exc:
            self.ctx.warn(f"[bold red]⚠️  Failed to start caffeinate: {exc}[/bold red]")
        return None

    def _stop_caffeinate(self, process: subprocess.Popen[bytes] | None) -> None:
        """Terminate caffeinate, escalating to a kill if it will not go."""
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=_CAFFEINATE_GRACE)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=_CAFFEINATE_GRACE)
            except (OSError, subprocess.SubprocessError):
                pass
        except (OSError, subprocess.SubprocessError):
            pass

    # ── panels ───────────────────────────────────────────────────────────────
    def _safe_panel(self, build, label: str, error: str) -> Panel:
        """Render *build*, or a red placeholder panel if it raises."""
        try:
            return build()
        except Exception as exc:  # a dead panel must not take the dashboard with it
            self.ctx.warn(f"⚠️  Error while fetching {label}: {exc}")
            return Panel(error, border_style="red")

    def power_panel(self, *, force: bool = False) -> Panel:
        return self._safe_panel(
            lambda: get_power_visual(get_power_data(force=force)),
            "power visual",
            "⚠️  Error fetching power data",
        )

    def network_panel(self) -> Panel:
        return self._safe_panel(
            get_network_panel, "network panel", "⚠️  Error fetching network data"
        )

    def splash_panel(self) -> Panel:
        return self._safe_panel(
            lambda: get_splash_panel(self.ctx.config.splash_path),
            "splash panel",
            "⚠️  Error fetching splash image",
        )

    def computer_panel(self, computer_data: dict[str, Any]) -> Panel:
        return self._safe_panel(
            lambda: get_computer_panel(computer_data),
            "computer panel",
            "⚠️  Error fetching computer data",
        )

    def leading_panel(self, computer_data: dict[str, Any]) -> Panel:
        """The first column: the splash image or the computer panel."""
        return self.splash_panel() if self.use_splash else self.computer_panel(computer_data)

    def collect_computer_data(self) -> dict[str, Any]:
        """Run ``system_profiler`` for the computer panel; ``{}`` if it fails."""
        try:
            return regenerate_computer_cache()
        except Exception as exc:
            self.ctx.warn(f"⚠️  Error while collecting computer info: {exc}")
            return {}

    # ── hotkeys ──────────────────────────────────────────────────────────────
    def refresh_all(self, screen: _Screen) -> None:
        """Re-fetch every panel now, bypassing the caches and the timers."""
        refresh_theme()
        now = time.time()
        screen.computer_data = self.collect_computer_data()
        screen.leading = self.leading_panel(screen.computer_data)
        screen.power = self.power_panel(force=True)
        screen.network = self.network_panel()
        screen.last_power_update = now
        screen.last_network_update = now

    def handle(self, action: Action, screen: _Screen) -> None:
        """Apply one hotkey to *screen*, or ask the loop to stop."""
        if action is Action.QUIT:
            self._stop.set()
        elif action is Action.ESCAPE:
            if screen.help:
                screen.help = False
            else:
                self._stop.set()
        elif action is Action.REFRESH:
            self.refresh_all(screen)
        else:
            screen.help = True

    def frame(self, screen: _Screen) -> RenderableType:
        """The renderable for *screen*: the four columns, plus the popup if open."""
        panels = [screen.leading, screen.network, screen.power]
        if screen.time is not None:
            panels.append(screen.time)
        dashboard = Align.right(Columns(panels))
        return Overlay(dashboard, hotkey_help_panel()) if screen.help else dashboard

    def _idle(self, seconds: float, screen: _Screen, live: Live) -> None:
        """Wait out one beat, acting on — and redrawing for — any hotkeys."""
        deadline = time.monotonic() + seconds
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                action = self._actions.get(timeout=remaining)
            except queue.Empty:
                return
            self.handle(action, screen)
            if not self._stop.is_set():
                live.update(self.frame(screen), refresh=True)

    # ── the loop ─────────────────────────────────────────────────────────────
    def run(self) -> int:
        """Draw until ``q``/``Esc`` is pressed, the process is signalled, or a panel dies."""
        keys = KeyboardWatcher(self._actions.put)
        keys.start()
        restore_signals = self._install_signal_handlers()
        caffeinate_process: subprocess.Popen[bytes] | None = None

        try:
            if self.configure_power:
                self.configure_power_settings()
            if self.caffeinate:
                caffeinate_process = self.start_caffeinate()

            # Hardware facts do not change under us; fetch them once (or on `r`).
            computer_data = self.collect_computer_data()

            if self.clear_screen:
                self.console.clear()

            beats = 0
            ct = time.time()
            screen = _Screen(
                computer_data=computer_data,
                leading=self.leading_panel(computer_data),
                power=self.power_panel(),
                network=self.network_panel(),
                last_power_update=ct,
                last_network_update=ct,
            )
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024**2
            last_theme_check = ct

            primary = pytz.timezone(self.tz)
            secondary = pytz.timezone(self.secondary_tz)
            boot_time = psutil.boot_time()

            with Live(console=self.console, refresh_per_second=self.refresh_per_second) as live:
                prev_size = (self.console.size.width, self.console.size.height)

                while not self._stop.is_set():
                    try:
                        if beats % self.refresh_per_second == 0:
                            ct = time.time()
                            memory_mb = process.memory_info().rss / 1024**2

                            size = (self.console.size.width, self.console.size.height)
                            if size != prev_size:
                                if self.clear_screen:
                                    self.console.clear()
                                prev_size = size

                            if ct - last_theme_check >= self.theme_interval:
                                last_theme_check = ct
                                if refresh_theme():
                                    # Every palette reference is baked into the
                                    # panels, so they all have to be rebuilt.
                                    if self.clear_screen:
                                        self.console.clear()
                                    screen.leading = self.leading_panel(screen.computer_data)
                                    screen.power = self.power_panel()
                                    screen.network = self.network_panel()

                        now = datetime.now(primary)
                        screen.time = build_time_panel(
                            now=now,
                            secondary=now.astimezone(secondary),
                            up_for=ct - boot_time,
                            memory_mb=memory_mb,
                            tz=self.tz,
                        )

                        if ct - screen.last_power_update >= self.power_interval:
                            screen.last_power_update = ct
                            screen.power = self.power_panel()

                        if ct - screen.last_network_update >= self.network_interval:
                            screen.last_network_update = ct
                            screen.network = self.network_panel()

                        live.update(self.frame(screen), refresh=True)
                        self._idle(SLEEP_INTERVAL, screen, live)
                        beats += 1
                    except KeyboardInterrupt:
                        self._stop.set()
                    except Exception as exc:
                        self.ctx.warn(f"[bold red]⚠️  Error in main loop: {exc}[/bold red]")
                        self.ctx.error_console.print_exception()
                        self._stop.set()
            return 0
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            self.ctx.warn(f"[bold red]⚠️  Unexpected error in main: {exc}[/bold red]")
            self.ctx.error_console.print_exception()
            return 1
        finally:
            restore_signals()
            self._stop_caffeinate(caffeinate_process)
            keys.restore()
            if self.clear_screen:
                self.ctx.error_console.clear()

    def _install_signal_handlers(self) -> Callable[[], None]:
        """Make SIGINT/SIGTERM end the loop cleanly. Returns an undo callable.

        Without this, a ``kill`` would skip the ``finally`` block that stops
        caffeinate and takes the terminal out of cbreak mode.
        """
        if threading.current_thread() is not threading.main_thread():
            return lambda: None

        previous: list[tuple[int, Any]] = []
        for signum in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(OSError, ValueError):
                previous.append((signum, signal.signal(signum, self._on_signal)))

        def restore() -> None:
            for signum, handler in previous:
                with contextlib.suppress(OSError, ValueError):
                    signal.signal(signum, handler)

        return restore

    def _on_signal(self, signum: int, frame: Any) -> None:
        """Signal handler: ask the loop to finish, do not tear anything down here."""
        self._stop.set()


def run_dashboard(
    ctx: Context,
    *,
    tz: str | None = None,
    refresh: int | None = None,
    clear_screen: bool | None = None,
    configure_power: bool | None = None,
    caffeinate: bool | None = None,
    use_splash: bool = False,
) -> int:
    """Build a :class:`Dashboard` from *ctx* plus overrides, and run it.

    ``$TZ`` beats the config file, and an explicit *tz* beats both — the same
    precedence the original script used.
    """
    from coffee.console import make_dashboard_console

    cfg = ctx.config
    resolved_tz = tz or os.environ.get("TZ") or cfg.tz

    dashboard = Dashboard(
        ctx=ctx,
        console=make_dashboard_console(),
        tz=resolved_tz,
        secondary_tz=cfg.secondary_tz,
        refresh_per_second=refresh if refresh is not None else cfg.refresh,
        clear_screen=cfg.clear_screen if clear_screen is None else clear_screen,
        power_interval=cfg.power_interval,
        network_interval=cfg.network_interval,
        theme_interval=cfg.theme_interval,
        configure_power=cfg.configure_on_start if configure_power is None else configure_power,
        caffeinate=cfg.caffeinate if caffeinate is None else caffeinate,
        use_splash=use_splash,
    )
    return dashboard.run()
