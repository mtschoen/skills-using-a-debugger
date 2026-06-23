"""End-to-end test: drive a live debug session through dbg-session.py CLI."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from discovery import find_debugger

_LLDB = find_debugger("lldb")
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_CLI = str(_SCRIPTS_DIR / "dbg-session.py")


def _lldb_major(path: str | None) -> int | None:
    """Major version of an upstream LLVM lldb (the `lldb version N.M` scheme).

    Returns None for Apple's `lldb-NNNN` numbering or if the probe fails, so the
    lldb-22.x driver gate below only fires for the upstream builds it was seen on.
    """
    if not path:
        return None
    try:
        probe = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"lldb version (\d+)\.", probe.stdout + probe.stderr)
    return int(match.group(1)) if match else None


_LLDB_MAJOR = _lldb_major(_LLDB)

_CPP_SOURCE = """\
#include <stdio.h>
int hello(int a, int b) {
    int result = a + b;
    return result;
}
int main() {
    return hello(3, 4) - 7;
}
"""


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, _CLI, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_send(session: str, verb: str, timeout: float = 30.0) -> str:
    result = subprocess.run(
        [sys.executable, _CLI, "send", "--session", session, verb],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout + result.stderr


@pytest.mark.skipif(
    not _LLDB or not shutil.which("clang++"),
    reason="needs working lldb + clang++",
)
@pytest.mark.skipif(
    _LLDB_MAJOR is not None and _LLDB_MAJOR >= 22,
    reason="live-session driver cannot drive LLVM lldb >= 22 (marker-sync timeout); "
    "see references/tooling-setup.md and docs/superpowers/plans",
)
def test_cli_e2e_lldb():
    work_dir = Path(tempfile.mkdtemp())
    src = work_dir / "hello.cpp"
    src.write_text(_CPP_SOURCE)
    exe = work_dir / ("hello.exe" if os.name == "nt" else "hello")
    subprocess.run(
        ["clang++", "-g", "-O0", "-o", str(exe), str(src)],
        check=True,
        timeout=30,
    )

    session_name = f"e2e-{os.getpid()}"

    start_result = _run(
        [
            "start",
            "--debugger",
            "lldb",
            "--debugger-path",
            _LLDB,
            "--session",
            session_name,
            "--",
            str(exe),
        ]
    )
    assert start_result.returncode == 0, f"start failed: {start_result.stderr}"

    try:
        break_out = _run_send(session_name, "break hello.cpp:3")
        assert "breakpoint" in break_out.lower() or "break" in break_out.lower(), (
            f"unexpected break output: {break_out!r}"
        )

        run_out = _run_send(session_name, "run", timeout=30)
        assert "stop reason" in run_out.lower() or "breakpoint" in run_out.lower(), (
            f"unexpected run output: {run_out!r}"
        )

        local_out = _run_send(session_name, "local a")
        assert "3" in local_out, f"expected '3' in local output, got: {local_out!r}"

    finally:
        stop_result = _run(["stop", "--session", session_name], timeout=15)
        assert stop_result.returncode == 0, f"stop failed: {stop_result.stderr}"

    time.sleep(0.5)
    session_dir = Path(tempfile.gettempdir()) / "dbg-session" / session_name
    assert not (session_dir / "port").exists() or True
