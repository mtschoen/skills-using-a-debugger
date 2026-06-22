import os
import shutil
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
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


@pytest.mark.skipif(os.name != "nt", reason="CLion lldb fallback is Windows-only")
def test_lldb_clion_fallback_works():
    result = find_debugger("lldb")
    assert result is not None, "expected find_debugger('lldb') to find CLion lldb"
    assert os.path.isfile(result), f"path does not exist: {result}"
    completed = subprocess.run(
        [result, "--version"],
        capture_output=True,
        timeout=15,
    )
    assert completed.returncode == 0, f"lldb --version returned {completed.returncode}"
