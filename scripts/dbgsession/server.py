"""Debug session server: listens on a TCP port and dispatches verb commands to a backend."""

import os
import socket
import sys
from pathlib import Path


def _dispatch(backend, verb_line: str) -> str:
    verb_line = verb_line.strip()
    if verb_line == "__STOP__":
        return "__STOP__"
    parts = verb_line.split(None, 1)
    if not parts:
        return "error: empty command"
    verb = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if verb == "break":
        location = rest.strip()
        if ":" not in location:
            return f"error: break requires FILE:LINE, got {location!r}"
        file_part, line_part = location.rsplit(":", 1)
        try:
            line_number = int(line_part)
        except ValueError:
            return f"error: invalid line number {line_part!r}"
        return backend.set_breakpoint(file_part, line_number)

    no_arg_table = {
        "run": backend.run,
        "continue": backend.cont,
        "step": backend.step_over,
        "stepin": backend.step_into,
        "bt": backend.backtrace,
    }
    one_arg_table = {
        "local": backend.read_local,
        "raw": backend.raw,
    }

    if verb in no_arg_table:
        return no_arg_table[verb]()
    if verb in one_arg_table:
        return one_arg_table[verb](rest.strip())
    return f"error: unknown verb {verb!r}"


class Server:
    def __init__(self, backend, session_dir: Path) -> None:
        self._backend = backend
        self._session_dir = session_dir
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._port: int = self._sock.getsockname()[1]

    @property
    def port(self) -> int:
        return self._port

    def _write_port_file(self) -> None:
        port_file = self._session_dir / "port"
        port_file.write_text(str(self._port))

    def serve_forever(self) -> None:
        self._write_port_file()
        while True:
            conn, _ = self._sock.accept()
            with conn:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
                request = data.decode(errors="replace").strip()
                response = _dispatch(self._backend, request)
                if response == "__STOP__":
                    conn.sendall(b"stopped\n")
                    self._sock.close()
                    self._backend.stop()
                    return
                conn.sendall((response + "\n").encode())


def _make_backend(debugger: str, program: str, program_args: list, debugger_path: str | None):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from backends.lldb_cli import LldbCliBackend
    from backends.mi import MiBackend

    backend_table = {
        "netcoredbg": lambda: MiBackend(
            "netcoredbg", "pipe", program, program_args, debugger_path
        ),
        "gdb": lambda: MiBackend(
            "gdb",
            "pty" if os.name != "nt" else "pipe",
            program,
            program_args,
            debugger_path,
        ),
        "lldb": lambda: LldbCliBackend("lldb", "pipe", program, program_args, debugger_path),
    }
    if debugger in backend_table:
        return backend_table[debugger]()
    if debugger == "cdb":
        from backends.cdb import CdbBackend

        return CdbBackend("cdb", "pipe", program, program_args, debugger_path)
    raise ValueError(f"unknown debugger: {debugger!r}")


def run_server_child(args) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tempfile

    import discovery

    session_dir = Path(tempfile.gettempdir()) / "dbg-session" / args.session
    session_dir.mkdir(parents=True, exist_ok=True)
    debugger_path = args.debugger_path or discovery.find_debugger(args.debugger)
    backend = _make_backend(args.debugger, args.program, args.program_args or [], debugger_path)
    backend.start()
    server = Server(backend, session_dir)
    server.serve_forever()
