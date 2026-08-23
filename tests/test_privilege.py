"""Escalation picks xlog first, sudo second, and refuses to guess."""

from __future__ import annotations

import subprocess

import pytest

from coffee import privilege
from coffee.privilege import SUDO, XLOG, Backend, Escalator


@pytest.fixture(autouse=True)
def _not_root(monkeypatch):
    monkeypatch.setattr(privilege.os, "geteuid", lambda: 1000)


def _stub(monkeypatch, *, xlog: bool, sudo: bool, sudo_cached: bool = False):
    """Pretend xlog and/or sudo exist and behave."""
    monkeypatch.setattr(
        privilege.Path, "exists", lambda self: (self == XLOG and xlog) or (self == SUDO and sudo)
    )

    def run(argv, **kwargs):
        if argv[0] == str(XLOG):
            return subprocess.CompletedProcess(argv, 0 if xlog else 1, "0\n" if xlog else "", "")
        if argv[:2] == [str(SUDO), "-n"]:
            return subprocess.CompletedProcess(argv, 0 if sudo_cached else 1, "", "")
        raise AssertionError(f"unexpected probe: {argv}")

    monkeypatch.setattr(privilege.subprocess, "run", run)
    monkeypatch.setattr(privilege.shutil, "which", lambda _: "/usr/bin/sudo" if sudo else None)


def test_xlog_is_preferred(monkeypatch):
    _stub(monkeypatch, xlog=True, sudo=True)
    esc = Escalator()
    assert esc.backend is Backend.XLOG
    assert esc.wrap(["pmset", "-a", "sleep", "0"]) == [str(XLOG), "pmset", "-a", "sleep", "0"]
    assert esc.available


def test_sudo_is_the_fallback(monkeypatch):
    _stub(monkeypatch, xlog=False, sudo=True)
    esc = Escalator()
    assert esc.backend is Backend.SUDO
    # -n so nothing can block on a hidden password prompt.
    assert esc.wrap(["pmset"]) == [str(SUDO), "-n", "pmset"]


def test_sudo_can_be_forced_over_a_working_xlog(monkeypatch):
    _stub(monkeypatch, xlog=True, sudo=True)
    esc = Escalator(prefer=Backend.SUDO)
    assert esc.backend is Backend.SUDO


def test_xlog_only_never_falls_back_to_sudo(monkeypatch):
    _stub(monkeypatch, xlog=False, sudo=True)
    esc = Escalator(prefer=Backend.XLOG, allow_sudo=False)
    assert esc.backend is Backend.NONE
    with pytest.raises(PermissionError):
        esc.wrap(["pmset"])


def test_no_backend_at_all(monkeypatch):
    _stub(monkeypatch, xlog=False, sudo=False)
    esc = Escalator()
    assert esc.backend is Backend.NONE
    assert not esc.available
    assert "unavailable" in esc.describe(["pmset"])


def test_root_needs_no_wrapper(monkeypatch):
    _stub(monkeypatch, xlog=True, sudo=True)
    monkeypatch.setattr(privilege.os, "geteuid", lambda: 0)
    esc = Escalator()
    assert esc.wrap(["pmset"]) == ["pmset"]
    assert esc.available


def test_priming_is_free_when_xlog_works(monkeypatch):
    _stub(monkeypatch, xlog=True, sudo=True)
    assert Escalator().prime(interactive=False) is True


def test_priming_without_a_tty_will_not_prompt(monkeypatch):
    _stub(monkeypatch, xlog=False, sudo=True, sudo_cached=False)
    assert Escalator().prime(interactive=False) is False


def test_priming_is_a_no_op_when_credentials_are_cached(monkeypatch):
    _stub(monkeypatch, xlog=False, sudo=True, sudo_cached=True)
    assert Escalator().prime(interactive=False) is True


def test_report_is_cached_until_refreshed(monkeypatch):
    _stub(monkeypatch, xlog=True, sudo=True)
    esc = Escalator()
    assert esc.report() is esc.report()
    assert esc.report(refresh=True) is not None
