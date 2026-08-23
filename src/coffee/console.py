"""Console factories.

The dashboard's console is deliberately forced to truecolor + interactive: the
panels use 24-bit hex colours and Nerd Font glyphs, and Rich would otherwise
downgrade both the moment output is not a tty.  Everything else (``doctor``,
``config``, error reporting) uses a console that respects the environment.
"""

from __future__ import annotations

from rich.console import Console

__all__ = ["make_console", "make_dashboard_console", "make_error_console"]


def make_dashboard_console(*, width: int | None = None) -> Console:
    """The console the live dashboard renders into."""
    return Console(
        color_system="truecolor",
        force_interactive=True,
        force_terminal=True,
        width=width,
    )


def make_error_console(*, width: int | None = None) -> Console:
    """The stderr console used for warnings and tracebacks."""
    return Console(
        stderr=True,
        color_system="truecolor",
        force_interactive=False,
        force_terminal=True,
        width=width,
    )


def make_console(
    *,
    stderr: bool = False,
    no_color: bool = False,
    width: int | None = None,
    quiet: bool = False,
) -> Console:
    """A general-purpose console for sub-commands."""
    return Console(
        stderr=stderr,
        no_color=no_color,
        width=width,
        quiet=quiet,
        soft_wrap=False,
        highlight=False,
    )
