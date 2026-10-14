"""Hotkeys for the live dashboard.

=================  ==================================================
``r`` / ``R``      refresh every panel now, bypassing the caches
``q`` / ``Q``      quit
``Esc``            close the hotkey help if it is open, otherwise quit
anything else      open the hotkey help
=================  ==================================================

The reader runs on its own thread with the terminal in cbreak mode and hands
each key to a callback as an :class:`Action`. ``Esc`` needs care: the arrow
and function keys arrive as escape *sequences* that begin with the same byte,
so a lone ``ESC`` only counts as the Escape key when nothing follows it within
:data:`ESCAPE_SEQUENCE_WINDOW` — the same rule curses applies with ``ESCDELAY``.
Alt+key arrives the same way (``ESC`` then the key, in one write), so it opens
the help rather than being mistaken for Escape followed by a hotkey.
"""

from __future__ import annotations

import codecs
import enum
import os
import select
import sys
import termios
import threading
import tty
from collections.abc import Callable
from typing import Any

__all__ = ["ESCAPE_SEQUENCE_WINDOW", "HOTKEYS", "Action", "KeyboardWatcher", "classify_key"]

ESC = b"\x1b"

#: How long to wait after an ``ESC`` byte for the rest of an escape sequence.
#: Terminals send a sequence in one write, so its tail is already buffered.
ESCAPE_SEQUENCE_WINDOW = 0.05

#: How often the reader looks up from ``select`` to see whether it was stopped.
_POLL_INTERVAL = 0.1
_JOIN_TIMEOUT = 1.0


class Action(enum.Enum):
    """What a keypress asks the dashboard to do."""

    REFRESH = "refresh"
    QUIT = "quit"
    #: Contextual: closes the help popup when it is open, quits otherwise.
    ESCAPE = "escape"
    HELP = "help"


#: ``(keys, description)`` rows for the help popup, in display order.
HOTKEYS: tuple[tuple[str, str], ...] = (
    ("r  R", "refresh all panels"),
    ("q  Q", "quit"),
    ("Esc", "close this help · quit"),
    ("any other key", "show this help"),
)

_ACTIONS = {
    "r": Action.REFRESH,
    "R": Action.REFRESH,
    "q": Action.QUIT,
    "Q": Action.QUIT,
    "\x1b": Action.ESCAPE,
}


def classify_key(key: str) -> Action:
    """The action for one decoded key. Anything unbound asks for help."""
    return _ACTIONS.get(key, Action.HELP)


class KeyboardWatcher:
    """Turns keypresses into :class:`Action` callbacks until restored.

    The terminal attributes are captured on the calling thread, *before* the
    reader starts, so :meth:`restore` can always put the tty back — including
    when the process is interrupted while the reader is waiting for input. The
    reader polls, so :meth:`restore` also stops it rather than leaving a thread
    behind to steal the next keystroke typed at the shell.
    """

    __slots__ = ("_closed", "_fd", "_on_key", "_saved", "_stream", "_thread")

    def __init__(self, on_key: Callable[[Action], Any], *, stream: Any = None) -> None:
        self._on_key = on_key
        self._stream = stream
        self._closed = threading.Event()
        self._fd: int | None = None
        self._saved: list[Any] | None = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        """Whether a reader thread is running."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Put the tty in cbreak mode and start watching. False if stdin is not a tty."""
        try:
            fd = (self._stream if self._stream is not None else sys.stdin).fileno()
            saved = termios.tcgetattr(fd)
        except (AttributeError, ValueError, OSError, termios.error):
            return False

        self._fd, self._saved = fd, saved
        try:
            tty.setcbreak(fd)
        except (OSError, termios.error):
            self._fd, self._saved = None, None
            return False

        self._closed.clear()
        self._thread = threading.Thread(
            target=self._read, args=(fd,), name="coffee-keys", daemon=True
        )
        self._thread.start()
        return True

    def _wait_readable(self, fd: int, timeout: float) -> bool:
        ready, _, _ = select.select([fd], [], [], timeout)
        return bool(ready)

    def _read(self, fd: int) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while not self._closed.is_set():
                if not self._wait_readable(fd, _POLL_INTERVAL):
                    continue
                byte = os.read(fd, 1)
                if not byte:  # end of input: nothing more can ever be pressed
                    self._on_key(Action.QUIT)
                    return
                if byte == ESC:
                    if self._wait_readable(fd, ESCAPE_SEQUENCE_WINDOW):
                        os.read(fd, 64)  # the rest of an arrow or function key
                        decoder.reset()
                        self._on_key(Action.HELP)
                    else:
                        self._on_key(Action.ESCAPE)
                    continue
                key = decoder.decode(byte)
                if key:  # empty while a multi-byte character is incomplete
                    self._on_key(classify_key(key))
        except (OSError, ValueError):
            if not self._closed.is_set():
                self._on_key(Action.QUIT)

    def restore(self) -> None:
        """Stop reading and put the terminal back. Safe to call more than once."""
        self._closed.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(_JOIN_TIMEOUT)
        if self._fd is None or self._saved is None:
            return
        try:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        except (OSError, termios.error):
            pass
        finally:
            self._fd, self._saved = None, None
