# Tooling setup: detect, then install

Do not give up because "the debugger isn't installed." Detect what is present, then install
the one that fits the language/platform. No machine-specific paths below - everything is
derived from `PATH`, environment variables, or platform install roots.

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
> with `lldb --version` (non-zero exit or a crash means reject it) before trusting it.
>
> Even once `--version` passes, the **persistent-session driver cannot drive the LLVM Windows
> lldb**: the lldb backend synchronizes on a `script print(<marker>)` token, but this build
> buffers embedded-Python `print()` output and flushes it only on the *next* command, so every
> `send` times out waiting for its marker. For lldb on Windows, use **scripted/batch** mode, an
> IDE-bundled lldb (e.g. CLion's, which is the documented driver fallback), or cdb for
> MSVC/clang-cl PDB builds. gdb and netcoredbg drive cleanly on Windows.

## Install per platform

### netcoredbg (.NET, all platforms)

Not distributed via package managers. Download the release artifact and extract:

```bash
# pick the asset for your platform from github.com/Samsung/netcoredbg/releases
#   netcoredbg-win64.zip / netcoredbg-linux-amd64.tar.gz / netcoredbg-osx-amd64.tar.gz
# extract, then put the netcoredbg binary on PATH, or set:
export NETCOREDBG=/path/to/netcoredbg            # POSIX
# or pass --debugger-path to dbg-session.py
```

```powershell
$env:NETCOREDBG = "C:\path\to\netcoredbg\netcoredbg.exe"   # Windows (parameterize the path)
```

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
