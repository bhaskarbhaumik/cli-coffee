"""``pmset`` parsing, snapshotting and command construction."""

from __future__ import annotations

import subprocess

import pytest

from coffee import pmset
from coffee.privilege import XLOG, Backend, Escalator, PrivilegeReport

SAMPLE = """\
Battery Power:
 lidwake              1
 sleep                5
 disksleep            10
 displaysleep         2
 powernap             1
 ttyskeepawake        1
AC Power:
 lidwake              1
 sleep                0
 disksleep            10
 displaysleep         20
 womp                 1
 powernap             1
"""


class _FakeEscalator(Escalator):
    """Always reports a working xlog, so the tests do not depend on the host."""

    def report(self, *, refresh: bool = False) -> PrivilegeReport:
        return PrivilegeReport(Backend.XLOG, True, True, True, False, "fake xlog")

    @property
    def is_root(self) -> bool:
        return False


def _fake_run(stdout: str, returncode: int = 0):
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    return run


def test_read_settings_groups_by_power_source(monkeypatch):
    monkeypatch.setattr(pmset.subprocess, "run", _fake_run(SAMPLE))
    settings = pmset.read_settings()
    assert set(settings) == {"Battery Power", "AC Power"}
    assert settings["Battery Power"]["sleep"] == "5"
    assert settings["AC Power"]["displaysleep"] == "20"
    assert "womp" not in settings["Battery Power"]


def test_read_settings_raises_when_pmset_fails(monkeypatch):
    monkeypatch.setattr(pmset.subprocess, "run", _fake_run("", returncode=1))
    with pytest.raises(pmset.PmsetError):
        pmset.read_settings()


def test_read_settings_raises_when_pmset_is_missing(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError("no pmset here")

    monkeypatch.setattr(pmset.subprocess, "run", boom)
    with pytest.raises(pmset.PmsetError, match="not found"):
        pmset.read_settings()


def test_awake_commands_match_the_documented_settings():
    commands = pmset.awake_commands()
    assert [(c[2], c[3]) for c in commands] == list(pmset.AWAKE_SETTINGS)
    assert all(c[:2] == [pmset.PMSET, "-a"] for c in commands)


def test_dry_run_wraps_but_never_executes(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a dry run must not execute anything")

    monkeypatch.setattr(pmset.subprocess, "run", boom)
    escalator = _FakeEscalator()
    assert escalator.backend is Backend.XLOG

    results = pmset.apply_awake_settings(escalator, dry_run=True)
    assert len(results) == len(pmset.AWAKE_SETTINGS)
    assert all(r.ok for r in results)
    assert all(r.argv[0] == str(XLOG) for r in results)


def test_snapshot_keeps_only_the_settings_coffee_touches(tmp_path, monkeypatch):
    monkeypatch.setattr(pmset.subprocess, "run", _fake_run(SAMPLE))
    path = tmp_path / "snap.json"

    saved = pmset.save_snapshot(pmset.read_settings(), path=path)
    assert saved == path

    snapshot = pmset.load_snapshot(path=path)
    assert set(snapshot) == {"Battery Power", "AC Power"}
    assert "lidwake" not in snapshot["AC Power"]
    assert snapshot["Battery Power"]["sleep"] == "5"
    assert snapshot["AC Power"]["womp"] == "1"


def test_load_snapshot_tolerates_a_missing_or_broken_file(tmp_path):
    assert pmset.load_snapshot(path=tmp_path / "absent.json") == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert pmset.load_snapshot(path=broken) == {}


def test_restore_targets_each_source_with_its_own_flag(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a dry run must not execute anything")

    monkeypatch.setattr(pmset.subprocess, "run", boom)
    snapshot = {"AC Power": {"sleep": "3"}, "Battery Power": {"sleep": "5", "womp": "1"}}
    results = pmset.restore_previous(_FakeEscalator(), snapshot, dry_run=True)
    tails = [r.argv[-3:] for r in results]
    assert ["-c", "sleep", "3"] in tails
    assert ["-b", "sleep", "5"] in tails
    assert ["-b", "womp", "1"] in tails


def test_restore_ignores_unknown_power_sources():
    snapshot = {"Martian Power": {"sleep": "1"}}
    assert pmset.restore_previous(_FakeEscalator(), snapshot, dry_run=True) == []
