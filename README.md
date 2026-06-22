# using-a-debugger

A Claude skill that teaches agents to drive interactive debuggers (breakpoints,
stepping, reading live program state) instead of falling back to print-debugging.
Cross-platform: Windows, Linux, macOS. First languages: C# (netcoredbg) and
C++ (lldb / gdb / cdb).

Two interaction modes:

- **Scripted / batch** - run a debugger non-interactively, capture output. The
  reliable default, works everywhere.
- **Persistent live session** - `scripts/dbg-session.py`, a client/server driver
  that holds a debugger process alive so the agent can `break`, `run`, `step`,
  and read locals across separate tool calls. Three backend families (MI for
  netcoredbg + gdb, lldb CLI, cdb) behind one uniform verb language.

See `SKILL.md` for the decision logic and `references/` for per-debugger detail.

Development notes (driver tests, evals, support matrix) are filled in as the
build proceeds. Only `SKILL.md`, `scripts/`, `references/`, and `assets/` ship;
`evals/`, `workspace/`, and this README are dev-only.
