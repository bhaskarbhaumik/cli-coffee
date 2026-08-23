"""coffee — keep an Apple Silicon Mac awake, with style.

A live terminal dashboard (machine, network, battery, clock) that also holds
the machine awake for as long as it runs, plus a small set of sub-commands for
inspecting and adjusting the power settings it manipulates.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("cli-coffee")
except PackageNotFoundError:  # source checkout without an install
    __version__ = "0.0.0+dev"

__author__ = "Bhaskar Bhaumik"
__description__ = "Keep an Apple Silicon Mac awake, with style."

__all__ = ["__version__", "main"]


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point, imported lazily to keep ``import coffee`` cheap."""
    from coffee.cli import main as _main

    return _main(argv)
