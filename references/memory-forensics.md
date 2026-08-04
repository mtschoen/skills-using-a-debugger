# Memory forensics: heap state, GC roots, and leaks (.NET, with native notes)

For questions about *state* rather than *control flow*: what is on the heap, why an
object is still alive, whether an AssemblyLoadContext / plugin / cache actually got
collected. No breakpoints involved - and usually no live session either.

## Decision: core dump first, live attach only if you must

| | Offline dump (`createdump` + `dotnet-dump analyze`) | Live attach (lldb + SOS) |
|---|---|---|
| Target impact | Frozen for seconds while dumping, then keeps running | Frozen the whole session |
| Large debug binaries | Immune to symbol-load cost | lldb attach can hang 10+ min on DWARF preload |
| Repeatability | Query the same snapshot as many times as you like | State changes under you |
| Needs | The runtime's own `createdump` binary | matching lldb + SOS plugin |

Reach for live attach only when you need the state to *move* (step, continue, watch) -
that is the main skill's territory. For everything else, dump.

## The offline workflow (.NET / CoreCLR)

1. **Find the real PID.** `pgrep -f Name | head -1` is a trap - when you launched the
   process from a shell script or tool wrapper, it matches the wrapper first. Use
   `pgrep -x BinaryName`, or verify with `ps -o pid,comm -p PID` before dumping.
2. **Snapshot**: `createdump` ships in the runtime directory of every .NET install
   (`shared/Microsoft.NETCore.App/<ver>/createdump`):

   ```bash
   <runtime-dir>/createdump --withheap -f /tmp/proc.dmp <PID>
   ```

   `--withheap` includes the GC heap (that is the point). Expect roughly the process's
   resident size on disk; an 18 GB process dumps in under a minute. `dotnet-dump collect`
   is the alternative when the target has the diagnostic IPC port enabled; `createdump`
   works regardless.
3. **Analyze** (`dotnet tool install -g dotnet-dump` once):

   ```bash
   dotnet-dump analyze /tmp/proc.dmp -c "dumpheap -stat" -c "exit"          # heap census
   dotnet-dump analyze /tmp/proc.dmp -c "dumpheap -type Some.Type" -c "exit"
   dotnet-dump analyze /tmp/proc.dmp -c "gcroot <objAddr>" -c "exit"        # WHY is it alive
   dotnet-dump analyze /tmp/proc.dmp -c "dumpobj <objAddr>" -c "exit"       # field-level view
   dotnet-dump analyze /tmp/proc.dmp -c "eeheap -loader" -c "exit"          # per-ALC loader heaps
   ```

   SOS reads managed state through the DAC (`libmscordaccore`), which ships next to the
   runtime - **no native symbols are needed**, release runtimes work fine.

## Reading `gcroot` at scale

On a real process `gcroot` can print hundreds of thousands of lines. Do not read it -
mine it:

- Each root is a handle/stack entry followed by an indented `->` chain ending at your
  target. The **penultimate hop** is the object that actually pins the target - count
  those: `grep -B1 "TargetType *$" out.txt | grep -- "->" | awk '{print $NF}' | sort |
  uniq -c | sort -rn`.
- The root *kind* matters: `(strong handle)` = native code / GCHandle owns it;
  `(pinned handle)` = statics tables and pinned buffers; thread entries = a live stack
  frame. A numeric kind SOS cannot name (e.g. `(10)`) means the runtime is newer than
  your SOS or carries custom handle types - treat those with suspicion rather than
  trust.
- Sections for multiple `gcroot` targets run in one `analyze` invocation are separated
  by their `Found N unique roots.` lines.

## Leak verification without a debugger

The cheapest leak check is in-process and belongs in your test/probe code, not the
debugger: hold a `WeakReference` (`trackResurrection: true`) to the suspect object, drop
all strong references, then loop `GC.Collect(); GC.WaitForPendingFinalizers();` and
check `IsAlive`. Unloadable resources (collectible AssemblyLoadContexts especially) need
**at least two** full GC + finalizer cycles by design - one cycle proving "still alive"
proves nothing. Ten cycles still alive = rooted; then take a dump and `gcroot` it.

## If you must attach live to something huge

Before `process attach`, turn off symbol preloading or lldb may appear to hang
indefinitely while indexing DWARF for every module:

```text
settings set target.preload-symbols false
settings set symbols.load-on-demand true
process attach --pid <PID>
```

SOS auto-loads via `~/.lldbinit` after `dotnet-sos install`. A batch attach that prints
only the SOS banner and nothing else usually means you attached to the wrong process
(see the PID trap above) - not that SOS is broken.

## Native-side notes

- Native heap questions (malloc'd memory, `VirtualAlloc` regions) are outside SOS:
  use `vmmap`/`heap` (macOS), `pmap`/massif (Linux), `!heap` in cdb (Windows).
- A native core (`ulimit -c` / `coredumpctl` / `kill -ABRT`) opened in gdb/lldb gives
  you stacks and globals of every thread - same "dump over live attach" logic applies.
