import contextlib
import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable

_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class Transport:
    def write(self, s: str) -> None:
        raise NotImplementedError

    def read_until(self, predicate: Callable[[str], bool], timeout: float) -> str:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class PipeTransport(Transport):
    def __init__(self, argv):
        self.p = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(line)

    def write(self, s):
        self.p.stdin.write(s)
        self.p.stdin.flush()

    def read_until(self, predicate, timeout):
        acc, deadline = "", time.monotonic() + timeout
        while True:
            if predicate(acc):
                return acc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"read_until timed out; acc so far:\n{acc}")
            with contextlib.suppress(queue.Empty):
                acc += self.q.get(timeout=min(remaining, 0.5))

    def close(self):
        if self.p.poll() is None:
            self.p.kill()


class PtyTransport(Transport):
    def __init__(self, argv):
        if os.name == "nt":
            raise RuntimeError("PtyTransport is POSIX-only")
        import pty

        self.master, slave = pty.openpty()
        self._master_closed = False
        self.p = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)

    def write(self, s):
        os.write(self.master, s.encode())

    def read_until(self, predicate, timeout):
        import select

        acc, deadline = "", time.monotonic() + timeout
        while True:
            if predicate(acc):
                return acc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"read_until timed out; acc so far:\n{acc}")
            r, _, _ = select.select([self.master], [], [], min(remaining, 0.5))
            if r:
                try:
                    chunk = os.read(self.master, 4096).decode(errors="replace")
                except OSError:
                    return acc
                acc += _ANSI.sub("", chunk.replace("\r", ""))

    def close(self):
        if self.p.poll() is None:
            self.p.kill()
        if not self._master_closed:
            self._master_closed = True
            os.close(self.master)


def open_transport(argv, kind):
    if kind == "pipe":
        return PipeTransport(argv)
    if kind == "pty":
        return PtyTransport(argv)
    raise ValueError(f"unknown transport kind: {kind}")
