"""The live dashboard — four panels, refreshed forever, machine held awake.

Layout and cadence are the visual contract:

* ``Columns([computer, network, power, time])``, right-aligned;
* four refreshes a second, so the seconds digit never looks like it stutters;
* the battery panel re-reads every 5 minutes and the network panel every hour,
  because both cost a ``system_profiler`` call;
* the theme is re-checked every 5 seconds, and a change rebuilds every panel.

Press any key to quit.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psutil
import pytz
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel

from coffee.clock import build_time_panel
from coffee.computer import get_computer_panel, regenerate_computer_cache
from coffee.context import Context
from coffee.network import get_network_panel
from coffee.pmset import apply_awake_settings
from coffee.power import get_power_data, get_power_visual
from coffee.splash import get_splash_panel
from coffee.theme import refresh_theme

__all__ = ["SECONDS_PER_YEAR", "Dashboard", "KeyboardWatcher", "run_dashboard"]

SECONDS_PER_YEAR = 31_536_000
SLEEP_INTERVAL = 0.4
CAFFEINATE_FLAGS = ["-dimsu", "-t", str(SECONDS_PER_YEAR)]
_CAFFEINATE_GRACE = 2.0


class KeyboardWatcher:
    """Sets an event as soon as any key is pressed.

    The terminal attributes are captured on the calling thread, *before* the
    reader starts, so :meth:`restore` can always put the tty back — including
    when the process is interrupted while the reader is still blocked in
    ``read()`` and never gets to clean up after itself.
    """

    __slots__ = ("_event", "_fd", "_saved", "_thread")

    def __init__(self, event: threading.Event) -> None:
        self._event = event
        self._fd: int | None = None
        self._saved: list[Any] | None = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        """Whether a reader thread is running."""
        return self._thread is not None

    def start(self) -> bool:
        """Put the tty in cbreak mode and start watching. False if stdin is not a tty."""
        try:
            fd = sys.stdin.fileno()
            saved = termios.tcgetattr(fd)
        except (ValueError, OSError, termios.error):
            return False

        self._fd, self._saved = fd, saved
        try:
            tty.setcbreak(fd)
        except (OSError, termios.error):
            self._fd, self._saved = None, None
            return False

        self._thread = threading.Thread(target=self._read, name="coffee-keys", daemon=True)
        self._thread.start()
        return True

    def _read(self) -> None:
        try:
            sys.stdin.read(1)
        except (OSError, ValueError):
            pass
        finally:
            self._event.set()

    def restore(self) -> None:
        """Put the terminal back the way it was. Safe to call more than once."""
        if self._fd is None or self._saved is None:
            return
        try:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        except (OSError, termios.error):
            pass
        finally:
            self._fd, self._saved = None, None


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

    _stop: threading.Event = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._stop is None:
            self._stop = threading.Event()

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

    def power_panel(self) -> Panel:
        return self._safe_panel(
            lambda: get_power_visual(get_power_data()),
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

    # ── the loop ─────────────────────────────────────────────────────────────
    def run(self) -> int:
        """Draw until a key is pressed, the process is signalled, or a panel dies."""
        keys = KeyboardWatcher(self._stop)
        keys.start()
        restore_signals = self._install_signal_handlers()
        caffeinate_process: subprocess.Popen[bytes] | None = None

        try:
            if self.configure_power:
                self.configure_power_settings()
            if self.caffeinate:
                caffeinate_process = self.start_caffeinate()

            # Hardware facts do not change under us; fetch them once.
            try:
                computer_data = regenerate_computer_cache()
            except Exception as exc:
                self.ctx.warn(f"⚠️  Error while collecting computer info: {exc}")
                computer_data = {}

            if self.clear_screen:
                self.console.clear()

            leading = self.splash_panel() if self.use_splash else self.computer_panel(computer_data)
            panel_power = self.power_panel()
            panel_network = self.network_panel()

            beats = 0
            ct = time.time()
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024**2
            last_power_update = ct
            last_network_update = ct
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
                                    leading = (
                                        self.splash_panel()
                                        if self.use_splash
                                        else self.computer_panel(computer_data)
                                    )
                                    panel_power = self.power_panel()
                                    panel_network = self.network_panel()

                        now = datetime.now(primary)
                        panel_time = build_time_panel(
                            now=now,
                            secondary=now.astimezone(secondary),
                            up_for=ct - boot_time,
                            memory_mb=memory_mb,
                            tz=self.tz,
                        )

                        if ct - last_power_update >= self.power_interval:
                            last_power_update = ct
                            panel_power = self.power_panel()

                        if ct - last_network_update >= self.network_interval:
                            last_network_update = ct
                            panel_network = self.network_panel()

                        live.update(
                            Align.right(Columns([leading, panel_network, panel_power, panel_time])),
                            refresh=True,
                        )
                        time.sleep(SLEEP_INTERVAL)
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
