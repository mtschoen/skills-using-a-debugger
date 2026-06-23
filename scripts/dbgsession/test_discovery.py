import os
import shutil
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import discovery
from discovery import find_debugger


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        find_debugger("nonsense")


def test_gdb_matches_which():
    result = find_debugger("gdb")
    which_gdb = shutil.which("gdb")
    env_gdb = os.environ.get("GDB")
    if which_gdb is not None:
        assert result == which_gdb
    elif env_gdb is not None:
        assert result == env_gdb
    else:
        assert result is None


def test_lldb_health_check_rejects_bad_candidate(tmp_path, monkeypatch):
    if os.name == "nt":
        bad_lldb = tmp_path / "lldb.bat"
        bad_lldb.write_text("@echo off\nexit /b 1\r\n")
    else:
        bad_lldb = tmp_path / "lldb"
        bad_lldb.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n")
        bad_lldb.chmod(bad_lldb.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    monkeypatch.setenv("LLDB", str(bad_lldb))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    original_which = shutil.which

    def patched_which(name, *args, **kwargs):
        if name == "lldb":
            return None
        return original_which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", patched_which)

    result = find_debugger("lldb")
    assert result is None or result != str(bad_lldb)


def test_lldb_finds_llvm_program_files(tmp_path, monkeypatch):
    # winget installs LLVM under Program Files\LLVM\bin without touching PATH;
    # detection must still find it. Drive the lookup purely off env + on-disk
    # layout (health check stubbed) so the test is hermetic and cross-platform.
    llvm_bin = tmp_path / "LLVM" / "bin"
    llvm_bin.mkdir(parents=True)
    lldb_exe = llvm_bin / "lldb.exe"
    lldb_exe.write_text("")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LLDB", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)  # no CLion fallback
    monkeypatch.setattr(discovery.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(discovery, "_health_check", lambda path: path == str(lldb_exe))

    assert discovery._find_lldb() == str(lldb_exe)


@pytest.mark.skipif(os.name != "nt", reason="lldb discovery integration is Windows-only")
def test_lldb_discoverable_on_windows():
    result = find_debugger("lldb")
    assert result is not None, "expected find_debugger('lldb') to find a working lldb"
    assert os.path.isfile(result), f"path does not exist: {result}"
    completed = subprocess.run(
        [result, "--version"],
        capture_output=True,
        timeout=15,
    )
    assert completed.returncode == 0, f"lldb --version returned {completed.returncode}"
