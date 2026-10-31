# Python Has No Tail Call Elimination — Here Is What to Do Instead

#### A tail-recursive function still costs one frame per call in CPython, and 1,000 frames still raise `RecursionError`. A trampoline and an explicit stack remove the limit, and raising it brings risks of its own

**By Tihomir Manushev**

*Oct 31, 2026 · 9 min read*

---

The field splitter passed every test. It read lines of comma-separated sensor data with three small functions, one per lexer state: outside quotes, inside quotes, and just after a closing quote. Each function handled one character and then called the function for the next state. Then a gateway started batching two hundred readings onto a single line, and the splitter died with `RecursionError: maximum recursion depth exceeded`.

The first suggestion in code review was to make it tail recursive. It already was. Every recursive call sat in tail position, with its result returned unchanged, and that made no difference at all, because CPython does not eliminate tail calls. Every call still pushes a frame, and the thousandth frame still hits the limit.

This article shows the frames piling up and why CPython chose not to remove them. It then covers two rewrites that do work: a trampoline for tail calls and an explicit stack for everything else. Finally, it measures what happens when you raise the recursion limit instead, including a segfault that no `try` block can catch.

---

### A Lexer That Is Already Tail Recursive

Here is the splitter. Each state function reads one character, then returns the result of calling the next state, so every recursive call is a **tail call**: the last thing the function does, with its result passed back untouched.

```python
def unquoted(text: str, pos: int, fields: list[str],
             buf: list[str]) -> list[str]:
    """Read characters outside quotes until a comma or the end."""
    if pos == len(text):
        fields.append("".join(buf))
        return fields
    char = text[pos]
    if char == ",":
        fields.append("".join(buf))
        return unquoted(text, pos + 1, fields, [])
    if char == '"' and not buf:
        return quoted(text, pos + 1, fields, buf)
    buf.append(char)
    return unquoted(text, pos + 1, fields, buf)


def quoted(text: str, pos: int, fields: list[str],
           buf: list[str]) -> list[str]:
    """Read characters inside quotes, commas included."""
    if pos == len(text):
        raise ValueError("unterminated quote")
    if text[pos] == '"':
        return after_quote(text, pos + 1, fields, buf)
    buf.append(text[pos])
    return quoted(text, pos + 1, fields, buf)


def after_quote(text: str, pos: int, fields: list[str],
                buf: list[str]) -> list[str]:
    """A doubled quote is a literal quote; anything else ends the field."""
    if pos < len(text) and text[pos] == '"':
        buf.append('"')
        return quoted(text, pos + 1, fields, buf)
    return unquoted(text, pos, fields, buf)


def split_line(text: str) -> list[str]:
    """Split one line of comma-separated fields."""
    return unquoted(text, 0, [], [])


print(split_line('7,"Lisbon, PT","say ""ola"""'))
# ['7', 'Lisbon, PT', 'say "ola"']
```

Writing a lexer as a set of states makes the grammar easy to read: each function is one state, and each `return` is one transition. The cost is one call per character, and none of those calls returns until the line is finished. Feed it a line of 1,399 characters and count the frames in the traceback:

```python
import traceback

long_line = ",".join(["sensor"] * 200)
try:
    split_line(long_line)
except RecursionError as error:
    frames = traceback.extract_tb(error.__traceback__)
    print(f"{error}: {len(frames)} frames")
# maximum recursion depth exceeded: 1000 frames
```

There are exactly 1,000 entries, the default value of `sys.getrecursionlimit()`. Every one of them is a call that has nothing left to do except hand its result back, and CPython keeps all of them anyway.

---

### What Proper Tail Calls Would Do, and Why CPython Refuses

A language with **proper tail calls** notices that a call is in tail position and reuses the current frame for it instead of pushing a new one. The splitter would then run in constant stack space, like a loop. Scheme requires this, because the language has no loop construct and uses recursion for all iteration.

Guido van Rossum explained in two 2009 blog posts why Python doesn't do this, and his main reason was tracebacks. If frames get reused, a traceback no longer shows how the program got where it is, and a debugger can no longer step back up through the calls that happened. Python promises that the traceback shows the real call chain, and it keeps that promise for every call, not only for code written in a functional style. He also pointed out that once one implementation eliminated tail calls, programs would start depending on it, and every other Python would then be forced to support it.

There is also a practical obstacle. In `return unquoted(...)`, the name `unquoted` is looked up when the line runs, not when the function is compiled, so the compiler can't be sure the call is even recursive. Any optimization would have to happen at runtime, on every call.

One source of confusion is worth clearing up. Python 3.14 added an optional interpreter build that its release notes call a tail-calling interpreter. That refers to the C code inside CPython, where small functions that execute individual bytecodes jump to one another. It changes how CPython runs bytecode, not how your functions call each other. Your frames still pile up.

---

### The Trampoline: Return the Call Instead of Making It

If the language won't reuse frames, you can avoid creating them. A **trampoline** turns each tail call into a value. The state function returns a description of the next call, and a small loop makes that call, so the stack never grows deeper than one level:

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Bounce:
    """A call to make next, returned instead of made."""

    step: Callable[..., Any]
    args: tuple[Any, ...]


def trampoline[R](step: Callable[..., Bounce | R], *args: Any) -> R:
    """Run steps in a loop until one returns a real result."""
    result = step(*args)
    while isinstance(result, Bounce):
        result = result.step(*result.args)
    return result
```

Converting the lexer is mechanical. Every `return state(...)` becomes `return Bounce(state, (...))`, and nothing else changes:

```python
type Step = Bounce | list[str]


def t_unquoted(text: str, pos: int, fields: list[str],
               buf: list[str]) -> Step:
    """Read characters outside quotes until a comma or the end."""
    if pos == len(text):
        fields.append("".join(buf))
        return fields
    char = text[pos]
    if char == ",":
        fields.append("".join(buf))
        return Bounce(t_unquoted, (text, pos + 1, fields, []))
    if char == '"' and not buf:
        return Bounce(t_quoted, (text, pos + 1, fields, buf))
    buf.append(char)
    return Bounce(t_unquoted, (text, pos + 1, fields, buf))


def t_quoted(text: str, pos: int, fields: list[str],
             buf: list[str]) -> Step:
    """Read characters inside quotes, commas included."""
    if pos == len(text):
        raise ValueError("unterminated quote")
    if text[pos] == '"':
        return Bounce(t_after_quote, (text, pos + 1, fields, buf))
    buf.append(text[pos])
    return Bounce(t_quoted, (text, pos + 1, fields, buf))


def t_after_quote(text: str, pos: int, fields: list[str],
                  buf: list[str]) -> Step:
    """A doubled quote is a literal quote; anything else ends the field."""
    if pos < len(text) and text[pos] == '"':
        buf.append('"')
        return Bounce(t_quoted, (text, pos + 1, fields, buf))
    return Bounce(t_unquoted, (text, pos, fields, buf))


def split_line_flat(text: str) -> list[str]:
    """Split one line of comma-separated fields in constant stack."""
    return trampoline(t_unquoted, text, 0, [], [])


huge_line = ",".join(["sensor"] * 200_000)
print(len(huge_line))                   # 1399999
print(len(split_line_flat(huge_line)))  # 200000
```

A line of 1.4 million characters now goes through without touching the recursion limit. Each state function returns before the next one starts, so the deepest the stack gets is `trampoline` plus one state.

The cost is one `Bounce` allocation and one extra trip through the loop per step:

```python
from timeit import timeit

sample = ",".join(["sensor"] * 120)
print(split_line(sample) == split_line_flat(sample))  # True
print(timeit(lambda: split_line(sample), number=2000) / 2000)
# about 245 microseconds
print(timeit(lambda: split_line_flat(sample), number=2000) / 2000)
# about 315 microseconds
```

On an 839-character line, the trampoline runs about 30% slower than the recursive version, and both are O(n) in the length of the line. A single `while` loop holding a state variable would beat both. Choose the trampoline when the code is clearer as separate functions, as with state machines and mutually recursive parsers, and keep that structure without the depth limit.

---

### The Gotcha: Results That Are Callable

Many trampoline examples skip the `Bounce` class. They return a bare `lambda` and loop `while callable(result)`. That works until the real result is itself callable:

```python
def naive_trampoline(result: Any) -> Any:
    """Keep calling while the result is callable."""
    while callable(result):
        result = result()
    return result


def render_landing() -> str:
    """The handler a route finally resolves to."""
    return "<h1>Welcome</h1>"


def resolve(route: str) -> Any:
    """Follow route aliases until one names a handler."""
    aliases = {"/home": "/index", "/index": "/landing"}
    if route in aliases:
        return lambda: resolve(aliases[route])
    return render_landing


print(naive_trampoline(resolve("/home")))  # <h1>Welcome</h1>
```

The resolver was supposed to return the handler function. The naive loop couldn't tell the handler from one more step, so it called it and returned a page instead. A dedicated `Bounce` type removes the ambiguity: the loop continues only for objects that were built to mean "call this next".

---

### When the Call Isn't in Tail Position

A trampoline only helps with tail calls. Rendering a comment thread is a different kind of recursion, because each call has work left to do after the recursive call returns:

```python
from dataclasses import field


@dataclass
class Comment:
    """One comment and the replies posted under it."""

    author: str
    replies: list["Comment"] = field(default_factory=list)


def render(comment: Comment, depth: int = 0) -> list[str]:
    """Indent each reply one level deeper than its parent."""
    lines = [f"{'  ' * depth}{comment.author}"]
    for reply in comment.replies:
        lines.extend(render(reply, depth + 1))
    return lines


def flame_war(rounds: int) -> Comment:
    """Two users replying to each other, rounds levels deep."""
    root = current = Comment("ivo")
    for turn in range(1, rounds):
        reply = Comment("kai" if turn % 2 else "ivo")
        current.replies.append(reply)
        current = reply
    return root


try:
    render(flame_war(1500))
except RecursionError as error:
    print(f"RecursionError: {error}")
# RecursionError: maximum recursion depth exceeded
```

After `render(reply, ...)` returns, the loop still has to extend `lines` and move on to the next sibling. That pending work is exactly what the frame stores. The way out is to keep the pending work yourself, in a list used as a stack:

```python
def render_flat(root: Comment) -> list[str]:
    """Same output as render(), with a list standing in for the stack."""
    lines: list[str] = []
    pending: list[tuple[Comment, int]] = [(root, 0)]
    while pending:
        comment, depth = pending.pop()
        lines.append(f"{'  ' * depth}{comment.author}")
        for reply in reversed(comment.replies):
            pending.append((reply, depth + 1))
    return lines


thread = Comment("noor", [Comment("ivo", [Comment("noor")]),
                          Comment("kai")])
print(render_flat(thread) == render(thread))  # True
print(len(render_flat(flame_war(100_000))))   # 100000
```

Each tuple on `pending` holds what a frame would have held: which comment to visit, and at what depth. The `reversed()` call is the one subtle part. A stack pops the last item first, so you have to push the replies in reverse order for the first reply to come out first. Without it, the thread renders as `noor, kai, ivo, noor` and every test that compares output fails. The stack lives on the heap, so it can grow as large as memory allows, and a tuple costs far less than a frame.

---

### Why Not Just Raise the Limit?

`sys.setrecursionlimit()` is the one-line fix, and for pure Python code on 3.12 it mostly works:

```python
import sys

sys.setrecursionlimit(50_000)
print(len(render(flame_war(20_000))))  # 20000
```

Since 3.11, a call from Python to Python no longer uses the C stack, so deep recursion costs memory rather than crashing the process. In my measurements, a million frames of a one-argument function took about 140 MB. That is the first cost: a runaway recursion bug that used to fail after 1,000 calls now eats memory for 50 times longer before it does.

The second cost shows up as soon as the recursion goes through C code, such as `repr()`, `json.dumps()`, `pickle`, a comparison or a C extension. That kind of recursion is still guarded by a separate C-level limit, and raising the Python limit doesn't lift it. On 3.12.3, the dataclass `repr` of a 5,000-deep `flame_war` still raises `RecursionError` at a limit of 50,000. A thread with a smaller stack has a worse problem: the C stack runs out before the guard triggers.

```python
import sys
import threading

sys.setrecursionlimit(20_000)
deep_thread = flame_war(1_000)
print(len(repr(deep_thread)))  # 33000

threading.stack_size(512 * 1024)
worker = threading.Thread(target=lambda: print(len(repr(deep_thread))))
worker.start()
worker.join()
# Segmentation fault (core dumped)
```

The main thread printed 33,000. The worker thread took the whole process down: no exception, no traceback, nothing for a `try` block to catch. That happened on both 3.12.3 and 3.13.9. On 3.14.0, the worker raised `RecursionError: Stack overflow (used 480 kB)` instead, because 3.14 checks how much C stack is actually left rather than counting calls. If you raise the limit, raise it by a measured amount, in the one place that needs it, and never as a fix for recursion whose depth depends on user input.

---

### Conclusion

CPython never reuses frames, so tail recursion is only a style choice and not an optimization. A tail call costs a frame like any other call, and the traceback that keeps all those frames is a feature the language decided to keep.

When a recursion's depth depends on data you don't control, rewrite it. Tail calls between separate functions, such as state machines, lexers and mutually recursive parsers, fit a trampoline with an explicit `Bounce` type. Recursion with work left after the call, such as tree walks and nested structures, needs an explicit stack, and pushing children in reverse keeps their order. Recursion is still fine when the depth is small and fixed, such as a balanced tree or a parse tree for one expression. Raise `sys.setrecursionlimit()` only by a measured amount, and remember that it can't protect code that recurses through C.
