# Mixed managed/native debugging (C# P/Invoke into C++)

When C# calls into a native DLL through P/Invoke, you may want one debugger to follow
execution across the boundary - step from the managed call site into the native function
with both frame sets visible. This reference is the honest verdict on what is actually
possible, established by a spike against a real dual-toolchain project (file-wizard:
managed C# entry calling `MFTLibNative.dll`).

## The verdict

**No single pipe-driveable debugger cleanly crosses the managed/native boundary.** Each
tool is blind on one side:

| Tool | Managed (C#) | Native (C++) | Pipe-driveable |
|---|---|---|---|
| netcoredbg | yes | **opaque at P/Invoke** | yes (MI) |
| cdb / WinDbg | opaque without SOS | yes | yes |
| lldb | partial (PDB) | yes | yes |
| Visual Studio | yes | yes (true mixed-mode) | **no - interactive only** |

netcoredbg sees the managed call site but cannot step into the native body. cdb/lldb see
native frames but treat managed frames as opaque. Visual Studio does true mixed-mode
debugging but only interactively - it is not driveable over a pipe, so it does not fit the
scripted/driver model this skill uses.

This was confirmed concretely: file-wizard builds cleanly (native `MFTLibNative.dll` + `.pdb`
via MSBuild v143; managed via `dotnet`; the native DLL copied next to the managed entry).
P/Invoke exports are present and bindable. But no scriptable single tool follows the call
through the P/Invoke thunk into native code with symbols on both sides.

## Realistic workarounds

Pick by what you actually need to observe:

1. **Bug is on one side only** (the common case): debug that side with its native tool.
   Managed logic wrong -> netcoredbg (`references/netcoredbg-dotnet.md`). Native crash/wrong
   value -> cdb (`references/cdb-windows.md`) or lldb/gdb (`references/lldb-native.md`,
   `references/gdb-native.md`). Most "mixed-mode" bugs are really single-side bugs; confirm
   which side before reaching for a crossing tool.

2. **Break on the native entry from the native side.** Attach cdb/lldb to the process and
   set a breakpoint on the exported native function (`bp MODULE!Export` in cdb). When the
   managed side calls through, you stop in native code with full native frames - you just do
   not see the managed caller's frames. Inspect the marshalled arguments there.

3. **Two debuggers, one process.** Run netcoredbg for the managed side and cdb/lldb for the
   native side against the same process, correlating by thread manually. Tedious but it
   gives both views.

4. **Visual Studio for true mixed-mode** when you genuinely need to single-step across the
   boundary with both frame sets. This is the only tool that does it, and it is interactive
   - drive it by hand, not through this skill's driver.

## Notes

- The blindness is symmetric and expected, not a configuration bug: netcoredbg is managed
  by design; cdb without SOS is native by design.
- macOS managed/native (.NET P/Invoke into a `.dylib` under lldb) is **(unverified on
  macOS)** - the spike ran on Windows only. Treat any macOS crossing claim as untested.
- If you only need to confirm *that* the boundary was crossed (not step through it), a log
  line on each side is faster than any debugger setup.
