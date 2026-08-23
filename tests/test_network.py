"""Network parsing, ordering and the two detail levels."""

from __future__ import annotations

import json
import subprocess

import pytest

from coffee import network

SAMPLE = {
    "SPNetworkDataType": [
        {
            "_name": "Thunderbolt Bridge",
            "interface": "bridge0",
            "spnetwork_service_order": 10,
            "Ethernet": {"MAC Address": "aa:bb:cc:dd:ee:01"},
        },
        {
            "_name": "Wi-Fi",
            "interface": "en0",
            "spnetwork_service_order": 2,
            "Wi-Fi": {"MAC Address": "aa:bb:cc:dd:ee:02"},
        },
        {
            "_name": "Ethernet Adapter",
            "interface": "en5",
            "spnetwork_service_order": 1,
            "IPv4": {"Addresses": ["192.168.1.20"]},
            "IPv6": {"Addresses": ["fe80::1"]},
            "Ethernet": {"MAC Address": "aa:bb:cc:dd:ee:03"},
        },
        {
            "_name": "Half configured",
            "interface": "en9",
            "spnetwork_service_order": "N/A",
        },
    ]
}


@pytest.fixture(autouse=True)
def _fake_profiler(monkeypatch):
    def run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, json.dumps(SAMPLE), "")

    monkeypatch.setattr(network.subprocess, "run", run)


def test_numeric_service_order_sorts_numerically():
    """A string sort would put service 10 ahead of service 2."""
    names = [i.name for i in network.get_interfaces()]
    assert names[:3] == ["en5", "en0", "bridge0"]


def test_non_numeric_order_is_parked_at_the_end():
    assert network.get_interfaces()[-1].name == "en9"


def test_active_means_has_an_ipv4():
    by_name = {i.name: i for i in network.get_interfaces()}
    assert by_name["en5"].active
    assert not by_name["en0"].active
    assert by_name["en5"].ipv6 == "fe80::1"


def test_mac_falls_back_from_ethernet_to_wifi():
    by_name = {i.name: i for i in network.get_interfaces()}
    assert by_name["en0"].mac == "aa:bb:cc:dd:ee:02"
    assert by_name["bridge0"].mac == "aa:bb:cc:dd:ee:01"


def test_missing_mac_reports_na(monkeypatch):
    payload = {"SPNetworkDataType": [{"_name": "X", "interface": "en1"}]}
    monkeypatch.setattr(
        network.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, json.dumps(payload), ""),
    )
    assert network.get_interfaces()[0].mac == "N/A"


def test_terse_always_shows_wifi_even_without_an_address(render):
    text = render(network.get_network_panel("terse"))
    assert "Wi-Fi" in text
    assert "n/a" in text
    assert "Half configured" not in text  # inactive, and not Wi-Fi


def test_terse_pads_to_a_stable_height(render):
    """The panel must not change height as interfaces come and go."""
    lines = render(network.get_network_panel("terse")).strip().splitlines()
    assert len(lines) == network.MIN_ROWS + 4  # border, header, rule, rows, border


def test_all_shows_inactive_interfaces_too(render):
    text = render(network.get_network_panel("all"))
    assert "Half configured" in text
    assert "Thunderbolt Bridge" in text


def test_broken_json_raises_network_error(monkeypatch):
    monkeypatch.setattr(
        network.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "{not json", ""),
    )
    with pytest.raises(network.NetworkError):
        network.get_interfaces()


def test_missing_system_profiler_raises_network_error(monkeypatch):
    def boom(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(network.subprocess, "run", boom)
    with pytest.raises(network.NetworkError, match="not found"):
        network.get_interfaces()
