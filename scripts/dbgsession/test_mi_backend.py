import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends.mi import MiBackend

NETCOREDBG = shutil.which("netcoredbg") or os.environ.get("NETCOREDBG")


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
