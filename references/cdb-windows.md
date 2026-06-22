# cdb (native C/C++ on Windows)

## When this debugger

- **Platform**: Windows.
- **Language**: native C/C++ built with MSVC or clang-cl (CodeView PDB symbols).
- **Build-info fit**: a `.pdb` next to the binary. cdb is the right native debugger on
  Windows when gdb/lldb cannot read the MSVC-style symbols. It is the console sibling of
  WinDbg, fully scriptable, and synchronous over pipes.

## Get the debug build

```powershell
clang-cl /Zi /Od /Fe:hello.exe hello.cpp     # emits hello.pdb next to hello.exe
```

or an MSVC `/Zi` Debug build. `/Zi` emits CodeView debug info into a PDB; `/Od` disables
optimization. The PDB must sit next to the executable (or be reachable via the symbol path).

> Build clang-cl from PowerShell or a subprocess argv list, **not** Git Bash - Git Bash
> mangles leading-slash flags (`/Zi` becomes `C:/Program Files/Git/Zi`).

## Core command cheatsheet

cdb uses terse single-letter commands. Backticks denote source-line syntax.

| Universal action | cdb command |
|---|---|
| set breakpoint | `` bp `FILE:LINE` `` |
| deferred breakpoint (not yet loaded) | `` bu `FILE:LINE` `` |
| break on symbol | `bp MODULE!FUNC` |
| run / continue | `g` |
| step over | `p` |
| step into | `t` |
| step out | `gu` |
| backtrace | `k` |
| read all locals | `dv` |
| read one local | `dv NAME` |
| evaluate C++ expression | `?? EXPR` |
| read memory | `db ADDR` / `dd ADDR` / `dq ADDR` |
| break on thrown exception | `sxe eh` (native C++) / `sxe clr` (managed) / `sxe av` (access violation) |
| quit | `q` |

Verified stop + locals output (clang-cl PDB target):

```
0:000> bp `hello.cpp:3`
0:000> g
Breakpoint 0 hit
hello!add+0xc:
00007ff6`3f97100c 8b442408        mov     eax,dword ptr [rsp+8]
0:000> dv
              a = 0n0
              b = 0n0
            sum = 0n0
```

`dv` prints integers in cdb's `0nNNN` notation (`0n` prefix = decimal). The driver's
`read_local` strips the `0n` and returns the plain decimal string.

## Driver / adapter note

- `dbg-session.py --debugger cdb` (transport: pipe).
- cdb is **fully synchronous** over stdin/stdout - the marker follows the command directly.
  Marker command: `.echo TOKEN` (cdb echoes it on its own line as `0:000> @@TOKEN@@`).
- The prompt is `N:NNN> ` (e.g. `0:000> `). `start` drains all startup noise (module loads,
  loader breakpoint) by sending `.echo TOKEN` first and reading to the token.
- Batch form: `cdb -cf script.txt hello.exe` with `bp` / `g` / `dv` / `q` in the file
  (see `scripted-batch.md`).

## Gotchas

- **CodeView PDB required.** A DWARF (`-g`) build will not give cdb line/local info; use
  `clang-cl /Zi` or MSVC `/Zi`.
- **Startup symbol-server warnings are noise**: `WARNING: Unable to verify checksum` and
  `srv*` lines come from the default symbol server being unreachable; the local PDB still
  binds via the executable's CodeView pointer.
- **Symbol path**: set `_NT_SYMBOL_PATH` (e.g. `srv*C:\symbols*https://msdl.microsoft.com/download/symbols`)
  if you need OS symbols; not required for your own PDBs.
- **Decimal notation**: parse `0nNNN` for integers; `0xNNN` is hex.
- **Discovery**: cdb is found on PATH, via `$CDB`, then
  `%ProgramFiles(x86)%\Windows Kits\10\Debuggers\x64\cdb.exe`. Install via the Windows SDK
  "Debugging Tools for Windows" feature (see `references/tooling-setup.md`).
- **Managed code is opaque**: cdb sees .NET managed frames as opaque without SOS; for C#
  use netcoredbg (`references/netcoredbg-dotnet.md`). For mixed managed/native, see
  `references/mixed-mode.md`.
