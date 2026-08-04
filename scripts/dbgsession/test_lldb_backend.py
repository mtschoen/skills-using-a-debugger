import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends import lldb_cli as lldb_cli_module
from backends.lldb_cli import LldbCliBackend
from discovery import find_debugger

LLDB = find_debugger("lldb")


class _TimeoutTransport:
    """Fake transport whose startup sync never completes, to exercise start()'s
    cleanup path without spawning a real lldb process."""

    def __init__(self):
        self.closed = False

    def write(self, s):
        pass

    def read_until(self, predicate, timeout):
        raise TimeoutError("startup token never seen")

    def close(self):
        self.closed = True


def test_start_closes_transport_and_reraises_on_sync_timeout(monkeypatch):
    fake = _TimeoutTransport()
    monkeypatch.setattr(lldb_cli_module, "open_transport", lambda argv, kind: fake)
    backend = LldbCliBackend("lldb", "pipe", "unused-program", [])

    with pytest.raises(TimeoutError):
        backend.start()

    assert fake.closed
    assert backend._transport is None


@pytest.mark.skipif(not LLDB or not shutil.which("clang++"), reason="needs working lldb + clang++")
def test_lldb_live_session_reads_locals():
    d = Path(tempfile.mkdtemp())
    (d / "hello.cpp").write_text(
        "int add(int a,int b){\n    int s=a+b;\n    return s;\n}\nint main(){return add(2,5)-7;}\n"
    )
    exe = d / ("hello.exe" if os.name == "nt" else "hello")
    subprocess.run(
        ["clang++", "-g", "-O0", "-o", str(exe), str(d / "hello.cpp")],
        check=True,
    )
    b = LldbCliBackend("lldb", "pipe", str(exe), [], LLDB)
    b.start()
    try:
        b.set_breakpoint("hello.cpp", 2)
        out = b.run()
        assert "stop reason" in out.lower()
        assert b.read_local("a") == "2"
        assert b.read_local("b") == "5"
    finally:
        b.stop()
