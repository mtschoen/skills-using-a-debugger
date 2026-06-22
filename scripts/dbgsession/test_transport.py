import os, sys, pytest
from transport import open_transport

ECHO = [sys.executable, "-u", "-c",
        "import sys\nfor line in sys.stdin:\n sys.stdout.write('GOT:'+line); sys.stdout.flush()"]

def test_pipe_read_until_marker():
    t = open_transport(ECHO, "pipe")
    try:
        t.write("hello\n")
        out = t.read_until(lambda acc: "GOT:hello" in acc, timeout=10)
        assert "GOT:hello" in out
    finally:
        t.close()

def test_pipe_read_until_times_out():
    t = open_transport(ECHO, "pipe")
    try:
        with pytest.raises(TimeoutError):
            t.read_until(lambda acc: "NEVER" in acc, timeout=1)
    finally:
        t.close()

@pytest.mark.skipif(os.name == "nt", reason="pty is POSIX-only")
def test_pty_available_on_posix():
    t = open_transport(ECHO, "pty")
    try:
        t.write("hi\n")
        assert "GOT:hi" in t.read_until(lambda acc: "GOT:hi" in acc, timeout=10)
    finally:
        t.close()

def test_pty_rejected_on_windows():
    if os.name == "nt":
        with pytest.raises(RuntimeError):
            open_transport(ECHO, "pty")
