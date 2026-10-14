"""Hotkey decoding, driven through a real pseudo-terminal."""

from __future__ import annotations

import io
import os
import queue
import termios
import time

import pytest

from coffee.keys import ESCAPE_SEQUENCE_WINDOW, Action, KeyboardWatcher, classify_key


@pytest.mark.parametrize(
    ("key", "action"),
    [
        ("r", Action.REFRESH),
        ("R", Action.REFRESH),
        ("q", Action.QUIT),
        ("Q", Action.QUIT),
        ("\x1b", Action.ESCAPE),
        ("x", Action.HELP),
        (" ", Action.HELP),
        ("\n", Action.HELP),
        ("é", Action.HELP),
    ],
)
def test_classify_key(key, action):
    assert classify_key(key) is action


@pytest.fixture
def terminal():
    """A started watcher on the slave side of a pty, its master fd, and its actions."""
    master, slave = os.openpty()
    stream = os.fdopen(slave, "rb", buffering=0)
    actions: queue.SimpleQueue[Action] = queue.SimpleQueue()
    watcher = KeyboardWatcher(actions.put, stream=stream)
    assert watcher.start()
    yield watcher, master, actions
    watcher.restore()
    stream.close()
    os.close(master)


def _next(actions: queue.SimpleQueue[Action]) -> Action:
    return actions.get(timeout=2)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (b"r", Action.REFRESH),
        (b"R", Action.REFRESH),
        (b"q", Action.QUIT),
        (b"Q", Action.QUIT),
        (b"\x1b", Action.ESCAPE),
        (b"k", Action.HELP),
        (b"\x1b[A", Action.HELP),  # up arrow: an escape *sequence*, not Escape
        (b"\x1bOP", Action.HELP),  # F1
        ("é".encode(), Action.HELP),  # one action for a two-byte character
    ],
)
def test_watcher_reports_one_action_per_key(terminal, typed, expected):
    _, master, actions = terminal
    os.write(master, typed)
    assert _next(actions) is expected
    with pytest.raises(queue.Empty):
        actions.get(timeout=0.3)


def test_watcher_keeps_reading_after_the_first_key(terminal):
    _, master, actions = terminal
    for typed in (b"z", b"\x1b", b"r", b"q"):
        os.write(master, typed)
        time.sleep(ESCAPE_SEQUENCE_WINDOW * 4)  # human typing speed
    assert [_next(actions) for _ in range(4)] == [
        Action.HELP,
        Action.ESCAPE,
        Action.REFRESH,
        Action.QUIT,
    ]


def test_escape_with_a_key_hard_behind_it_is_one_keystroke(terminal):
    """Alt+R arrives as ESC R in a single write; it must not quit or refresh."""
    _, master, actions = terminal
    os.write(master, b"\x1br")
    assert _next(actions) is Action.HELP
    with pytest.raises(queue.Empty):
        actions.get(timeout=0.3)


def test_restore_stops_the_reader_and_the_terminal_comes_back(terminal):
    watcher, master, actions = terminal
    assert watcher.active
    watcher.restore()
    assert not watcher.active
    # After restore the keystroke belongs to whoever owns the tty next.
    os.write(master, b"q")
    with pytest.raises(queue.Empty):
        actions.get(timeout=0.3)
    watcher.restore()  # idempotent


def test_restore_puts_the_terminal_attributes_back():
    master, slave = os.openpty()
    try:
        with os.fdopen(slave, "rb", buffering=0) as stream:
            before = termios.tcgetattr(slave)
            watcher = KeyboardWatcher(lambda action: None, stream=stream)
            assert watcher.start()
            assert termios.tcgetattr(slave) != before  # cbreak
            watcher.restore()
            after = termios.tcgetattr(slave)
            # The kernel may raise PENDIN on the switch back to canonical mode.
            after[3] &= ~getattr(termios, "PENDIN", 0)
            assert after == before
    finally:
        os.close(master)


def test_a_non_tty_cannot_be_watched():
    watcher = KeyboardWatcher(lambda action: None, stream=io.StringIO())
    assert watcher.start() is False
    assert not watcher.active
    watcher.restore()
