"""CLI entry point for persistent debug sessions."""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "dbgsession"))

from client import send_verb

_SESSION_BASE = Path(tempfile.gettempdir()) / "dbg-session"
_PORT_WAIT_SECONDS = 10.0
_PORT_POLL_INTERVAL = 0.1


def _session_dir(name: str) -> Path:
    return _SESSION_BASE / name


def _wait_for_port_file(session_dir: Path) -> bool:
    port_file = session_dir / "port"
    deadline = time.monotonic() + _PORT_WAIT_SECONDS
    while time.monotonic() < deadline:
        if port_file.exists() and port_file.read_text().strip():
            return True
        time.sleep(_PORT_POLL_INTERVAL)
    return False


def _cmd_start(args: argparse.Namespace) -> int:
    if os.environ.get("_DBG_SERVER") == "1":
        from server import run_server_child

        run_server_child(args)
        return 0

    session_dir = _session_dir(args.session)
    session_dir.mkdir(parents=True, exist_ok=True)
    port_file = session_dir / "port"
    if port_file.exists():
        port_file.unlink()

    child_env = {**os.environ, "_DBG_SERVER": "1"}
    child_argv = [sys.executable, __file__, *sys.argv[1:]]

    if os.name == "nt":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            child_argv,
            env=child_env,
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            close_fds=True,
        )
    else:
        subprocess.Popen(
            child_argv,
            env=child_env,
            start_new_session=True,
            close_fds=True,
        )

    if not _wait_for_port_file(session_dir):
        print(f"error: server did not write port file within {_PORT_WAIT_SECONDS}s", file=sys.stderr)
        return 1
    return 0


def _cmd_send(args: argparse.Namespace) -> int:
    session_dir = _session_dir(args.session)
    reply = send_verb(session_dir, args.verb)
    print(reply, end="")
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    session_dir = _session_dir(args.session)
    reply = send_verb(session_dir, "__STOP__")
    print(reply, end="")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persistent debugger session driver")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    start_parser = subparsers.add_parser("start", help="Start a debug session")
    start_parser.add_argument(
        "--debugger",
        required=True,
        choices=["netcoredbg", "gdb", "lldb", "cdb"],
    )
    start_parser.add_argument("--debugger-path", dest="debugger_path", default=None)
    start_parser.add_argument("--session", required=True)
    start_parser.add_argument("program")
    start_parser.add_argument("program_args", nargs="*", metavar="ARGS")

    send_parser = subparsers.add_parser("send", help="Send a verb to a running session")
    send_parser.add_argument("--session", required=True)
    send_parser.add_argument("verb")

    stop_parser = subparsers.add_parser("stop", help="Stop a running session")
    stop_parser.add_argument("--session", required=True)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    dispatch = {
        "start": _cmd_start,
        "send": _cmd_send,
        "stop": _cmd_stop,
    }
    return dispatch[args.subcommand](args)


if __name__ == "__main__":
    sys.exit(main())
