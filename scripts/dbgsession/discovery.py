import glob
import os
import shutil
import subprocess
from pathlib import Path


def netcoredbg_install_dir() -> Path | None:
    """Canonical user directory where setup-debuggers.py extracts netcoredbg.

    netcoredbg is not distributed by any package manager, so the setup script
    downloads the release archive into a stable per-user location and detection
    looks there. Derived from environment roots only (never a fixed home dir) so
    the same code resolves correctly for any user on any host.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "Programs" / "netcoredbg" if base else None
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "netcoredbg"
    home = os.environ.get("HOME")
    return Path(home) / ".local" / "share" / "netcoredbg" if home else None


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
    found = shutil.which("netcoredbg") or os.environ.get("NETCOREDBG")
    if found is not None:
        return found
    install_dir = netcoredbg_install_dir()
    if install_dir is None:
        return None
    binary = "netcoredbg.exe" if os.name == "nt" else "netcoredbg"
    # The release archive extracts to a netcoredbg/ subfolder holding the binary
    # plus its managed support DLLs; check that layout and the flat one.
    for candidate in (install_dir / "netcoredbg" / binary, install_dir / binary):
        if candidate.is_file():
            return str(candidate)
    return None


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
    # winget installs LLVM under Program Files\LLVM\bin and does NOT add it to
    # PATH, so a winget'd lldb is invisible to the shutil.which probe above.
    for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        program_files = os.environ.get(env_var)
        if program_files:
            llvm_lldb = os.path.join(program_files, "LLVM", "bin", "lldb.exe")
            if os.path.isfile(llvm_lldb):
                candidates.append(llvm_lldb)
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
