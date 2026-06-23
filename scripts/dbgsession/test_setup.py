import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import setup
from setup import (
    Result,
    netcoredbg_asset_substring,
    platform_targets,
    select_asset,
)


def test_platform_targets_per_system():
    assert platform_targets("Linux") == ("netcoredbg", "gdb", "lldb")
    assert platform_targets("Darwin") == ("netcoredbg", "lldb")
    assert platform_targets("Windows") == ("netcoredbg", "cdb", "lldb")
    assert platform_targets("plan9") == ()


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Windows", "AMD64", "win64"),
        ("Windows", "ARM64", "win64"),
        ("Linux", "x86_64", "linux-amd64"),
        ("Linux", "aarch64", "linux-arm64"),
        ("Darwin", "x86_64", "osx-amd64"),
        ("Darwin", "arm64", "osx-amd64"),
        ("Plan9", "x86_64", None),
    ],
)
def test_netcoredbg_asset_substring(system, machine, expected):
    assert netcoredbg_asset_substring(system, machine) == expected


def test_select_asset_matches_and_misses():
    names = [
        "netcoredbg-linux-amd64.tar.gz",
        "netcoredbg-linux-arm64.tar.gz",
        "netcoredbg-win64.zip",
    ]
    assert select_asset(names, "linux-arm64") == "netcoredbg-linux-arm64.tar.gz"
    assert select_asset(names, "win64") == "netcoredbg-win64.zip"
    assert select_asset(names, "osx-amd64") is None


def test_run_skips_present_debuggers(monkeypatch):
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup, "find_debugger", lambda kind: f"/usr/bin/{kind}")
    installs: list[str] = []
    monkeypatch.setattr(
        setup,
        "install_for",
        lambda kind, system, dry_run: (
            installs.append(kind) or Result(kind, "installed", "")
        ),
    )

    results = setup.run(report=lambda _line: None)

    assert installs == []  # nothing missing, so nothing installed
    assert {result.kind for result in results} == {"netcoredbg", "gdb", "lldb"}
    assert all(result.status == "present" for result in results)


def test_run_installs_only_missing(monkeypatch):
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        setup, "find_debugger", lambda kind: "/usr/bin/gdb" if kind == "gdb" else None
    )
    installed: list[str] = []
    monkeypatch.setattr(
        setup,
        "install_for",
        lambda kind, system, dry_run: (
            installed.append(kind) or Result(kind, "installed", "")
        ),
    )

    results = setup.run(report=lambda _line: None)

    assert installed == ["netcoredbg", "lldb"]  # gdb present, skipped
    by_kind = {result.kind: result.status for result in results}
    assert by_kind == {"netcoredbg": "installed", "gdb": "present", "lldb": "installed"}


def test_run_only_filters_targets(monkeypatch):
    monkeypatch.setattr(setup.platform, "system", lambda: "Windows")
    monkeypatch.setattr(setup, "find_debugger", lambda kind: None)
    seen: list[str] = []
    monkeypatch.setattr(
        setup,
        "install_for",
        lambda kind, system, dry_run: (
            seen.append(kind) or Result(kind, "installed", "")
        ),
    )

    setup.run(only=["lldb"], report=lambda _line: None)

    assert seen == ["lldb"]


def test_run_dry_run_does_not_install(monkeypatch):
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup, "find_debugger", lambda kind: None)
    flags: list[bool] = []
    monkeypatch.setattr(
        setup,
        "install_for",
        lambda kind, system, dry_run: (
            flags.append(dry_run) or Result(kind, "dryrun", "")
        ),
    )

    results = setup.run(dry_run=True, report=lambda _line: None)

    assert all(flags)  # dry_run propagated to every dispatch
    assert all(result.status == "dryrun" for result in results)


def test_install_netcoredbg_dry_run_is_inert(monkeypatch):
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup.platform, "machine", lambda: "x86_64")

    def fail_http(*_args, **_kwargs):
        raise AssertionError("dry run must not touch the network")

    monkeypatch.setattr(setup, "_http_get", fail_http)

    result = setup.install_netcoredbg(dry_run=True)

    assert result.kind == "netcoredbg"
    assert result.status == "dryrun"
