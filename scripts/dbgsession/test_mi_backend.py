import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends import mi as mi_module
from backends.mi import MiBackend

NETCOREDBG = shutil.which("netcoredbg") or os.environ.get("NETCOREDBG")


class _TimeoutTransport:
    """Fake transport whose startup sync never completes, to exercise start()'s
    cleanup path without spawning a real netcoredbg/gdb process."""

    def __init__(self):
        self.closed = False

    def write(self, s):
        pass

    def read_until(self, predicate, timeout):
        raise TimeoutError("prompt never seen")

    def close(self):
        self.closed = True


def test_start_closes_transport_and_reraises_on_sync_timeout(monkeypatch):
    fake = _TimeoutTransport()
    monkeypatch.setattr(mi_module, "open_transport", lambda argv, kind: fake)
    backend = MiBackend("netcoredbg", "pipe", "unused-program", [], "netcoredbg")

    with pytest.raises(TimeoutError):
        backend.start()

    assert fake.closed
    assert backend._transport is None


@pytest.mark.skipif(
    not NETCOREDBG or not shutil.which("dotnet"),
    reason="needs netcoredbg + dotnet",
)
def test_netcoredbg_live_session_reads_locals():
    d = Path(tempfile.mkdtemp())
    subprocess.run(["dotnet", "new", "console", "-o", str(d)], check=True, capture_output=True)
    (d / "Program.cs").write_text(
        textwrap.dedent(
            """
            int Add(int a, int b){ int sum=a+b; return sum; }
            for (int i=0;i<3;i++){ int r=Add(i,i*2); System.Console.WriteLine(r); }
            """
        )
    )
    subprocess.run(["dotnet", "build", "-c", "Debug"], cwd=d, check=True, capture_output=True)
    dll = next(d.glob("bin/Debug/net*/*.dll"))
    backend = MiBackend("netcoredbg", "pipe", "dotnet", [str(dll)], NETCOREDBG)
    backend.start()
    try:
        backend.set_breakpoint("Program.cs", 2)
        backend.run()
        assert backend.read_local("a") == "0"
        assert backend.read_local("b") == "0"
        backend.cont()
        assert backend.read_local("a") == "1"
    finally:
        backend.stop()
