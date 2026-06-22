# netcoredbg (.NET managed)

## When this debugger

- **Platform**: Windows, Linux, macOS (all platforms .NET runs on).
- **Language**: .NET managed code (C#, F#, VB) running on the CoreCLR.
- **Build-info fit**: portable PDBs from a Debug build. netcoredbg is **managed-only** - it
  cannot step into native code reached through P/Invoke (the P/Invoke boundary is opaque).
  For the native side see `references/cdb-windows.md`; for crossing the boundary see
  `references/mixed-mode.md`.

## Get the debug build

```bash
dotnet build -c Debug      # emits portable PDBs next to the assemblies
```

A Release build optimizes and strips locals; use `-c Debug`.

## Core command cheatsheet

netcoredbg has two interpreters. Use **CLI** for batch/scripted runs and **MI** for the
persistent driver.

### CLI verbs (batch, `--interpreter=cli`)

| Universal action | CLI command |
|---|---|
| set breakpoint | `break FILE:LINE` |
| run | `run` |
| continue | `continue` |
| step over | `next` |
| step into | `step` |
| step out | `finish` |
| backtrace | `backtrace` |
| read a variable | `print NAME` |

### MI commands (driver, `--interpreter=mi`)

| Universal action | MI command |
|---|---|
| set breakpoint | `-break-insert FILE:LINE` |
| run | `-exec-run` |
| continue | `-exec-continue` |
| step over | `-exec-next` |
| step into | `-exec-step` |
| read a local | `-var-create NAME * NAME` -> parse `value="..."` from `^done` |

Verified CLI batch output (trimmed of library-load noise):

```
Breakpoint 1 at Program.cs:1 --pending, warning: No executable code ...
breakpoint modified,  Breakpoint 1 at .../Program.cs:1
stopped, reason: breakpoint 1 hit, frame={Program...g__Add|0_0() at .../Program.cs:1}
a = 0
stopped, reason: exited, exit-code: 0
```

The "No executable code" warning before the module loads is expected; `breakpoint modified`
confirms the breakpoint resolved once the assembly loaded.

## Driver / adapter note

- `dbg-session.py --debugger netcoredbg` (transport: pipe, MI mode).
- Launch: `netcoredbg --interpreter=mi -- dotnet <app.dll>`.
- **MI is self-framing** - no marker needed. Gate on a parsed `*stopped` record with
  `reason="breakpoint-hit"`, then drain to the next `(gdb)` prompt.
- **Entry-point skip**: after `-exec-run`, netcoredbg fires `*stopped,reason="entry-point-hit"`
  *first*. The driver auto-continues once past it to reach the user breakpoint. (gdb does
  NOT do this - the skip is netcoredbg-specific.)
- **Local reads use `-var-create NAME * NAME`.** `-stack-list-locals` and
  `-data-evaluate-expression` are NOT in netcoredbg's reduced MI subset - do not use them.

## Gotchas

- **CLI mode is unusable over a stdin pipe**: it drops all runtime output after `run`
  (needs a real TTY). The driver uses MI for exactly this reason. CLI is fine for *batch*
  `--command=FILE` runs (see `scripted-batch.md`).
- **ANSI color codes**: netcoredbg colorizes output by default; strip `\x1b\[[0-9;]*m` when
  parsing CLI output.
- **Not preinstalled**: download the release artifact from
  `github.com/Samsung/netcoredbg/releases` (e.g. `netcoredbg-win64.zip`), extract, and put
  it on PATH or pass `--debugger-path` / set `$NETCOREDBG`. Do not hard-code its location.
  See `references/tooling-setup.md`.
- **Managed-only**: stepping into a P/Invoke call shows the managed call site, not the
  native body. That is a netcoredbg limitation, not a bug.
