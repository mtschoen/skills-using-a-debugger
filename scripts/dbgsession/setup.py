"""Detect-then-install the debuggers this skill drives.

Reuses ``discovery.find_debugger`` for the detect half so detection logic (the
lldb health-check, the cdb/lldb platform roots) lives in exactly one place, then
installs whatever is missing and relevant to the current platform. Idempotent:
anything already found is reported present and skipped.

Pure decision functions (platform target list, release-asset selection) are kept
separate from the imperative install steps so the decision surface is unit
testable without privileged commands or network access. Standard library only,
because the skill ships standalone into ``~/.claude/skills``.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(__file__))
from discovery import find_debugger, netcoredbg_install_dir

# All four debuggers, grouped by the platform on which they apply. netcoredbg is
# managed-runtime and runs everywhere; the native debuggers are platform-bound.
_TARGETS_BY_SYSTEM = {
    "linux": ("netcoredbg", "gdb", "lldb"),
    "darwin": ("netcoredbg", "lldb"),
    "windows": ("netcoredbg", "cdb", "lldb"),
}

_NETCOREDBG_RELEASES_API = (
    "https://api.github.com/repos/Samsung/netcoredbg/releases/latest"
)
_WINDESKTOP_DEBUGGERS_FEATURE = "OptionId.WindowsDesktopDebuggers"
_HTTP_TIMEOUT_SECONDS = 60
# winget's APPINSTALLER_CLI_ERROR_UPDATE_NOT_APPLICABLE: package already
# installed, no newer version available. LLVM is present, so treat it as success.
_WINGET_NO_APPLICABLE_UPGRADE = 0x8A15002B


class Result(NamedTuple):
    kind: str
    status: str  # present | installed | failed | manual | dryrun
    detail: str


def platform_targets(system: str) -> tuple[str, ...]:
    """Debugger kinds worth installing on ``system`` (a ``platform.system()`` value)."""
    return _TARGETS_BY_SYSTEM.get(system.lower(), ())


def netcoredbg_asset_substring(system: str, machine: str) -> str | None:
    """The release-asset name fragment for this OS/arch, or None if unsupported.

    netcoredbg ships win64, linux-amd64, linux-arm64, and osx-amd64 only. There
    is no native macOS arm64 build, so Apple Silicon takes the osx-amd64 binary
    and runs it under Rosetta 2; Windows arm64 likewise falls back to win64.
    """
    system = system.lower()
    machine = machine.lower()
    is_arm = machine in ("arm64", "aarch64")
    if system == "windows":
        return "win64"
    if system == "darwin":
        return "osx-amd64"
    if system == "linux":
        return "linux-arm64" if is_arm else "linux-amd64"
    return None


def select_asset(asset_names: list[str], substring: str) -> str | None:
    """Pick the release asset whose name contains ``substring`` (first match)."""
    for name in asset_names:
        if substring in name:
            return name
    return None


def _http_get(url: str, *, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "using-a-debugger-setup"}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
        return response.read()


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def _extract_archive(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        return
    with tarfile.open(archive) as tf:
        tf.extractall(dest, filter="data")


def install_netcoredbg(dry_run: bool) -> Result:
    substring = netcoredbg_asset_substring(platform.system(), platform.machine())
    if substring is None:
        return Result(
            "netcoredbg", "failed", f"no release asset for {platform.machine()}"
        )
    install_dir = netcoredbg_install_dir()
    if install_dir is None:
        return Result(
            "netcoredbg",
            "failed",
            "could not resolve an install directory from the environment",
        )
    if dry_run:
        return Result(
            "netcoredbg", "dryrun", f"download '{substring}' asset into {install_dir}"
        )
    try:
        release = json.loads(
            _http_get(_NETCOREDBG_RELEASES_API, accept="application/vnd.github+json")
        )
        assets = {
            asset["name"]: asset["browser_download_url"]
            for asset in release.get("assets", [])
        }
        asset_name = select_asset(list(assets), substring)
        if asset_name is None:
            return Result(
                "netcoredbg",
                "failed",
                f"no asset matching '{substring}' in latest release",
            )
        payload = _http_get(assets[asset_name])
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        return Result("netcoredbg", "failed", f"download failed: {exc}")
    with tempfile.TemporaryDirectory() as scratch:
        archive = Path(scratch) / asset_name
        archive.write_bytes(payload)
        if install_dir.exists():
            shutil.rmtree(install_dir)
        try:
            _extract_archive(archive, install_dir)
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
            return Result("netcoredbg", "failed", f"extract failed: {exc}")
    return Result(
        "netcoredbg", "installed", f"extracted {asset_name} into {install_dir}"
    )


_LINUX_PACKAGE_MANAGERS = (
    ("apt-get", ["apt-get", "install", "-y"]),
    ("dnf", ["dnf", "install", "-y"]),
    ("pacman", ["pacman", "-S", "--noconfirm"]),
    ("zypper", ["zypper", "install", "-y"]),
)


def install_native_linux(kind: str, dry_run: bool) -> Result:
    for tool, install_args in _LINUX_PACKAGE_MANAGERS:
        if shutil.which(tool) is None:
            continue
        command = [*install_args, kind]
        sudo = [] if os.geteuid() == 0 else ["sudo", "-n"]
        if dry_run:
            return Result(kind, "dryrun", " ".join([*sudo, *command]))
        if sudo and _run(["sudo", "-n", "true"]).returncode != 0:
            return Result(
                kind,
                "manual",
                f"sudo {' '.join(command)}  (passwordless sudo unavailable)",
            )
        completed = _run([*sudo, *command])
        if completed.returncode == 0:
            return Result(kind, "installed", f"via {tool}")
        return Result(
            kind,
            "failed",
            completed.stderr.strip() or f"{tool} exited {completed.returncode}",
        )
    return Result(
        kind, "manual", "no supported package manager (apt-get/dnf/pacman/zypper) found"
    )


def install_lldb_macos(dry_run: bool) -> Result:
    if shutil.which("brew") is not None:
        if dry_run:
            return Result("lldb", "dryrun", "brew install llvm")
        completed = _run(["brew", "install", "llvm"])
        if completed.returncode == 0:
            return Result("lldb", "installed", "via Homebrew llvm")
        return Result(
            "lldb", "failed", completed.stderr.strip() or "brew install llvm failed"
        )
    if dry_run:
        return Result("lldb", "dryrun", "xcode-select --install")
    completed = _run(["xcode-select", "--install"])
    # xcode-select launches an asynchronous GUI installer; it cannot finish unattended.
    return Result(
        "lldb",
        "manual",
        "launched 'xcode-select --install' - finish in the macOS dialog",
    )


def install_cdb_windows(dry_run: bool) -> Result:
    installer = shutil.which("winsdksetup") or shutil.which("winsdksetup.exe")
    if installer is None:
        return Result(
            "cdb",
            "manual",
            "install the Windows SDK 'Debugging Tools for Windows' feature "
            "(winsdksetup.exe /features OptionId.WindowsDesktopDebuggers /quiet /norestart)",
        )
    command = [
        installer,
        "/features",
        _WINDESKTOP_DEBUGGERS_FEATURE,
        "/quiet",
        "/norestart",
    ]
    if dry_run:
        return Result("cdb", "dryrun", " ".join(command))
    completed = _run(command)
    if completed.returncode == 0:
        return Result("cdb", "installed", "via Windows SDK debuggers feature")
    return Result(
        "cdb",
        "failed",
        completed.stderr.strip() or f"winsdksetup exited {completed.returncode}",
    )


def install_lldb_windows(dry_run: bool) -> Result:
    if shutil.which("winget") is None:
        return Result("lldb", "manual", "install LLVM (winget install --id LLVM.LLVM)")
    command = [
        "winget",
        "install",
        "--id",
        "LLVM.LLVM",
        "--accept-source-agreements",
        "--accept-package-agreements",
    ]
    if dry_run:
        return Result("lldb", "dryrun", " ".join(command))
    completed = _run(command)
    if completed.returncode == 0:
        return Result("lldb", "installed", "via winget LLVM.LLVM")
    if completed.returncode == _WINGET_NO_APPLICABLE_UPGRADE:
        return Result("lldb", "present", "winget reports LLVM already installed")
    return Result(
        "lldb",
        "failed",
        completed.stderr.strip() or f"winget exited {completed.returncode}",
    )


def install_for(kind: str, system: str, dry_run: bool) -> Result:
    """Dispatch a single debugger install for the current ``system``."""
    if kind == "netcoredbg":
        return install_netcoredbg(dry_run)
    if system == "linux":
        return install_native_linux(kind, dry_run)
    if system == "darwin":
        return install_lldb_macos(dry_run)
    if system == "windows":
        return (
            install_cdb_windows(dry_run)
            if kind == "cdb"
            else install_lldb_windows(dry_run)
        )
    return Result(kind, "failed", f"no installer for {kind} on {system}")


def run(
    only: list[str] | None = None,
    dry_run: bool = False,
    *,
    report: Callable[[str], None] = print,
) -> list[Result]:
    """Ensure every platform-relevant debugger is present, installing the missing ones."""
    system = platform.system().lower()
    targets = platform_targets(system)
    if not targets:
        report(f"no debugger targets defined for platform '{system}'")
        return []
    if only:
        requested = {kind.strip() for kind in only}
        targets = tuple(kind for kind in targets if kind in requested)

    results: list[Result] = []
    for kind in targets:
        existing = find_debugger(kind)
        if existing is not None:
            result = Result(kind, "present", existing)
        else:
            result = install_for(kind, system, dry_run)
        results.append(result)
        report(f"  {result.kind:<11} {result.status:<10} {result.detail}")
    return results
