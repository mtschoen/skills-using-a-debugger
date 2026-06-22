# gdb (native C/C++ on Linux)

## When this debugger

- **Platform**: Linux (primary). Also macOS (less common than lldb) and MinGW on Windows.
- **Language**: native C/C++ (and others) compiled with DWARF debug info.
- **Build-info fit**: DWARF (`-g`). gdb does not read MSVC PDBs well - on Windows-native
  MSVC binaries use cdb (`references/cdb-windows.md`). The clean persistent C++ story is
  gdb on Linux.

## Get the debug build

```bash
g++ -g -O0 -o hello hello.cpp      # or: clang++ -g -O0 -o hello hello.cpp
```

## Core command cheatsheet

| Universal action | gdb command | short |
|---|---|---|
| set breakpoint | `break FILE:LINE` | `b FILE:LINE` |
| break on function | `break FUNC` | `b FUNC` |
| run | `run` | `r` |
| continue | `continue` | `c` |
| step over | `next` | `n` |
| step into | `step` | `s` |
| step out | `finish` | - |
| backtrace | `backtrace` | `bt` |
| read all locals | `info locals` | - |
| read arguments | `info args` | - |
| read one var | `print NAME` | `p NAME` |
| mutate a variable | `set var sum = -1` | - |
| read memory | `x/FMT ADDR` | - |
| break on thrown exception | `catch throw` (or `catch throw <regexp>`) | - |

Verified stop + locals output (GNU gdb 17.2, Linux):

```
Breakpoint 1, add (a=0, b=0) at hello.cpp:3
3	    int sum = a + b;
(gdb) info args
a = 0
b = 0
(gdb) info locals
sum = 32767      # uninitialized: line 3 has not executed yet
```

## Driver / adapter note

- `dbg-session.py --debugger gdb`.
- **Transport: PTY on Unix.** gdb's CLI buffers its `(gdb) ` prompt when stdout is not a
  tty and deadlocks on a plain pipe (`stdbuf` does not fix it), so the driver runs it under
  `pty.openpty()`. PTY echoes input and adds CRLF/ANSI - the transport strips these.
- **MI mode for the driver**: `gdb --interpreter=mi2`. MI is self-framing
  (`^done`/`^error` for sync results, `*stopped` for async stops, `(gdb)` prompt after each
  result), so no marker is needed - the backend gates on a parsed `*stopped` record and
  drains to the next `(gdb)`. The hand-rolled MI parser (`miparse.py`) handles this.
- CLI stop handling is **synchronous** (unlike lldb): `run`/`continue`/`step`/`next` block
  until the stop, so a bare `echo TOKEN\n` after an execution command always captures the
  stop banner if you drive the CLI directly.
- Batch form: `gdb -batch -ex "break FILE:LINE" -ex run -ex "info locals" --args ./prog`
  (see `scripted-batch.md`).

## Gotchas

- **PTY echo**: command lines you write are echoed back on the PTY; strip them when parsing.
- **CRLF + ANSI** on the PTY: strip `\r` and `\x1b\[[0-9;]*[a-zA-Z]`.
- **`quit` on non-tty input auto-answers Y** to the "kill the inferior?" prompt - clean
  enough for a driver, but do not rely on interactive confirmation.
- **MI subset differs from CLI**: drive the driver with MI commands (`-break-insert`,
  `-exec-run`, `-exec-continue`, `-exec-next`, `-exec-step`), not CLI verbs.
- lldb is not always installed alongside gdb on Linux; do not assume both are present.
