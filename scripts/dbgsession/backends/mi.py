"""GDB/MI backend for netcoredbg and gdb."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backends.base import Backend
from miparse import parse_mi_line
from transport import open_transport

_TIMEOUT = 30.0
_DRAIN_TIMEOUT = 2.0


def _has_stopped(text: str) -> bool:
    for line in text.splitlines():
        parsed = parse_mi_line(line)
        if parsed.get("kind") == "async" and parsed.get("class") == "stopped":
            return True
    return False


def _has_result(text: str) -> bool:
    for line in text.splitlines():
        parsed = parse_mi_line(line)
        if parsed.get("kind") == "result" and parsed.get("class") in ("done", "error"):
            return True
    return False


def _has_prompt(text: str) -> bool:
    return any(line.strip() == "(gdb)" for line in text.splitlines())


def _find_stopped_reason(text: str) -> str:
    for line in text.splitlines():
        parsed = parse_mi_line(line)
        if parsed.get("kind") == "async" and parsed.get("class") == "stopped":
            fields: dict = parsed.get("fields") or {}
            return fields.get("reason", "")
    return ""


def _find_result_value(text: str) -> str:
    for line in text.splitlines():
        parsed = parse_mi_line(line)
        if parsed.get("kind") == "result" and parsed.get("class") == "done":
            fields: dict = parsed.get("fields") or {}
            return fields.get("value", "")
    return ""


def _drain_to_prompt(transport, accumulated: str) -> str:
    already = accumulated

    def prompt_seen(new: str) -> bool:
        return _has_prompt(already + new)

    try:
        return transport.read_until(prompt_seen, _DRAIN_TIMEOUT)
    except TimeoutError:
        return ""


class MiBackend(Backend):
    def __init__(
        self,
        debugger: str,
        kind: str,
        program: str,
        program_args: list,
        debugger_path: str | None = None,
    ) -> None:
        if debugger not in ("netcoredbg", "gdb"):
            raise ValueError(f"unsupported debugger: {debugger}")
        self._debugger = debugger
        self._kind = kind
        self._program = program
        self._program_args = program_args
        self._debugger_path = debugger_path
        self._transport = None

    def start(self) -> None:
        if self._debugger == "netcoredbg":
            path = self._debugger_path or "netcoredbg"
            argv = [path, "--interpreter=mi", "--", self._program, *self._program_args]
        else:
            path = self._debugger_path or "gdb"
            argv = [path, "--interpreter=mi2", "--args", self._program, *self._program_args]
        self._transport = open_transport(argv, self._kind)
        self._transport.read_until(_has_prompt, _TIMEOUT)

    def _run_until_stop(self, command: str) -> str:
        self._transport.write(command + "\n")
        acc = self._transport.read_until(_has_stopped, _TIMEOUT)
        acc += _drain_to_prompt(self._transport, acc)
        return acc

    def _run_sync(self, command: str) -> str:
        self._transport.write(command + "\n")
        acc = self._transport.read_until(_has_result, _TIMEOUT)
        acc += _drain_to_prompt(self._transport, acc)
        return acc

    def set_breakpoint(self, file: str, line: int) -> str:
        return self._run_sync(f"-break-insert {file}:{line}")

    def run(self) -> str:
        result = self._run_until_stop("-exec-run")
        if self._debugger == "netcoredbg":
            reason = _find_stopped_reason(result)
            if reason == "entry-point-hit":
                result = self._run_until_stop("-exec-continue")
        return result

    def cont(self) -> str:
        return self._run_until_stop("-exec-continue")

    def step_over(self) -> str:
        return self._run_until_stop("-exec-next")

    def step_into(self) -> str:
        return self._run_until_stop("-exec-step")

    def read_local(self, name: str) -> str:
        text = self._run_sync(f"-var-create {name} * {name}")
        return _find_result_value(text)

    def backtrace(self) -> str:
        return self._run_sync("-stack-list-frames")

    def raw(self, command: str) -> str:
        self._transport.write(command + "\n")
        return _drain_to_prompt(self._transport, "")

    def stop(self) -> None:
        if self._transport is not None:
            try:
                self._transport.write("-gdb-exit\n")
            except OSError as error:
                import sys as _sys
                print(f"stop: -gdb-exit write failed: {error}", file=_sys.stderr)
            self._transport.close()
            self._transport = None
