---
name: using-a-debugger
description: "Use when a bug needs more than print statements - set breakpoints, step, and read live program state in C#/C++ (and similar native/managed runtimes). Covers scripted/batch debugging and a persistent live-session driver, cross-platform (lldb/gdb/cdb/netcoredbg). Triggers: a crash or wrong value you cannot localize by reading code, an exception with no clear origin, or wanting to inspect memory/locals at a specific point."
---

# Using a Debugger

A debugger lets you stop a running program at a chosen point and read its real state -
locals, arguments, the call stack, memory - instead of guessing from the source or
sprinkling print statements. Reach for it when reading code and adding logs is not
converging.

## When to use

- A crash or wrong value you cannot localize by reading the code.
- An exception with no clear origin.
- You need to inspect locals, arguments, or memory at a specific point in execution.
- Print-debugging would mean many rebuild-and-rerun cycles to bisect the state.

## When NOT to use

- A one-line, obvious bug a single log line settles - just fix it.
- This is the *tooling* arm, not the *process*. The thinking - reproduce, form a
  hypothesis, isolate - belongs to `superpowers:systematic-debugging`. Use that to decide
  *what* to investigate; use this skill to *observe* it. Do not aimlessly single-step.

## The loop

The debugger serves a hypothesis. Every breakpoint should be able to confirm or refute one:

1. Form a hypothesis about what is wrong (via `superpowers:systematic-debugging`).
2. Pick the breakpoint that would confirm or refute it - the line where the suspect state
   should be observable.
3. Set it, run, read the state.
4. Step only as far as the hypothesis needs; read state again.
5. Conclude: hypothesis confirmed (now fix) or refuted (form the next one).

If you find yourself stepping without a question in mind, stop and go back to step 1.

## Break on the exception

When the bug is an exception with no clear origin (a `NullReferenceException` from a deep
stack, a C++ `throw` you cannot localize), do not guess a line breakpoint. Tell the debugger
to stop the moment the exception is thrown - it halts you at the throw site with the null (or
bad argument) live in scope. This is the first move for "exception, no clear origin." Per
debugger: netcoredbg `catch throw *`, gdb `catch throw`, lldb `break set -E c++`, cdb
`sxe eh`/`sxe clr`. Full grammar, stages (throw vs unhandled), a worked NRE example, and the
Windows lldb nuance are in `references/break-on-exception.md`.

## Mode decision

**Start scripted.** Feed the debugger a fixed command list, run it non-interactively, read
the captured output. Reliable, reproducible, CI-friendly. Use it whenever the breakpoint
location is known. See `references/scripted-batch.md`.

**Escalate to a live session** only when you do not yet know where the bug is and must
follow state interactively - where you look next depends on what you just read. The shipped
driver (`scripts/dbg-session.py`) holds the debuggee alive across separate tool calls. See
`references/interactive-sessions.md`.

## Debugger selection

Pick by language and platform (build a debug build first - symbols are required):

| Language | Platform | Debugger | Reference |
|---|---|---|---|
| .NET (C#/F#/VB) | any | netcoredbg | `references/netcoredbg-dotnet.md` |
| native C/C++ | Linux | gdb (or lldb) | `references/gdb-native.md` |
| native C/C++ | macOS | lldb | `references/lldb-native.md` |
| native C/C++ | Windows (MSVC/clang-cl PDB) | cdb | `references/cdb-windows.md` |
| native C/C++ | Windows (clang/DWARF) | lldb (IDE-bundled) | `references/lldb-native.md` |

Not installed? Do not give up - detect then install per `references/tooling-setup.md`.

## Mixed managed/native (C# P/Invoke into C++)

No single pipe-driveable tool cleanly crosses the managed/native boundary. For what is and
is not possible per platform, and the realistic workarounds, see `references/mixed-mode.md`.

## The driver

```
scripts/dbg-session.py start --debugger {netcoredbg|gdb|lldb|cdb} --session NAME -- PROGRAM [ARGS...]
scripts/dbg-session.py send  --session NAME "VERB ..."     # break FILE:LINE | run | continue | step | stepin | local NAME | bt | raw ...
scripts/dbg-session.py stop  --session NAME
```

One uniform verb language across all four debuggers; the server keeps the debuggee alive
between calls. Details in `references/interactive-sessions.md`.
