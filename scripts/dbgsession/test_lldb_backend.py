import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backends.lldb_cli import LldbCliBackend
from discovery import find_debugger

LLDB = find_debugger("lldb")


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
