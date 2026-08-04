import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends import cdb as cdb_module
from backends.cdb import CdbBackend
from discovery import find_debugger

CDB = find_debugger("cdb")


class _TimeoutTransport:
    """Fake transport whose startup sync never completes, to exercise start()'s
    cleanup path without spawning a real cdb process."""

    def __init__(self):
        self.closed = False

    def write(self, s):
        pass

    def read_until(self, predicate, timeout):
        raise TimeoutError("startup token never seen")

    def close(self):
        self.closed = True


class _TimeoutTransportCloseRaises(_TimeoutTransport):
    """Like _TimeoutTransport, but close() itself fails (e.g. the child process
    already exited between poll() and kill()) - the original TimeoutError must
    still win, not the close() failure."""

    def close(self):
        self.closed = True
        raise OSError("process already exited")


def test_start_closes_transport_and_reraises_on_sync_timeout(monkeypatch):
    fake = _TimeoutTransport()
    monkeypatch.setattr(cdb_module, "open_transport", lambda argv, kind: fake)
    backend = CdbBackend("cdb", "pipe", "unused-program.exe", [])

    with pytest.raises(TimeoutError):
        backend.start()

    assert fake.closed
    assert backend._transport is None


def test_start_reraises_original_error_when_close_also_fails(monkeypatch):
    fake = _TimeoutTransportCloseRaises()
    monkeypatch.setattr(cdb_module, "open_transport", lambda argv, kind: fake)
    backend = CdbBackend("cdb", "pipe", "unused-program.exe", [])

    with pytest.raises(TimeoutError):
        backend.start()

    assert fake.closed
    assert backend._transport is None
CLANG_CL = shutil.which("clang-cl") or (
    "C:/Program Files/LLVM/bin/clang-cl.exe"
    if Path("C:/Program Files/LLVM/bin/clang-cl.exe").exists()
    else None
)

_SKIP = pytest.mark.skipif(
    not CDB or os.name != "nt" or not CLANG_CL,
    reason="needs cdb (Windows) + clang-cl",
)

_SOURCE = """\
int add(int a, int b) {
    int sum = a + b;
    return sum;
}
int main() { return add(2, 5) - 7; }
"""


@_SKIP
def test_cdb_breakpoint_hits_add():
    d = Path(tempfile.mkdtemp())
    src = d / "hello.cpp"
    src.write_text(_SOURCE)
    exe = d / "hello.exe"
    subprocess.run(
        [CLANG_CL, "/Zi", "/Od", f"/Fe:{exe}", str(src)],
        check=True,
        capture_output=True,
    )
    b = CdbBackend("cdb", "pipe", str(exe), [], CDB)
    b.start()
    try:
        b.set_breakpoint("hello.cpp", 2)
        out = b.run()
        lower = out.lower()
        assert "add" in lower or "breakpoint" in lower or "hello.cpp" in lower, (
            f"Expected breakpoint hit in add(), got:\n{out}"
        )
    finally:
        b.stop()


@_SKIP
def test_cdb_read_local_after_breakpoint():
    d = Path(tempfile.mkdtemp())
    src = d / "hello.cpp"
    src.write_text(_SOURCE)
    exe = d / "hello.exe"
    subprocess.run(
        [CLANG_CL, "/Zi", "/Od", f"/Fe:{exe}", str(src)],
        check=True,
        capture_output=True,
    )
    b = CdbBackend("cdb", "pipe", str(exe), [], CDB)
    b.start()
    try:
        b.set_breakpoint("hello.cpp", 2)
        b.run()
        val = b.read_local("a")
        assert val == "2", f"Expected a=2, got: {val!r}"
    finally:
        b.stop()
