import glob
import os
import shutil
import subprocess


def _health_check(path: str) -> bool:
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _find_gdb() -> str | None:
    return shutil.which("gdb") or os.environ.get("GDB")


def _find_netcoredbg() -> str | None:
    return shutil.which("netcoredbg") or os.environ.get("NETCOREDBG")


def _find_cdb() -> str | None:
    candidate = shutil.which("cdb")
    if candidate is not None:
        return candidate
    candidate = os.environ.get("CDB")
    if candidate is not None:
        return candidate
    prog_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    if prog_files_x86:
        kit_path = os.path.join(
            prog_files_x86,
            "Windows Kits",
            "10",
            "Debuggers",
            "x64",
            "cdb.exe",
        )
        if os.path.isfile(kit_path):
            return kit_path
    return None


def _find_lldb() -> str | None:
    candidates: list[str] = []
    env_lldb = os.environ.get("LLDB")
    if env_lldb:
        candidates.append(env_lldb)
    which_lldb = shutil.which("lldb")
    if which_lldb:
        candidates.append(which_lldb)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        pattern = os.path.join(
            local_app_data,
            "Programs",
            "CLion",
            "bin",
            "lldb",
            "win",
            "x64",
            "bin",
            "lldb.exe",
        )
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    for candidate in candidates:
        if _health_check(candidate):
            return candidate
    return None


_FINDERS = {
    "gdb": _find_gdb,
    "netcoredbg": _find_netcoredbg,
    "cdb": _find_cdb,
    "lldb": _find_lldb,
}


def find_debugger(kind: str) -> str | None:
    finder = _FINDERS.get(kind)
    if finder is None:
        raise ValueError(f"unknown debugger kind: {kind!r}")
    return finder()
