# The Truthy Return in `__exit__` That Silently Swallows Your Exceptions

#### One stray `return` at the end of a cleanup method turns every failure inside the `with` block into silence — and the interpreter never warns you

**By Tihomir Manushev**

*Aug 24, 2026 · 8 min read*

---

Here is a context manager that looks entirely reasonable. It times a block of work and records whether that work failed — the kind of thing that ends up in every observability layer eventually.

```python
import time
from types import TracebackType


class SpanRecorder:
    """Times a block of work and records whether it failed."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.elapsed_ms: float = 0.0
        self.failed: bool = False

    def __enter__(self) -> "SpanRecorder":
        self._started = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self.elapsed_ms = (time.perf_counter() - self._started) * 1000
        self.failed = exc_type is not None
        print(f"[span] {self.label} took {self.elapsed_ms:.1f}ms failed={self.failed}")
        return True


def settle_invoice(cents: int) -> int:
    if cents < 0:
        raise ValueError(f"refusing to settle a negative amount: {cents}")
    return cents


with SpanRecorder("settle") as span:
    total = settle_invoice(-250)
    print("this line never runs")

print("execution continues as if nothing happened")
print(f"span.failed = {span.failed}")
```

Running it produces:

```
[span] settle took 0.0ms failed=True
execution continues as if nothing happened
span.failed = True
```

The `ValueError` was raised. It is gone. There is no traceback, no log line, no non-zero exit code — and `total` was never assigned, so the next function to touch it dies with a `NameError` pointing at a line that has nothing to do with the actual bug.

The culprit is the last line of `__exit__`: `return True`. Whoever wrote it almost certainly meant "cleanup succeeded." Python read it as "I have handled the exception, discard it."

---

### The Three Arguments Are the Whole Interface

When a `with` block ends, Python calls `__exit__` on the context manager with exactly three arguments. On a clean exit they are all `None`. On an exceptional exit they describe the exception in flight:

```python
from types import TracebackType


class ArgumentProbe:
    def __enter__(self) -> "ArgumentProbe":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        print(f"exc_type  = {exc_type}")
        print(f"exc_value = {exc_value!r}")
        print(f"traceback = {type(traceback).__name__}")


with ArgumentProbe():
    pass
# exc_type  = None
# exc_value = None
# traceback = NoneType

try:
    with ArgumentProbe():
        raise LookupError("shard 7 is offline")
except LookupError as caught:
    print(f"caller still sees: {caught!r}")
# exc_type  = <class 'LookupError'>
# exc_value = LookupError('shard 7 is offline')
# traceback = traceback
# caller still sees: LookupError('shard 7 is offline')
```

Two details are worth pinning down. First, `exc_type is None` is the only reliable test for "did this block succeed" — checking `exc_value` works too, but a bare `raise SomeError` with no arguments still produces a truthy instance, so people reach for `exc_type` out of habit and it is the right habit.

Second, this `__exit__` returns `None`, and the `LookupError` reached the caller untouched. That is the default and correct behaviour: **a falsy return means "I did not handle this, keep unwinding."** A method that ends without an explicit `return` returns `None`, which is falsy, which is why most context managers never think about the return value at all.

---

### Truthiness, Not `True`

The check the interpreter performs is not `result is True`. It is a plain truthiness test, and you can see it in the bytecode. Compiling a minimal `with` block on Python 3.12 and disassembling it gives, at the exception-handling end:

```
>>   40 PUSH_EXC_INFO
     42 WITH_EXCEPT_START
     44 POP_JUMP_IF_TRUE         1 (to 48)
     46 RERAISE                  2
>>   48 POP_TOP
     50 POP_EXCEPT
```

`WITH_EXCEPT_START` calls `__exit__` with the three exception arguments and leaves its return value on the stack. `POP_JUMP_IF_TRUE` then decides the program's fate in one instruction: jump past the `RERAISE` if the value is truthy, fall into it if not.

That means `1`, `"ok"`, `[0]`, a non-empty dict, and any object whose `__bool__` returns `True` all suppress the exception exactly as thoroughly as `return True` does. Nothing type-checks this. Annotating `__exit__` as returning `bool` and then returning an `int` will be flagged by mypy but not by the interpreter, and plenty of `__exit__` methods carry no annotation at all.

The most common instance of that last category comes from muscle memory. `__enter__` ends with `return self`, so the hand types the same thing at the bottom of `__exit__`:

```python
from types import TracebackType


class ChainableGuard:
    def __enter__(self) -> "ChainableGuard":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> "ChainableGuard":
        return self


with ChainableGuard():
    raise ZeroDivisionError("denominator collapsed to zero")
print("the ZeroDivisionError never escaped")
# the ZeroDivisionError never escaped
```

A plain object with no `__bool__` and no `__len__` is truthy, so `return self` suppresses everything. The annotation is even self-consistent — the method really does return a `ChainableGuard`. Nothing in the type system objects; the object simply is not falsy.

---

### The Accidental Suppressor

The `return True` in the opening example is at least visible in code review. The version that actually ships looks like this:

```python
from types import TracebackType


class BufferedAuditLog:
    def __init__(self) -> None:
        self._pending: list[str] = []

    def record(self, line: str) -> None:
        self._pending.append(line)

    def _flush(self) -> int:
        """Write buffered lines out and return how many were written."""
        written = len(self._pending)
        self._pending.clear()
        return written

    def __enter__(self) -> "BufferedAuditLog":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> int:
        return self._flush()
```

`return self._flush()` is a natural thing to write. `_flush` is the cleanup, so returning its result feels like tidy plumbing. But `_flush` returns a count, and a count is truthy whenever it is not zero.

The result is a bug whose behaviour depends on the *data*, not the code path:

```python
from types import TracebackType


class BufferedAuditLog:
    def __init__(self) -> None:
        self._pending: list[str] = []

    def record(self, line: str) -> None:
        self._pending.append(line)

    def _flush(self) -> int:
        written = len(self._pending)
        self._pending.clear()
        return written

    def __enter__(self) -> "BufferedAuditLog":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> int:
        return self._flush()


def run(record_first: bool) -> str:
    """Fail inside the block, optionally after recording one line first."""
    audit = BufferedAuditLog()
    try:
        with audit:
            if record_first:
                audit.record("began reconciliation")
            raise RuntimeError("ledger checksum mismatch")
    except RuntimeError:
        return "propagated"
    return "swallowed"


print(run(record_first=True))    # swallowed
print(run(record_first=False))   # propagated
```

Identical source, identical exception, opposite outcomes. A request that logged something before failing disappears; a request that failed immediately raises normally. This is the shape of bug that survives months in production and produces support tickets reading "sometimes the job just stops."

The fix is to make the return value deliberate. Call the cleanup as a statement, and let the method fall off the end:

```python
from types import TracebackType


class BufferedAuditLog:
    def __init__(self) -> None:
        self._pending: list[str] = []

    def record(self, line: str) -> None:
        self._pending.append(line)

    def _flush(self) -> int:
        written = len(self._pending)
        self._pending.clear()
        return written

    def __enter__(self) -> "BufferedAuditLog":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._flush()          # called, not returned


fixed = BufferedAuditLog()
try:
    with fixed:
        fixed.record("began reconciliation")
        raise RuntimeError("ledger checksum mismatch")
except RuntimeError as caught:
    print(f"propagated: {caught}")
# propagated: ledger checksum mismatch
```

Annotating the return type as `None` is not cosmetic here — it tells a type checker that any `return <value>` in this method is an error, which is exactly the guardrail the bug needed.

---

### Suppressing On Purpose

Suppression is a real feature, and sometimes you want it. The rule is that it must be conditional on the exception type, never unconditional:

```python
from types import TracebackType


class StaleCacheTolerated:
    """Lets a cache miss pass silently; everything else propagates."""

    def __init__(self) -> None:
        self.suppressed: str | None = None

    def __enter__(self) -> "StaleCacheTolerated":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is not None and issubclass(exc_type, KeyError):
            self.suppressed = str(exc_value)
            return True
        return False


guard = StaleCacheTolerated()
with guard:
    raise KeyError("region:eu-north")
print(f"swallowed a cache miss: {guard.suppressed}")
# swallowed a cache miss: 'region:eu-north'

try:
    with StaleCacheTolerated():
        raise TimeoutError("upstream took 30s")
except TimeoutError as caught:
    print(f"propagated: {caught}")
# propagated: upstream took 30s
```

`issubclass(exc_type, KeyError)` rather than `exc_type is KeyError` matters: a subclass of `KeyError` should be caught by the same rule, the same way an `except KeyError` clause would catch it.

If suppression is *all* you need, the standard library already ships it and you should not write the class above:

```python
from contextlib import suppress
from pathlib import Path

stale = Path("/tmp/does-not-exist-9f2a.tmp")

with suppress(FileNotFoundError):
    stale.unlink()
print("cleanup finished")            # cleanup finished

with suppress(FileNotFoundError, PermissionError):
    stale.unlink()
print("still fine")                  # still fine

try:
    with suppress(FileNotFoundError):
        raise IsADirectoryError("that is a directory")
except IsADirectoryError as caught:
    print(f"not suppressed: {caught}")
# not suppressed: that is a directory
```

`contextlib.suppress` is the honest version of `try`/`except SomeError: pass`, and it names the types it swallows at the call site where a reader will see them.

---

### Finding These in a Codebase You Did Not Write

Because the symptom is silence, you cannot grep for the failure — you have to grep for the shape. Every `__exit__` that returns anything other than a bare `None` or a literal `False` is worth a human looking at it, and the standard library's `ast` module makes that a twenty-line script:

```python
import ast
import sys
from pathlib import Path


def suspicious_exits(source: str, filename: str) -> list[str]:
    """Report every __exit__ that returns something other than a bare None."""
    findings: list[str] = []
    tree = ast.parse(source, filename)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "__exit__":
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Return) or inner.value is None:
                continue
            if isinstance(inner.value, ast.Constant) and inner.value.value is False:
                continue
            rendered = ast.unparse(inner.value)
            findings.append(f"{filename}:{inner.lineno}: __exit__ returns {rendered}")
    return findings


for path in map(Path, sys.argv[1:]):
    for line in suspicious_exits(path.read_text(), str(path)):
        print(line)
```

Pointed at the files from this article, it prints exactly the three lines that matter:

```
span_recorder.py:26: __exit__ returns True
stale_cache.py:21: __exit__ returns True
audit_log.py:25: __exit__ returns self._flush()
```

Note what it does *not* report: the `return False` inside `StaleCacheTolerated`, and the two managers that end without returning at all. `ast.unparse` renders the offending expression back into source, so a reviewer can triage the list without opening every file. Run it across a repository and the output is usually short — under a dozen hits in a large codebase — which is exactly the size of list a person will actually read.

---

### `__exit__` Must Not Raise

The mirror image of swallowing too much is raising during cleanup, which destroys the original error:

```python
from types import TracebackType


class LeasedConnection:
    def __enter__(self) -> "LeasedConnection":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        raise OSError("socket already closed by peer")


try:
    with LeasedConnection():
        raise ValueError("row 88 has a malformed timestamp")
except OSError as caught:
    print(f"caller sees: {caught!r}")
    print(f"__context__: {caught.__context__!r}")
# caller sees: OSError('socket already closed by peer')
# __context__: ValueError('row 88 has a malformed timestamp')
```

The `ValueError` is not lost — it survives on `__context__`, and the printed traceback includes it under "During handling of the above exception, another exception occurred." But the exception the caller catches, the one that reaches the top of the stack and drives every `except` clause above it, is now the cleanup failure. Code written to handle `ValueError` will not run.

Cleanup that can fail belongs inside its own `try`/`except` within `__exit__`, logging the failure rather than raising it. The one job `__exit__` has during an exception is to not make things worse.

---

### It Swallows `BaseException` Too

One last consequence of the truthiness test: it does not discriminate by exception type, and the exceptions that inherit from `BaseException` rather than `Exception` are not exempt.

```python
from types import TracebackType


class SwallowsEverything:
    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return True


with SwallowsEverything():
    raise KeyboardInterrupt("user pressed Ctrl-C")
print("Ctrl-C was ignored")          # Ctrl-C was ignored

with SwallowsEverything():
    raise SystemExit(2)
print("sys.exit(2) was ignored")     # sys.exit(2) was ignored
```

The script above runs to completion and exits with status `0`. A user hammering Ctrl-C cannot stop a loop wrapped in that manager, and a deliberate `sys.exit(2)` inside the block does not set the exit code — which means a CI job built on it reports success no matter what happened.

That is why an unconditional `return True` is strictly worse than a bare `except:` clause. A bare `except` at least catches the eye: linters flag it, style guides name it, and reviewers have been trained since their first year to stop on it. A `return True` at the bottom of a fifteen-line `__exit__` reads like an afterthought about cleanup, and it is the only line in the method that does not concern cleanup at all.

---

### Conclusion

The return value of `__exit__` is not a status code. It is a single question the interpreter asks — *should I stop unwinding?* — answered by a truthiness test compiled down to one `POP_JUMP_IF_TRUE`.

Three habits keep it from biting. Annotate `__exit__` as `-> None` and let it fall off the end, so a type checker rejects any accidental `return value`. Never return the result of a cleanup call; invoke it as a statement. And when you do want suppression, gate it on `issubclass(exc_type, ...)`, or reach for `contextlib.suppress` and name the exceptions where the reader can see them.

The failure mode here is uniquely nasty because there is nothing to debug. No traceback, no log line, no crash — just work that quietly did not happen, discovered days later by a number that does not add up.
