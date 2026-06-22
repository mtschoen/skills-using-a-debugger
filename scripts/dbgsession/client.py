"""Debug session client: sends a verb to the running server and prints the reply."""

import socket
import time
from pathlib import Path


def _read_port(session_dir: Path, retries: int = 50, interval: float = 0.1) -> int:
    port_file = session_dir / "port"
    for _ in range(retries):
        if port_file.exists():
            text = port_file.read_text().strip()
            if text:
                return int(text)
        time.sleep(interval)
    raise TimeoutError(f"port file not found after {retries * interval:.1f}s: {port_file}")


def send_verb(session_dir: Path, verb_line: str) -> str:
    port = _read_port(session_dir)
    with socket.create_connection(("127.0.0.1", port), timeout=10.0) as conn:
        conn.sendall((verb_line.strip() + "\n").encode())
        reply = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            reply += chunk
            if reply.endswith(b"\n"):
                break
    return reply.decode(errors="replace")
