# Scripted / batch debugging

The reliable default. You feed the debugger a fixed list of commands, it runs them
non-interactively, and you read the captured output. No persistent process, no state to
manage across tool calls. Use this whenever you already know where you want to look:
a known breakpoint location, a one-shot "what are the locals at line N" capture, a
reproduction you want recorded, or anything that runs in CI.

Escalate to a live session (`references/interactive-sessions.md`) only when you do *not*
yet know where the bug is and need to follow state interactively.

All examples below were run against this C++ target (`hello.cpp`):

```cpp
#include <cstdio>
int add(int a, int b) {
    int sum = a + b;   // line 3 - breakpoint target
    return sum;
}
int main() {
    for (int i = 0; i < 3; ++i) {
        int r = add(i, i * 2);
        printf("r=%d\n", r);
    }
    return 0;
}
```

## lldb (one `-o` per command)

```bash
lldb --no-use-colors -b \
  -o "breakpoint set -f hello.cpp -l 3" \
  -o run \
  -o "frame variable" \
  -o continue \
  -o "process kill" \
  -- ./hello
```

`-b` is batch mode (exit after the commands), each `-o` is one command, and everything
after `--` is the program plus its arguments. The `-s scriptfile` form takes the same
commands from a file instead of repeated `-o` flags. Real output:

```
(lldb) breakpoint set -f hello.cpp -l 3
Breakpoint 1: where = hello`add(int,int) + 12 at hello.cpp:3, address = 0x...
(lldb) run
Process 53172 stopped
* thread #1, name = 'Main Thread', stop reason = breakpoint 1.1
    frame #0: 0x... hello`add(a=0, b=0) at hello.cpp:3
   3   	    int sum = a + b;   // line 3 - breakpoint target
(lldb) frame variable
(int) a = 0
(int) b = 0
(int) sum = 0
```

Note `process kill` before exit: a bare exit while the process is stopped at a breakpoint
can hang for a few seconds waiting on the inferior.

## gdb (one `-ex` per command)

```bash
gdb -batch \
  -ex "break hello.cpp:3" \
  -ex run \
  -ex "info locals" \
  -ex "info args" \
  -ex continue \
  --args ./hello
```

`-batch` runs the commands and exits; each `-ex` is one command; `--args` passes the
program and its arguments. Use `info args` for parameters and `info locals` for locals.
Real output (Linux, GNU gdb 17.2):

```
Breakpoint 1 at 0x1143: file hello.cpp, line 3.
Breakpoint 1, add (a=0, b=0) at hello.cpp:3
3	    int sum = a + b;
sum = 32767          # uninitialized - line 3 has not executed yet
a = 0
b = 0
```

## cdb (commands from a script file)

cdb has no per-command flag; put the commands in a file and pass `-cf`:

`script.txt`:
```
bp `hello.cpp:3`
g
dv
q
```

```bash
cdb -cf script.txt hello.exe
```

`bp \`file:line\`` sets the breakpoint (the backticks are cdb's source-line syntax),
`g` runs/continues, `dv` dumps local variables, `q` quits. Real output:

```
0:000> bp `hello.cpp:3`
0:000> g
Breakpoint 0 hit
hello!add+0xc:
00007ff6`3f97100c 8b442408        mov     eax,dword ptr [rsp+8]
0:000> dv
              a = 0n0
              b = 0n0
            sum = 0n0
```

cdb prints integers in `0nNNN` notation (`0n` = decimal). It needs a CodeView PDB next to
the binary - build native C++ with `clang-cl /Zi /Od` or an MSVC `/Zi` Debug build, not a
DWARF (`-g`) build. Startup `WARNING: Unable to verify checksum` / `srv*` symbol-server
lines are noise; the local PDB still binds.

## netcoredbg (.NET, CLI batch from a file)

```bash
netcoredbg --interpreter=cli --command=script.txt -- dotnet App.dll
```

`script.txt`:
```
break Program.cs:1
run
print a
continue
quit
```

`--command=FILE` runs the commands and the program to completion. Real output (trimmed of
library-load noise):

```
Breakpoint 1 at Program.cs:1 --pending, warning: No executable code ...
^running
breakpoint modified,  Breakpoint 1 at .../Program.cs:1
stopped, reason: breakpoint 1 hit, thread id: ..., frame={Program...g__Add|0_0() at .../Program.cs:1}
a = 0
stopped, reason: exited, exit-code: 0
```

The "No executable code" warning before the module loads is normal; `breakpoint modified`
confirms it resolved. netcoredbg colorizes output with ANSI codes by default; strip
`\x1b\[[0-9;]*m` when parsing.

Important distinction: netcoredbg's **CLI** interpreter works fine for *batch* runs from a
`--command` file, but it drops runtime output when driven over a stdin **pipe** - so the
persistent-session driver uses `--interpreter=mi` instead. See
`references/netcoredbg-dotnet.md` and `references/interactive-sessions.md`.

## Reading the output

A stop tells you three things: where (`file:line` / function with argument values), why
(`stop reason` / `Breakpoint N hit`), and the call site. Locals dumps print one variable
per line. A variable read *before* its line executes shows garbage (the gdb `sum = 32767`
above) - that is the breakpoint landing before the assignment, not a bug.
