"""lldb CLI backend using pipe transport with content-gated async stop detection."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backends.base import Backend
from transport import open_transport

_TIMEOUT = 30.0
_STOP_PATTERN = re.compile(r"stop reason =|Process \d+ exited|exited with status")


def _has_stopped(text: str) -> bool:
    return bool(_STOP_PATTERN.search(text))


class LldbCliBackend(Backend):
    def __init__(
        self,
        debugger: str,
        kind: str,
        program: str,
        program_args: list,
        debugger_path: str | None = None,
    ) -> None:
        self._debugger = debugger
        self._kind = kind
        self._program = program
        self._program_args = program_args
        self._debugger_path = debugger_path or "lldb"
        self._transport = None
        self._counter = 0

    def _next_token(self) -> str:
        self._counter += 1
        return f"@@DBG{self._counter}@@"

    def _run_sync(self, command: str) -> str:
        token = self._next_token()
        self._transport.write(command + "\n")
        self._transport.write(f'script print("{token}")\n')
        acc = self._transport.read_until(
            lambda text: any(line.strip() == token for line in text.splitlines()),
            _TIMEOUT,
        )
        lines = acc.splitlines(keepends=True)
        result_lines = [line for line in lines if line.strip() != token]
        return "".join(result_lines)

    def _run_exec(self, command: str) -> str:
        self._transport.write(command + "\n")
        stop_text = self._transport.read_until(_has_stopped, _TIMEOUT)
        token = self._next_token()
        self._transport.write(f'script print("{token}")\n')
        drain = self._transport.read_until(
            lambda text: any(line.strip() == token for line in text.splitlines()),
            _TIMEOUT,
        )
        lines = drain.splitlines(keepends=True)
        drain_clean = "".join(line for line in lines if line.strip() != token)
        return stop_text + drain_clean

    def start(self) -> None:
        argv = [self._debugger_path, "--no-use-colors", self._program]
        if self._program_args:
            argv += ["--", *self._program_args]
        self._transport = open_transport(argv, "pipe")

    def set_breakpoint(self, file: str, line: int) -> str:
        return self._run_sync(f"breakpoint set --file {file} --line {line}")

    def run(self) -> str:
        return self._run_exec("run")

    def cont(self) -> str:
        return self._run_exec("continue")

    def step_over(self) -> str:
        return self._run_exec("next")

    def step_into(self) -> str:
        return self._run_exec("step")

    def read_local(self, name: str) -> str:
        text = self._run_sync(f"frame variable {name}")
        for line in text.splitlines():
            if name in line and " = " in line:
                return line.rsplit(" = ", 1)[-1].strip()
        return ""

    def backtrace(self) -> str:
        return self._run_sync("bt")

    def raw(self, command: str) -> str:
        return self._run_sync(command)

    def stop(self) -> None:
        if self._transport is not None:
            try:
                self._transport.write("process kill\n")
            except OSError as error:
                import sys as _sys

                print(f"stop: process kill write failed: {error}", file=_sys.stderr)
            self._transport.close()
            self._transport = None
