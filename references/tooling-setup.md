# Tooling setup: detect, then install

Do not give up because "the debugger isn't installed." Detect what is present, then install
the one that fits the language/platform. No machine-specific paths below - everything is
derived from `PATH`, environment variables, or platform install roots.

## Automated: one command

`scripts/setup-debuggers.py` does the whole detect-then-install loop for you. It is
idempotent and platform-gated: it installs only the debuggers that make sense for the
current OS and skips any already discoverable (it reuses `discovery.find_debugger`, so the
lldb health-check and platform-root fallbacks apply).

```bash
python scripts/setup-debuggers.py            # ensure every relevant debugger is present
python scripts/setup-debuggers.py --dry-run  # show what it would install, change nothing
python scripts/setup-debuggers.py --only netcoredbg,lldb
```

Targets per platform: Linux installs netcoredbg/gdb/lldb, macOS installs netcoredbg/lldb,
Windows installs netcoredbg/cdb/lldb. A few paths cannot run fully unattended and are
reported as `manual` with the exact next step: password-required `sudo` on Linux, and
`xcode-select --install` on macOS (it launches Apple's GUI installer). Everything else
installs without prompting. (The umbrella skills installer can run this for you after a
skill install: `install-skills.sh --setup-debuggers` / `install-skills.bat --setup-debuggers`.)

The rest of this page is the manual playbook the script automates - reach for it when you
want to install one tool by hand or understand what the script is doing.

## Pick the right tool

| Language | Platform | Debugger | Reference |
|---|---|---|---|
| .NET (C#/F#/VB) | any | netcoredbg | `netcoredbg-dotnet.md` |
| native C/C++ | Linux | gdb (or lldb) | `gdb-native.md` |
| native C/C++ | macOS | lldb | `lldb-native.md` |
| native C/C++ | Windows (MSVC/clang-cl) | cdb | `cdb-windows.md` |
| native C/C++ | Windows (clang/DWARF) | lldb (IDE-bundled) | `lldb-native.md` |
| managed + native mix | Windows | see mixed-mode | `mixed-mode.md` |

## Detect

Cross-platform PATH probe:

```bash
# POSIX
for t in gdb lldb netcoredbg cdb; do command -v "$t" && echo "  ^ $t found"; done
```

```powershell
# Windows
foreach ($t in 'gdb','lldb','netcoredbg','cdb') { (Get-Command $t -ErrorAction SilentlyContinue)?.Source }
```

PATH is not the only place. Known install roots, discovered via environment variables (never
a hard-coded user directory):

- **lldb (Windows, IDE-bundled)**: `%LOCALAPPDATA%\Programs\CLion\bin\lldb\win\x64\bin\lldb.exe`.
  Use this when the LLVM-installer lldb on PATH is broken (see the health-check note below).
- **cdb (Windows SDK)**: `%ProgramFiles(x86)%\Windows Kits\10\Debuggers\x64\cdb.exe`.
- **LLVM tools (Windows)**: `%ProgramFiles%\LLVM\bin`.

The shipped driver's `discovery.find_debugger(kind)` already encodes this: PATH, then env
overrides (`$GDB` / `$LLDB` / `$NETCOREDBG` / `$CDB`), then platform roots, plus a
health-check for lldb.

> **lldb health-check (Windows).** A PATH `lldb` from the LLVM installer can crash on launch
> with `unable to find 'python311.dll'` - it embeds CPython and needs a matching **Python 3.11**
> runtime reachable (the LLVM 22.x build links 3.11 specifically, not 3.12/3.13). Always verify
> with `lldb --version` (non-zero exit or a crash means reject it) before trusting it. When the
> runtime is missing the live driver's `start` just times out waiting for an lldb that never came
> up; the health-check is what turns that into an actionable rejection. Once `lldb --version`
> passes, the persistent-session driver drives upstream LLVM **lldb 22.x** fine - verified end to
> end on Linux (Arch, lldb 22.1.6); gdb and netcoredbg drive cleanly everywhere.

## Install per platform

### netcoredbg (.NET, all platforms)

Not distributed via package managers. Download the release artifact and extract. The
official releases are `netcoredbg-win64.zip`, `netcoredbg-linux-amd64.tar.gz`,
`netcoredbg-linux-arm64.tar.gz`, and `netcoredbg-osx-amd64.tar.gz` - there is **no native
macOS arm64 build**, so Apple Silicon uses the `osx-amd64` binary under Rosetta 2 (Windows
arm64 likewise falls back to `win64`).

```bash
# pick the asset for your platform from github.com/Samsung/netcoredbg/releases
# extract, then put the netcoredbg binary on PATH, or set:
export NETCOREDBG=/path/to/netcoredbg            # POSIX
# or pass --debugger-path to dbg-session.py
```

```powershell
$env:NETCOREDBG = "C:\path\to\netcoredbg\netcoredbg.exe"   # Windows (parameterize the path)
```

`setup-debuggers.py` extracts into a canonical per-user dir derived from the environment
(`%LOCALAPPDATA%\Programs\netcoredbg\` on Windows, `$XDG_DATA_HOME/netcoredbg` or
`~/.local/share/netcoredbg` on POSIX), and `discovery.find_debugger("netcoredbg")` looks
there as a fallback - so an auto-installed netcoredbg is found without touching `PATH`.

### gdb / lldb (native)

```bash
# Debian/Ubuntu
sudo apt-get install -y gdb            # or: lldb
# Fedora
sudo dnf install -y gdb lldb
# macOS (lldb ships with Xcode command-line tools)
xcode-select --install                 # provides lldb
brew install gdb                       # gdb on macOS needs codesigning to control processes
```

```powershell
# Windows: the LLVM installer provides lldb (may need the Python runtime - see health-check)
winget install --id LLVM.LLVM
```

### cdb (Windows native)

cdb ships with the Windows SDK "Debugging Tools for Windows" feature.

- `winget install --id Microsoft.WinDbg` installs **WinDbgX** but NOT the classic console
  `cdb.exe`.
- The classic `cdb.exe` comes from the **Windows SDK installer** with only the "Debugging
  Tools for Windows" feature selected, landing under
  `%ProgramFiles(x86)%\Windows Kits\10\Debuggers\x64\`.

Verify any install with `<tool> --version` (or `cdb -version`).

## Compilers for debug builds

Debugging needs symbols, which need a debug build:

- native + DWARF: `clang++ -g -O0` or `g++ -g -O0`
- native + CodeView (for cdb): `clang-cl /Zi /Od` or MSVC `/Zi` (build from PowerShell, not
  Git Bash - it mangles `/`-flags)
- .NET: `dotnet build -c Debug`
