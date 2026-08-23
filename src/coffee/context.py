"""The runtime context every command is handed."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field

from rich.console import Console

from coffee.config import Config
from coffee.privilege import Escalator

__all__ = ["Context"]


@dataclass(slots=True)
class Context:
    """Everything a command needs that is not one of its own arguments."""

    console: Console
    error_console: Console
    escalator: Escalator
    config: Config

    dry_run: bool = False
    assume_yes: bool = False
    quiet: bool = False
    verbose: int = 0

    _macos_version: str | None = field(default=None, init=False, repr=False)

    # ── platform ─────────────────────────────────────────────────────────────
    @property
    def is_macos(self) -> bool:
        return sys.platform == "darwin"

    @property
    def arch(self) -> str:
        return platform.machine()

    @property
    def is_apple_silicon(self) -> bool:
        return self.is_macos and self.arch == "arm64"

    @property
    def macos_version(self) -> str:
        if self._macos_version is None:
            self._macos_version = platform.mac_ver()[0] or "unknown"
        return self._macos_version

    # ── privileges ───────────────────────────────────────────────────────────
    @property
    def root_usable(self) -> bool:
        """Whether root-requiring steps can run at all."""
        return self.escalator.available

    # ── output ───────────────────────────────────────────────────────────────
    def say(self, renderable: object) -> None:
        """Print unless ``--quiet``."""
        if not self.quiet:
            self.console.print(renderable)

    def warn(self, message: str) -> None:
        """Print a warning to stderr, regardless of ``--quiet``."""
        self.error_console.print(message, soft_wrap=True)
