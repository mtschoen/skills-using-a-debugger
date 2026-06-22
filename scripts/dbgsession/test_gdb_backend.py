import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends.mi import MiBackend

GDB = shutil.which("gdb")
GPP = shutil.which("g++")


@pytest.mark.skipif(
    not GDB or not GPP or os.name == "nt",
    reason="needs gdb + g++ on POSIX",
)
def test_gdb_live_session_reads_locals():
    d = Path(tempfile.mkdtemp())
    src = d / "add.cpp"
    src.write_text(
        "int add(int a, int b) { int sum = a + b; return sum; }\n"
        "int main() { return add(2, 5) - 7; }\n"
    )
    exe = d / "add"
    subprocess.run(
        ["g++", "-g", "-O0", "-o", str(exe), str(src)],
        check=True,
        capture_output=True,
    )
    backend = MiBackend("gdb", "pty", str(exe), [], GDB)
    backend.start()
    try:
        backend.set_breakpoint("add.cpp", 1)
        backend.run()
        assert backend.read_local("a") == "2"
        assert backend.read_local("b") == "5"
    finally:
        backend.stop()
