# Persistent / interactive sessions

When you do not yet know where the bug is, you need to keep the debuggee alive and probe
it step by step: set a breakpoint, run, look, step, read a value, decide the next move
based on what you saw. A debugger process cannot survive between separate agent tool calls
on its own, so this skill ships a driver - `scripts/dbg-session.py` - that holds the
debuggee in a long-lived server process and lets each tool call talk to it.

Start with scripted/batch (`references/scripted-batch.md`). Escalate to a live session only
for genuine exploration.

## The model

```
dbg-session.py start ...   ->  spawns a detached server process that owns ONE debugger
dbg-session.py send  ...   ->  short-lived client; sends one verb, prints the reply
dbg-session.py stop  ...   ->  tells the server to kill the debuggee and exit
```

The server keeps the debugger (and the stopped program) alive between `send` calls, so the
debuggee's state - breakpoints, the current frame, variable values - persists across what
are, to you, completely separate tool invocations. State lives under the OS temp dir at
`dbg-session/<session-name>/` (a `port` file the client reads to find the server).

You speak a **uniform verb language**, the same for every debugger; each backend translates
to its native commands:

| Verb | Meaning |
|---|---|
| `break FILE:LINE` | set a breakpoint |
| `run` | start the program (stops at the first breakpoint) |
| `continue` | resume to the next stop |
| `step` | step over one source line |
| `stepin` | step into a call |
| `local NAME` | read the value of a local/argument |
| `bt` | backtrace |
| `raw NATIVE...` | send a raw debugger-native command (escape hatch) |

## CLI

```
dbg-session.py start --debugger {netcoredbg|gdb|lldb|cdb} --session NAME [--debugger-path PATH] -- PROGRAM [ARGS...]
dbg-session.py send  --session NAME "VERB ..."
dbg-session.py stop  --session NAME
```

- **`PROGRAM` is what the OS launches, not your source or assembly.** Native debuggers
  (gdb/lldb/cdb) take the compiled binary directly: `-- ./hello`, `-- app.exe`. **netcoredbg
  takes the .NET host with your assembly as its argument: `-- dotnet App.dll`** - NOT
  `-- App.dll`. Passing the bare `.dll` leaves the breakpoint unresolved ("No executable
  code ...") and the next `run` hangs. See `references/netcoredbg-dotnet.md`.
- The transport is chosen automatically per debugger (lldb/cdb/netcoredbg use a pipe; gdb
  uses a PTY on Unix). You do not pick it.
- The debugger binary is resolved by `discovery.find_debugger` (PATH, env overrides like
  `$NETCOREDBG` / `$LLDB` / `$CDB`, then platform install roots, with a health-check for
  lldb). Pass `--debugger-path` to override, e.g. for a netcoredbg you unzipped to a
  scratch dir.
- `--session NAME` namespaces the session, so you can run several at once (`bug-a`,
  `bug-b`) without collision.

## Worked transcript

Driving the `hello.cpp` target (the `add(a, b)` example from `scripted-batch.md`) through a
live lldb session. Each block is a *separate* `dbg-session.py` invocation - a separate
agent tool call:

```
$ dbg-session.py start --debugger lldb --session demo -- ./hello

$ dbg-session.py send --session demo "break hello.cpp:3"
Breakpoint 1: where = hello`add(int,int) + 12 at hello.cpp:3, address = 0x...

$ dbg-session.py send --session demo "run"
Process 41816 stopped
* thread #1, stop reason = breakpoint 1.1
    frame #0: 0x... hello`add(a=0, b=0) at hello.cpp:3

$ dbg-session.py send --session demo "local a"
0

$ dbg-session.py send --session demo "continue"
Process 41816 stopped
* thread #1, stop reason = breakpoint 1.1
    frame #0: 0x... hello`add(a=1, b=2) at hello.cpp:3

$ dbg-session.py send --session demo "local a"
1                                  # <- state persisted: a is 1 on the second hit

$ dbg-session.py send --session demo "bt"
* thread #1, stop reason = breakpoint 1.1
  * frame #0: 0x... hello`add(a=1, b=2) at hello.cpp:3
    frame #1: 0x... hello`main() at hello.cpp:8

$ dbg-session.py stop --session demo
stopped
```

The two `local a` reads returning `0` then `1` across separate processes are the whole
point: the server held the debuggee between calls. Execution verbs (`run`, `continue`, `bt`)
return the debugger's native stop text; `local NAME` returns just the parsed value.

To mutate state mid-session, use `raw` with the debugger's native expression command, e.g.
`raw expression sum = -1` (lldb) or `raw print sum = -1` (gdb).

## When to escalate vs stay scripted

Start scripted. Escalate to a live session when:

- You do not yet know where the bug is and must follow state interactively.
- The decision about *where to look next* depends on a value you just read.
- You want to mutate state and observe the consequence without rebuilding.

Stay scripted when the breakpoint location is known, you want a reproducible one-shot
capture, or you are in CI.

## Recovery and troubleshooting

- **Wedged session**: `stop --session NAME`, then `start` again. The server kills the
  debuggee on stop; if a `send` hangs, the server is gone or the debuggee deadlocked - stop
  and restart.
- **Stale port file**: `start` removes any old `port` file before spawning, so a crashed
  prior server does not poison a fresh start under the same name.
- **lldb on Windows**: the system LLVM `lldb` may be broken (missing `python311.dll`);
  discovery health-checks it and falls back to an IDE-bundled lldb. See
  `references/lldb-native.md`.
- **netcoredbg over the driver**: only `--interpreter=mi` is pipe-viable; the driver
  already uses MI. The CLI interpreter drops output over a pipe (it is fine for *batch*
  `--command` runs - see `scripted-batch.md`).
- **Color codes / CRLF in output**: lldb prints a doubled `(lldb) (lldb)` prompt after an
  async stop and Windows CRLF line endings; netcoredbg emits ANSI color codes. The backends
  strip these, but if you parse `raw` output yourself, account for them.
