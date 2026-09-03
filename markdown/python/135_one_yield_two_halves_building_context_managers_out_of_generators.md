# One `yield`, Two Halves: Building Context Managers Out of Generators

#### `@contextmanager` splits a single function into setup and teardown — and if you skip four characters, the teardown half never runs

**By Tihomir Manushev**

*Sep 3, 2026 · 8 min read*

---

A context manager written as a class is mostly ceremony. You need a `__init__` to hold the arguments, an `__enter__` to do the setup, an `__exit__` with three parameters you will not look at, and state on `self` so the second method can find what the first one did. For a manager whose entire job is "set this, then unset it," that is twenty lines of scaffolding around two lines of intent.

`contextlib.contextmanager` collapses all of it into one function with one `yield` in the middle. Everything above the `yield` is `__enter__`. Everything below it is `__exit__`. The value you yield is what the `as` clause binds.

It is the most useful decorator in the standard library, and it has a failure mode that a class-based manager cannot have: **write the generator the obvious way and your teardown becomes unreachable the first time the caller raises.**

---

### The Same Manager, Written Twice

Here is a manager that takes a load-balancer node out of rotation for the duration of a block — the shape you reach for when patching a machine that is currently serving traffic.

```python
from contextlib import contextmanager
from types import TracebackType
from typing import Iterator

ROTATION: dict[str, str] = {"edge-a": "serving", "edge-b": "serving", "edge-c": "serving"}


class DrainedNode:
    """Take a node out of rotation for the duration of a block."""

    def __init__(self, node: str) -> None:
        self.node = node

    def __enter__(self) -> str:
        ROTATION[self.node] = "draining"
        print(f"  [enter] {self.node} -> draining")
        return self.node

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ROTATION[self.node] = "serving"
        print(f"  [exit]  {self.node} -> serving")


@contextmanager
def drained(node: str) -> Iterator[str]:
    """Exactly the same thing, as a generator."""
    ROTATION[node] = "draining"
    print(f"  [enter] {node} -> draining")
    try:
        yield node
    finally:
        ROTATION[node] = "serving"
        print(f"  [exit]  {node} -> serving")


with DrainedNode("edge-a") as target:
    print(f"  patching {target}")
# [enter] edge-a -> draining
#   patching edge-a
# [exit]  edge-a -> serving

with drained("edge-b") as target:
    print(f"  patching {target}")
# [enter] edge-b -> draining
#   patching edge-b
# [exit]  edge-b -> serving
```

Same behaviour, same call site, roughly a third of the code. The `node` parameter needs no home on `self`, because the generator's own frame is the state — it stays suspended at the `yield`, holding every local it had, until the block ends.

Note the return type: `Iterator[str]`, not `str`. You are annotating the generator function, and the `str` inside describes what it yields. `@contextmanager` then turns that into something whose `__enter__` returns `str`.

---

### The Split Happens at `yield`

The mechanics are worth stating precisely, because everything else follows from them.

When `with` executes, `@contextmanager`'s wrapper calls `next()` on the generator. The generator body runs from the top until it reaches `yield`, then suspends. The yielded value becomes the result of `__enter__`, which is what `as` binds. The `with` body then runs — while your generator sits frozen mid-function.

When the block ends normally, the wrapper calls `next()` a second time. The generator resumes just after the `yield` and runs to completion. That resumption is the entire `__exit__`.

So this:

```python
from contextlib import contextmanager
from typing import Iterator

ROTATION: dict[str, str] = {"edge-a": "serving"}


@contextmanager
def drained(node: str) -> Iterator[str]:
    ROTATION[node] = "draining"      # __enter__
    try:
        yield node                   # the with body runs here
    finally:
        ROTATION[node] = "serving"   # __exit__


with drained("edge-a") as target:
    print(ROTATION[target])          # draining
print(ROTATION["edge-a"])            # serving
```

is a single readable narrative of a resource's life, in the order it actually happens. The class version splits that story across two methods and asks you to reassemble it in your head.

---

### The Bug That Takes a Node Out of Rotation Forever

Now write it the way it first occurs to you. The `try`/`finally` looks like noise, so it goes:

```python
from contextlib import contextmanager
from typing import Iterator

ROTATION: dict[str, str] = {"edge-a": "serving"}


@contextmanager
def drained_unsafe(node: str) -> Iterator[str]:
    ROTATION[node] = "draining"
    yield node                      # nothing guards this
    ROTATION[node] = "serving"
```

This works perfectly. It works every single time, right up until the block raises:

```python
try:
    with drained_unsafe("edge-a"):
        raise TimeoutError("package mirror did not respond")
except TimeoutError as caught:
    print(f"caught: {caught}")
# caught: package mirror did not respond

print(f"edge-a status: {ROTATION['edge-a']!r}")
# edge-a status: 'draining'
```

(Both snippets belong in one file — the second half needs the manager defined above it.)

The node is still draining. It will be draining tomorrow. Your load balancer has quietly lost a third of its capacity because a package mirror timed out, and the code that was supposed to put it back is sitting on a line the interpreter will never reach.

The reason is mechanical. The exception propagates into the generator at the point where it is suspended — the `yield`. An unhandled exception at that line unwinds the generator's frame immediately. Line 4 is below line 3 in the source, but it is *after* the suspension point in execution, and there is nothing to make the interpreter run it on the way out.

A class-based manager cannot fail this way: `__exit__` is called by the `with` statement itself, so it runs whether the block succeeded or exploded. When you move teardown into a generator, you take that guarantee off Python and put it on yourself, and `finally` is how you pay it back:

```python
from contextlib import contextmanager
from typing import Iterator

ROTATION: dict[str, str] = {"edge-a": "serving"}


@contextmanager
def drained(node: str) -> Iterator[str]:
    ROTATION[node] = "draining"
    try:
        yield node
    finally:
        ROTATION[node] = "serving"


try:
    with drained("edge-a"):
        raise TimeoutError("package mirror did not respond")
except TimeoutError:
    pass
print(f"edge-a status: {ROTATION['edge-a']!r}")
# edge-a status: 'serving'
```

**Treat the `try` as part of the syntax.** If a `@contextmanager` generator has a bare `yield` with cleanup below it, that is a bug whether or not it has failed yet.

---

### The Exception Arrives *At* the `yield`

Because the exception is delivered into the generator's frame at the suspension point, a plain `except` around the `yield` catches exceptions from the caller's block. This is the feature that makes generator managers genuinely more expressive than the class form, where you get an exception *object* handed to `__exit__` rather than a live exception you can catch.

```python
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def observed(label: str) -> Iterator[str]:
    print(f"[setup] {label}")
    try:
        yield label
    except ValueError as caught:
        print(f"[caught at the yield] {caught!r}")
        raise RuntimeError(f"{label} failed validation") from caught
    finally:
        print(f"[teardown] {label}")


try:
    with observed("edge-c"):
        raise ValueError("weight must be positive")
except RuntimeError as escaped:
    print(f"[caller sees] {escaped}")
    print(f"[__cause__ ] {escaped.__cause__!r}")
# [setup] edge-c
# [caught at the yield] ValueError('weight must be positive')
# [teardown] edge-c
# [caller sees] edge-c failed validation
# [__cause__ ] ValueError('weight must be positive')
```

The `ValueError` was raised three frames away, inside the caller's `with` block, and caught by an `except` clause written around a `yield`. Under the hood the wrapper calls `gen.throw()`, which resumes the generator by raising at the suspension point instead of returning a value.

`finally` still runs, and in the right order — teardown happens before the new exception reaches the caller.

---

### Suppression Is Just Not Re-Raising

A class-based manager suppresses an exception by returning something truthy from `__exit__`, which is easy to do by accident. The generator form has no return value to get wrong. If you catch an exception around the `yield` and do not re-raise it, it is suppressed. That is all.

```python
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def tolerate_missing(label: str) -> Iterator[str]:
    try:
        yield label
    except FileNotFoundError as caught:
        print(f"[swallowed] {caught}")
        # Simply not re-raising is what suppresses it.
    finally:
        print(f"[teardown] {label}")


with tolerate_missing("cache-warm"):
    raise FileNotFoundError("manifest.json")
print("execution continues")
# [swallowed] manifest.json
# [teardown] cache-warm
# execution continues
```

This is harder to do by mistake and easier to read: the exception type you swallow is named in an `except` clause, exactly where a reader looks for it. The trade is that you can no longer suppress *everything* with one careless line — which is a trade worth making.

---

### One Generator, One Use

A `@contextmanager` object wraps one generator, and a generator that has run to completion cannot run again. So the object is single-use, and the way it fails is worse than you would expect:

```python
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def drained(node: str) -> Iterator[str]:
    print(f"[enter] {node}")
    try:
        yield node
    finally:
        print(f"[exit]  {node}")


window = drained("edge-a")

with window:
    print("  first use is fine")

try:
    with window:
        print("  second use")
except AttributeError as caught:
    print(f"AttributeError: {caught}")
# AttributeError: '_GeneratorContextManager' object has no attribute 'args'
```

Not a `RuntimeError` explaining that the manager is exhausted — an `AttributeError` about a missing private attribute, raised from inside `contextlib`. The reason is in the standard library source. `_GeneratorContextManager.__enter__` opens by deleting the arguments it was constructed with, under a comment reading *"do not keep args and kwds alive unnecessarily — they are only needed for recreation, which is not possible anymore."* It drops those references deliberately, and the second entry trips over their absence.

The fix is to call the function again rather than reusing the object — `with drained("edge-a"):` at each site, never a manager saved in a module-level variable and shared.

The neighbouring mistake produces a clearer message. A generator that yields twice cannot be a context manager, because there is no second block to run:

```python
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def twice() -> Iterator[int]:
    yield 1
    yield 2


try:
    with twice() as value:
        print(f"got {value}")
except RuntimeError as caught:
    print(f"RuntimeError: {caught}")
# got 1
# RuntimeError: generator didn't stop
```

The block ran, and the error surfaced during teardown when the second `next()` produced a value instead of `StopIteration`. **Exactly one `yield`, on exactly one path** — a `yield` inside an `if` whose other branch returns early is the same bug wearing a disguise, and it fails with `generator didn't yield` instead.

---

### The Same Deal, Asynchronously

`contextlib.asynccontextmanager` applies the identical split to an async generator, and it inherits the identical hazard. Everything before the `yield` runs on `__aenter__`, everything after on `__aexit__`, and a bare `yield` still strands your teardown when the block raises.

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

ROTATION: dict[str, str] = {"edge-a": "serving"}


@asynccontextmanager
async def drained(node: str) -> AsyncIterator[str]:
    ROTATION[node] = "draining"
    await asyncio.sleep(0)          # let the health checker notice
    try:
        yield node
    finally:
        ROTATION[node] = "serving"


async def main() -> None:
    try:
        async with drained("edge-a") as target:
            print(f"patching {target}, status {ROTATION[target]!r}")
            raise TimeoutError("mirror timed out")
    except TimeoutError:
        pass
    print(f"edge-a status: {ROTATION['edge-a']!r}")


asyncio.run(main())
# patching edge-a, status 'draining'
# edge-a status: 'serving'
```

You can `await` on both sides of the `yield`, which is the point — draining a node for real means telling a health checker and waiting for in-flight requests to finish. The annotation becomes `AsyncIterator[str]`, and the call site becomes `async with`.

---

### Conclusion

`@contextmanager` is the right default for any manager that does not need to be an object. Setup, the suspension point, and teardown read as one continuous story, and the parameters live in the generator's frame instead of on `self`.

What it hands you along with that brevity is one responsibility Python was previously carrying. `__exit__` is invoked by the `with` statement and always runs; the second half of a generator only runs if execution can get there. Four characters of `try` and `finally` are the whole difference between a manager that restores state and one that restores state *unless something goes wrong*, which is the only time it mattered.

Write the `try` first, before the `yield`, every time — and prefer calling the function at each `with` site over saving the manager, because a generator gets one life.
