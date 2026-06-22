# Break on the exception, not a guessed line

When the bug is an exception with no clear origin - a `NullReferenceException` from a
deep stack, a C++ `throw` you cannot localize - do NOT hunt for a line breakpoint. Tell
the debugger to **stop the moment the exception is thrown** (a first-chance / throw-stage
breakpoint). It halts you *at the throw site* with the live stack and locals, so the null
reference (or bad argument) is right there in frame #0/#1. This is usually the fastest path
to an exception bug, and it is the first thing to reach for when you would otherwise be
guessing where to break.

Two stages matter:

- **throw / first-chance**: stop when the exception is raised, before any `catch` runs. This
  is what pins the origin. Use it to find where the bad value comes from.
- **unhandled**: stop only if nothing catches it. Use it when first-chance is too noisy
  (a codebase that throws-and-catches as control flow) and you only care about the fatal one.

## Per-debugger commands (verified)

| Debugger | Break on every throw | Scope to a type | Only unhandled |
|---|---|---|---|
| netcoredbg (CLI) | `catch throw *` | `catch throw System.NullReferenceException` | `catch unhandled *` |
| netcoredbg (MI / driver) | `-break-exception-insert throw *` | `-break-exception-insert throw System.NullReferenceException` | `-break-exception-insert unhandled *` |
| gdb | `catch throw` | `catch throw <regexp>` | (use `catch catch` for catch-site) |
| lldb | `break set -E c++` | - | - |
| cdb | `sxe eh` (native C++) / `sxe clr` (managed) | - | (default is second-chance) |

netcoredbg's full grammar (from its own usage string):
`catch [-mda|-native] <unhandled|user-unhandled|throw|throw+user-unhandled> *|<Exception names>`

## Worked example: a NullReferenceException with no clear origin (.NET)

This is the managed case where break-on-exception shines. Instead of reading the stack and
guessing which reference is null, attach and let the NRE happen - the debugger stops you on
the throwing line with the null in scope.

Program under debug (`s` is null at line 3):

```csharp
string s = null;
System.Console.WriteLine("before");
int len = s.Length;            // line 3 - NullReferenceException
```

### Via the live driver (MI)

```
$ dbg-session.py start --debugger netcoredbg --session nre -- dotnet App.dll
$ dbg-session.py send --session nre "raw -break-exception-insert throw *"
^done,bkpt={number="1"}
$ dbg-session.py send --session nre "run"
*stopped reason="exception-received" ... frame={Program.<Main>$() at Program.cs:3}
$ dbg-session.py send --session nre "local s"
null                           # the null reference, caught AT the throw - no line guess
$ dbg-session.py stop --session nre
```

The MI command goes through the `raw` verb; the backend's `*stopped` gate handles the
`reason="exception-received"` stop the same as a breakpoint stop.

### Via scripted/batch (CLI)

`script.txt`:
```
catch throw *
run
```

```bash
netcoredbg --interpreter=cli --command=script.txt -- dotnet App.dll
```

Real output (trimmed):
```
^done, Catchpoint 1 (throw)
stopped, reason: exception received, name: System.NullReferenceException,
  exception: Object reference not set to an instance of an object.,
  stage: throw, category: clr, frame={Program.<Main>$() at Program.cs:3}
```

`name`, the message, and the throwing `frame` are all reported at the stop. `stage: throw`
confirms it is the first-chance break, not the final unhandled one.

## Native worked example (gdb)

```bash
gdb -batch -ex "catch throw" -ex run -ex bt --args ./prog
```

Real output (Linux):
```
Catchpoint 1 (exception thrown), 0x... in __cxa_throw () from /usr/lib/libstdc++.so.6
#0  0x... in __cxa_throw () from /usr/lib/libstdc++.so.6
#1  0x... in risky (x=-5) at th.cpp:3      # <- the real throw site, with the bad arg
```

gdb stops inside `__cxa_throw`; `bt` walks one frame up to your code (`risky (x=-5)`),
showing both the location and the argument that triggered the throw.

## Platform gotcha: lldb on Windows

`break set -E c++` hooks the Itanium ABI `__cxa_throw`, which is present on Linux/macOS but
**not** in a Windows MSVC-ABI binary (clang++/clang-cl on Windows). There the breakpoint
stays pending/unbound:

```
(lldb) break set -E c++
Breakpoint 1: no locations (pending).
```

But lldb still stops on the Windows structured exception that a C++ `throw` raises:

```
stop reason = Exception 0xe06d7363 encountered at address 0x...
```

`0xe06d7363` is the MSVC C++ exception code ("msc"). So on Windows you still land at the
throw, just via SEH rather than the named C++ breakpoint. On Linux/macOS, `break set -E c++`
binds and works as written. cdb's `sxe eh` keys off the same `e06d7363` code from the native
side.

## When NOT to use it

- First-chance breaks fire on **every** throw. In a codebase that uses exceptions as control
  flow, `catch throw *` stops constantly - scope to a type (`catch throw <Type>`) or switch
  to `unhandled`.
- If you already know the throwing line, a plain line breakpoint there is simpler.
- This finds *where* an exception is thrown. *Why* the state got that way is still the
  hypothesis loop (`superpowers:systematic-debugging`) - read the locals at the throw and
  work backward.
