"""cdb backend using pipe transport with .echo-token synchronisation."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backends.base import Backend
from transport import open_transport

_TIMEOUT = 30.0
_PROMPT_RE = re.compile(r"^\d+:\d+> ", re.MULTILINE)


def _has_token(token: str):
    def predicate(text: str) -> bool:
        return any(token in line for line in text.splitlines())

    return predicate


def _strip_token_lines(text: str, token: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if token not in line
    )


class CdbBackend(Backend):
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
        self._debugger_path = debugger_path or "cdb"
        self._transport = None
        self._counter = 0

    def _next_token(self) -> str:
        self._counter += 1
        return f"@@CDBDBG{self._counter}@@"

    def _run_sync(self, command: str) -> str:
        token = self._next_token()
        self._transport.write(command + "\n")
        self._transport.write(f".echo {token}\n")
        acc = self._transport.read_until(_has_token(token), _TIMEOUT)
        return _strip_token_lines(acc, token)

    def start(self) -> None:
        argv = [self._debugger_path, self._program, *self._program_args]
        self._transport = open_transport(argv, "pipe")
        token = self._next_token()
        self._transport.write(f".echo {token}\n")
        self._transport.read_until(_has_token(token), _TIMEOUT)

    def set_breakpoint(self, file: str, line: int) -> str:
        result = self._run_sync(f"bp `{file}:{line}`")
        if "could not" in result.lower() or "syntax error" in result.lower():
            return self._run_sync(f"bu `{file}:{line}`")
        return result

    def run(self) -> str:
        return self._run_sync("g")

    def cont(self) -> str:
        return self._run_sync("g")

    def step_over(self) -> str:
        return self._run_sync("p")

    def step_into(self) -> str:
        return self._run_sync("t")

    def read_local(self, name: str) -> str:
        text = self._run_sync(f"dv {name}")
        for line in text.splitlines():
            if name in line and "=" in line:
                raw = line.split("=", 1)[-1].strip()
                if raw.startswith("0n"):
                    return raw[2:]
                return raw
        return ""

    def backtrace(self) -> str:
        return self._run_sync("k")

    def raw(self, command: str) -> str:
        return self._run_sync(command)

    def stop(self) -> None:
        if self._transport is not None:
            try:
                self._transport.write("q\n")
            except OSError as error:
                import sys as _sys

                print(f"stop: q write failed: {error}", file=_sys.stderr)
            self._transport.close()
            self._transport = None
