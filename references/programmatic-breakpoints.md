# Trigger a breakpoint from code

Sometimes the right place to stop is one the debugger cannot easily reach from the
outside:

- The condition that distinguishes the bad case is **expressible only in code** - it
  depends on several locals, a computed predicate, or the Nth-and-only-the-Nth iteration -
  and a conditional line breakpoint expression would be fragile or impossible to type.
- The process is **launched indirectly** (by a test runner, a parent process, a script, a
  service host), so you cannot reliably attach a debugger *before* the moment of interest.
- A plain line breakpoint would **stop on every iteration** of a hot path when you only
  care about one specific entry.

In these cases you put the breakpoint *in the source*: a one-line call that raises a
debugger trap when execution reaches it. Guard it with the real condition, rebuild, and run
under (or attach) the debugger - it halts exactly there with full live state.

This is a **source edit**: rebuild is required, and you must remove it (or guard it so it is
inert) before the code ships. Treat it like a temporary breakpoint that happens to live in
the file.

## Per language

| Language | Call | Notes |
|---|---|---|
| C# / .NET | `System.Diagnostics.Debugger.Break()` | Breaks into an **already-attached** debugger. If none is attached it reports to Windows Error Reporting (since .NET Framework 4) rather than reliably launching one - so pre-attach, or use `Launch()`. |
| C# / .NET | `System.Diagnostics.Debugger.Launch()` | Forces the "attach a debugger?" prompt if none is attached. This is the one to use when the process is spawned by a harness you cannot pre-attach to. |
| C# / .NET | `if (System.Diagnostics.Debugger.IsAttached) Debugger.Break();` | Guard so the call is inert in production / CI where no debugger is present. |
| C / C++ (MSVC) | `__debugbreak()` | Intrinsic; emits `int 3`. Preferred on Windows over the older Win32 `DebugBreak()`. |
| C / C++ (Win32) | `DebugBreak()` | Win32 API equivalent; works across MSVC and MinGW. |
| C / C++ (Clang) | `__builtin_debugtrap()` | Emits `int3` on x86; resumable, the debugger stops cleanly. |
| C / C++ (POSIX) | `raise(SIGTRAP);` | `#include <signal.h>`. gdb/lldb stop on the signal; resumable. The portable Unix choice. |
| C / C++ (x86 asm) | `__asm__ volatile("int3");` | The raw software-breakpoint instruction; last resort when no intrinsic is available. |
| C / C++ (C++26) | `std::breakpoint()` / `std::breakpoint_if_debugging()` | Standardized in C++26 (`<debugging>`); the latter no-ops when no debugger is present. |
| Python | `breakpoint()` | Built in since 3.7; drops into `pdb` (or `$PYTHONBREAKPOINT`'s hook). |

Avoid `__builtin_trap()` (GCC/Clang) for this purpose: on x86 it emits `ud2`, which raises
`SIGILL` and **aborts** the process rather than giving you a resumable stop. Use
`__builtin_debugtrap()` or `raise(SIGTRAP)` instead.

## Worked example (.NET): stop only on the one bad record

`InvoiceService.TotalFor` throws for exactly one customer id in a long batch, and the
distinguishing condition is "the customer exists but its `Invoice` is null" - awkward to type
as a conditional breakpoint, trivial in code:

```csharp
public decimal TotalFor(string customerId)
{
    Customer c = _customers.GetValueOrDefault(customerId);
    if (System.Diagnostics.Debugger.IsAttached && c is { Invoice: null })
        System.Diagnostics.Debugger.Break();   // stops here only for the bad id
    decimal total = 0;
    foreach (var line in c.Invoice.Lines)
        total += line.Amount;
    return total;
}
```

Rebuild (`dotnet build -c Debug`), run under netcoredbg, and it halts on the guarded line for
the offending id only - `customerId` and `c` are live in scope, so you see exactly which id
and why `Invoice` is null. Remove the two lines once you have the answer.

If the process is started by a test runner you cannot attach to in time, swap
`Debugger.Break()` for `Debugger.Launch()` - it will raise the attach prompt at that point.

## Worked example (native): stop on the Nth record

`parse_value` is called once per argv record; the segfault is on one specific record and a
breakpoint on the function stops on every one. Drop a guarded trap in instead:

```cpp
#include <csignal>   // or <intrin.h> on MSVC for __debugbreak()

const char* parse_value(const char* record, int* out_len) {
    const char* eq = strchr(record, '=');
    if (eq == nullptr) raise(SIGTRAP);   // stop exactly on the record with no '='
    const char* value = eq + 1;
    *out_len = (int)strlen(value);
    return value;
}
```

Under gdb/lldb the `raise(SIGTRAP)` stops you on that line with `record` in scope; on Windows
build use `__debugbreak()` instead. Resume or remove once localized.

## When NOT to use it

- If a **conditional line breakpoint** expresses the condition cleanly
  (`break FILE:LINE if x == 5`), prefer it - no source edit, no rebuild. See
  `references/scripted-batch.md` and `references/interactive-sessions.md`.
- If you already know the exact line and there is no awkward condition, a plain breakpoint is
  simpler.
- Never leave the call in shipped code. Guard managed calls with `Debugger.IsAttached`; delete
  native traps. An unguarded `Debugger.Break()`/`raise(SIGTRAP)` in production crashes or hangs
  for real users.
