# using-a-debugger

A Claude skill that teaches agents to drive interactive debuggers (breakpoints, stepping,
reading live program state) instead of falling back to print-debugging. Cross-platform:
Windows, Linux, macOS. Languages: C# (netcoredbg) and native C/C++ (lldb / gdb / cdb).

See `SKILL.md` for the decision logic and `references/` for per-debugger detail.

## Prerequisites (external tools the installer does NOT install)

The skill installer ships only this skill's files (`SKILL.md`, `scripts/`, `references/`). The
actual debugger binaries are **runtime prerequisites you install separately** -
`scripts/setup-debuggers.py` installs them for you (see [Installing the debuggers](#installing-the-debuggers)),
and `references/tooling-setup.md` is the authoritative detect-then-install guide. Quick summary:

| Debugger | Install | Notes |
|---|---|---|
| netcoredbg (.NET) | Download release zip from `github.com/Samsung/netcoredbg/releases`; put on PATH or set `$NETCOREDBG` | No package manager. Needed for C#/Unity. |
| gdb (native, Linux) | distro package (`apt`/`dnf`) | On Windows a MinGW gdb (e.g. Strawberry Perl) works for DWARF builds. |
| lldb (native) | macOS: Xcode CLT; Linux: distro; Windows: `winget install LLVM.LLVM` | **Windows caveat below.** |
| cdb (native, Windows) | Windows SDK "Debugging Tools for Windows" feature | Lands under `%ProgramFiles(x86)%\Windows Kits\10\Debuggers\x64\`; the driver discovers it there even when it is not on PATH. |

The driver (`scripts/dbg-session.py`) also needs **Python 3** on PATH.

> **Windows lldb caveat.** The LLVM-installer `lldb.exe` needs a matching **Python 3.11**
> runtime (it embeds CPython); without `python311.dll` reachable it crashes on launch with
> `unable to find 'python311.dll'`. Even with Python 3.11 present, the persistent-session
> driver's lldb backend cannot drive the LLVM Windows build: it synchronizes on a
> `script print(<marker>)` token, but that build buffers embedded-Python `print()` output and
> only flushes it on the *next* command, so each `send` times out. Use **scripted/batch** mode
> for lldb on Windows, prefer an IDE-bundled lldb (e.g. CLion's) for the live driver, or use
> cdb for MSVC/clang-cl PDB builds. gdb and netcoredbg drive cleanly on Windows.

## Two interaction modes

- **Scripted / batch** - run a debugger non-interactively, capture output. The reliable
  default; use it when the breakpoint location is known. See `references/scripted-batch.md`.
- **Persistent live session** - `scripts/dbg-session.py`, a client/server driver that holds
  a debugger process alive so the agent can `break`, `run`, `step`, and read locals across
  separate tool calls. Use it when you do not yet know where the bug is and must follow
  state interactively. See `references/interactive-sessions.md`.

## Support matrix

| Debugger | Language | Platforms | Backend family | Transport |
|---|---|---|---|---|
| netcoredbg | .NET (C#/F#/VB) | Windows, Linux, macOS | MI (self-framing) | pipe |
| gdb | native C/C++ | Linux (primary) | MI (self-framing) | PTY on Unix |
| lldb | native C/C++ | macOS, Linux, Windows (clang) | CLI + content-gated marker | pipe |
| cdb | native C/C++ | Windows (MSVC/clang-cl PDB) | CLI + `.echo` marker | pipe |

The driver exposes one **uniform verb language** across all four - `break FILE:LINE`, `run`,
`continue`, `step`, `stepin`, `local NAME`, `bt`, `raw NATIVE...` - and each backend
translates to its debugger's native protocol. The three backend families exist because the
spike proved their I/O models genuinely differ (MI is self-framing; lldb delivers stops
asynchronously and needs content-based gating; cdb is synchronous).

### Mixed managed/native verdict

No single pipe-driveable debugger cleanly steps across the C# managed / native (P/Invoke)
boundary - netcoredbg is managed-only, cdb/lldb treat managed frames as opaque, and Visual
Studio does true mixed-mode but only interactively. `references/mixed-mode.md` gives the
honest limits and the realistic workarounds.

## Installing the debuggers

`scripts/setup-debuggers.py` ensures the debuggers this skill drives are present. It is
idempotent and platform-gated (Linux: netcoredbg/gdb/lldb; macOS: netcoredbg/lldb; Windows:
netcoredbg/cdb/lldb), reuses `discovery.find_debugger` to skip anything already discoverable,
and downloads netcoredbg (no package-manager distribution) into a canonical per-user dir that
discovery also checks - so it is found without editing `PATH`.

```bash
python scripts/setup-debuggers.py            # ensure every relevant debugger is present
python scripts/setup-debuggers.py --dry-run  # show what it would install, change nothing
python scripts/setup-debuggers.py --only netcoredbg,lldb
```

Two paths cannot run fully unattended and are reported as `manual` with the exact command:
password-required `sudo` (Linux) and `xcode-select --install` (macOS GUI installer). The
umbrella skills installer can chain this after a skill install with
`install-skills.sh --setup-debuggers` (or `.bat`). See `references/tooling-setup.md` for the
manual per-platform playbook.

## Running the driver locally

```bash
# start a session (binary is auto-discovered; override with --debugger-path)
python scripts/dbg-session.py start --debugger lldb --session demo -- ./hello

# drive it - each send is a separate process; state persists in the server
python scripts/dbg-session.py send --session demo "break hello.cpp:3"
python scripts/dbg-session.py send --session demo "run"
python scripts/dbg-session.py send --session demo "local a"
python scripts/dbg-session.py stop --session demo
```

## Driver tests

The driver has a stdlib-only pytest suite under `scripts/dbgsession/`. Unit tests (transport,
MI parser, discovery) run everywhere; integration tests are gated with `skipif` on the
relevant debugger/compiler being present.

```bash
cd scripts/dbgsession && python -m pytest -q
```

On a machine with lldb + cdb + clang installed, expect the lldb and cdb integration tests to
run; netcoredbg and gdb legs skip unless those tools are on PATH (set `$NETCOREDBG` /
`$GDB`, or run the gdb leg on Linux).

## Evals

Decision-surface evals (single-turn, adapted from the `fast-tests` harness) live in
`evals/`. They check that the skill steers the agent toward a hypothesis-driven debugger
workflow, the right mode, and the right debugger - and away from print-debugging an obvious
one-line bug.

```bash
python evals/run.py  --evals evals/evals.json --skill-md SKILL.md --output-dir workspace/eval-out
python evals/grade.py --responses-dir workspace/eval-out --evals evals/evals.json
```

## What ships

Only `SKILL.md`, `scripts/`, `references/`, and `assets/` are installed. `evals/`,
`workspace/`, and this README are dev-only (excluded by the installer allowlist).
