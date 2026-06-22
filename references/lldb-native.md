# lldb (native C/C++/Rust)

## When this debugger

- **Platform**: macOS (primary), Linux, Windows (against clang-built binaries).
- **Language**: native C/C++/Objective-C/Rust compiled with DWARF debug info.
- **Build-info fit**: DWARF (`-g`). On Windows lldb reads clang DWARF output; it is only
  partial against MSVC PDBs - prefer cdb there (`references/cdb-windows.md`).

## Get the debug build

```bash
clang++ -g -O0 -o hello hello.cpp     # -O0 so variables are not optimized away
```

`-g` emits debug info, `-O0` keeps locals readable. Optimized builds inline and elide
variables, which makes `frame variable` show `<optimized out>`.

## Core command cheatsheet

| Universal action | lldb command | short |
|---|---|---|
| set breakpoint | `breakpoint set -f FILE -l LINE` | `b FILE:LINE` |
| break on function | `breakpoint set -n FUNC` | `b FUNC` |
| run | `run` | `r` |
| continue | `continue` | `c` |
| step over | `next` | `n` |
| step into | `step` | `s` |
| step out | `finish` | - |
| backtrace | `thread backtrace` | `bt` |
| read all locals | `frame variable` | - |
| read one local | `frame variable NAME` | - |
| evaluate expression | `expression EXPR` | `p EXPR` |
| mutate a variable | `expression sum = -1` | - |
| read memory | `memory read ADDR` | `x ADDR` |

Verified stop + locals output:

```
(lldb) breakpoint set -f hello.cpp -l 3
Breakpoint 1: where = hello`add(int,int) + 12 at hello.cpp:3, address = 0x...
(lldb) run
Process ... stopped
* thread #1, stop reason = breakpoint 1.1
    frame #0: 0x... hello`add(a=0, b=0) at hello.cpp:3
(lldb) frame variable
(int) a = 0
(int) b = 0
(int) sum = 0
```

Live mutation is confirmed: `expression sum = -1` returns `(int) $0 = -1`.

## Driver / adapter note

- `dbg-session.py --debugger lldb` (transport: pipe).
- Stop detection is **content-based**, not a plain marker. lldb delivers stop events on a
  background thread in pipe mode, so after `run`/`continue` the driver reads until
  `stop reason =` / `Process \d+ exited` matches, *then* sends the marker
  `script print("TOKEN")` to drain trailing source-context lines. For synchronous commands
  (`breakpoint set`, `frame variable`) the marker can follow immediately.
- Batch form: `lldb -b -o "..." -o run ... -- ./prog` (see `scripted-batch.md`).

## Gotchas

- **Windows: the system LLVM lldb may be broken.** A PATH `lldb` from the LLVM installer
  can crash on launch with `unable to find 'python311.dll'` (LLVM installed without the
  Python 3.11 runtime) - the *whole binary* fails, not just scripting. Discovery
  health-checks `lldb --version` and falls back to an IDE-bundled lldb under
  `%LOCALAPPDATA%\Programs\CLion\bin\lldb\win\x64\bin\lldb.exe` (JetBrains CLion ships a
  working lldb 9.0 with its own Python). Android Studio / Rider ship only
  `LLDBFrontend.exe` (JetBrains protocol, not the raw CLI) - not usable.
- **No bare prompt line in pipe mode**: the `(lldb) ` prompt is echoed onto the same line
  as the next command, and after an async stop you see a doubled `(lldb) (lldb)`. Do not
  parse prompts for synchronization; gate on stop-reason content.
- **`--no-use-colors`** to suppress ANSI codes when capturing output.
- **Quitting while stopped hangs**: send `process kill` before `quit`, or just kill the
  process. The driver's `stop` handles this.
- **Loop targets hit the breakpoint repeatedly**: a breakpoint inside a loop stops on every
  iteration; `continue` lands on the next hit, not at program exit.
