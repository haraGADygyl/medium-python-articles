# One Object, Two Protocols: Context Managers That Are Also Decorators

#### `ContextDecorator` lets one manager wrap a block or a whole function, and the two kinds of manager disagree about what "the same object" means

**By Tihomir Manushev**

*Oct 5, 2026 · 9 min read*

---

Most codebases that time things have two timers. One is a context manager for timing a few lines inside a function. The other is a decorator for timing a whole function. They start out identical, and then someone adds a log field to one and forgets the other. Six months later the two produce slightly different output, and nobody remembers why there are two.

There never needed to be two. `contextlib.ContextDecorator` gives a context manager a `__call__` method, so the same object works after `with` and after `@`. Every manager built with `@contextmanager` already has it. The feature is cheap to adopt and easy to trust, which is why its sharp edge goes unnoticed: a class-based manager and a generator-based one treat repeated calls to the decorated function in opposite ways. One of them creates a fresh manager for every call. The other reuses a single instance forever, and that instance breaks under recursion and threads.

The examples come from a map-tile rendering service: tiles rasterized at different zoom levels, elevation fetched from a remote service, rendered PNGs pushed to object storage.

---

### One Class, Both Syntaxes

Here is a stage timer written once, as a class that inherits from `ContextDecorator`:

```python
import time
from contextlib import ContextDecorator


class StageTimer(ContextDecorator):
    """Report how long one stage of the tile pipeline takes."""

    def __init__(self, stage: str) -> None:
        self.stage = stage

    def __enter__(self) -> "StageTimer":
        self.started = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        elapsed_ms = (time.perf_counter() - self.started) * 1000
        print(f"{self.stage}: {elapsed_ms:.0f} ms")


with StageTimer("load style sheet"):
    time.sleep(0.02)
# load style sheet: 20 ms


@StageTimer("rasterize")
def rasterize_tile(zoom: int, column: int, row: int) -> str:
    """Pretend to turn vector data for one tile into pixels."""
    time.sleep(0.03)
    return f"{zoom}/{column}/{row}.png"


print(rasterize_tile(12, 2200, 1343))
# rasterize: 30 ms
# 12/2200/1343.png
print(rasterize_tile.__name__, rasterize_tile.__wrapped__.__name__)
# rasterize_tile rasterize_tile
```

The `with` usage is ordinary. The decorator usage works because `ContextDecorator.__call__` takes the function, builds a wrapper with `functools.wraps`, and has that wrapper run the original call inside `with` on a manager. Thanks to `wraps`, the result keeps its name, docstring and signature, and `__wrapped__` points back at the undecorated function. Tracebacks, `help()` and `inspect.signature` all behave as if the decorator weren't there.

Read the decorator line slowly, though. `StageTimer("rasterize")` runs once, at import time, when Python evaluates the `def` statement. Every later call to `rasterize_tile` goes through that one instance. Which manager the wrapper actually enters is decided by a small hook called `_recreate_cm()`, and on `ContextDecorator` that hook simply returns `self`.

---

### The Same Instance, Every Call

Sharing an instance is harmless until two calls overlap. Recursion is the easiest way to make them overlap. Tile rendering recurses naturally, because each tile is drawn and then its children at the next zoom level:

```python
import time
from contextlib import ContextDecorator


class StageTimer(ContextDecorator):
    """Report how long one stage of the tile pipeline takes."""

    def __init__(self, stage: str) -> None:
        self.stage = stage

    def __enter__(self) -> "StageTimer":
        self.started = time.perf_counter()
        return self

    def __exit__(self, *exc_info: object) -> None:
        elapsed_ms = (time.perf_counter() - self.started) * 1000
        print(f"{self.stage}: {elapsed_ms:.0f} ms")


@StageTimer("render")
def render_tile(zoom: int, max_zoom: int) -> None:
    """Render one tile, then recurse into the next zoom level."""
    time.sleep(0.01)
    if zoom < max_zoom:
        render_tile(zoom + 1, max_zoom)


render_tile(0, 2)
# render: 10 ms
# render: 10 ms   <- should be 20
# render: 10 ms   <- should be 30
```

Three calls entered the same object, and each `__enter__` overwrote `self.started`. By the time the outer calls exit, the attribute holds the start time of the innermost call, so every level reports the innermost duration. Nothing raises. The numbers are just wrong, and they look plausible.

Threads cause the same bug without any recursion. If two request handlers call `rasterize_tile` at overlapping moments, the second `__enter__` replaces the first thread's start time, and the first thread reports a duration that is too short. Any class-based manager that keeps per-entry state on `self` has this problem the moment it becomes a decorator. That covers start times, opened handles, saved previous values and acquired tokens.

---

### Why the Generator Version Gets It Right

Now write the same timer with `@contextmanager`:

```python
import time
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def stage_timer(stage: str) -> Iterator[None]:
    """Report how long one stage takes; the start time lives in the frame."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"{stage}: {elapsed_ms:.0f} ms")


@stage_timer("render")
def render_tile(zoom: int, max_zoom: int) -> None:
    """Render one tile, then recurse into the next zoom level."""
    time.sleep(0.01)
    if zoom < max_zoom:
        render_tile(zoom + 1, max_zoom)


render_tile(0, 2)
# render: 10 ms
# render: 20 ms
# render: 30 ms
```

The object that `stage_timer("render")` returns is a `_GeneratorContextManager`. It is single-use: it wraps one generator, and a generator can't be restarted. Normally that makes it the more fragile of the two. As a decorator, though, it overrides `_recreate_cm()` to build a brand-new manager, and therefore a brand-new generator, from the function and arguments it saved at construction. Every call to `render_tile` gets its own generator frame with its own `started` local. Recursion and threads can't collide because they have nothing to share.

So the two kinds of manager have opposite reuse rules. Class-based managers are reusable in `with` statements and *shared* as decorators. Generator-based managers are single-use in `with` statements and *fresh per call* as decorators.

That recreation has a precondition, and it produces one of the odder failures in the standard library:

```python
import time
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def stage_timer(stage: str) -> Iterator[None]:
    """Report how long one stage takes; the start time lives in the frame."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"{stage}: {elapsed_ms:.0f} ms")


upload_timer = stage_timer("upload")


@upload_timer
def upload_tile(path: str) -> str:
    """Pretend to push a rendered tile to object storage."""
    time.sleep(0.01)
    return f"s3://tiles/{path}"


print(upload_tile("12/2200/1343.png"))
print(upload_tile("12/2201/1343.png"))
# upload: 10 ms
# s3://tiles/12/2200/1343.png
# upload: 10 ms
# s3://tiles/12/2201/1343.png

with upload_timer:
    time.sleep(0.01)
# upload: 10 ms

try:
    upload_tile("12/2202/1343.png")
except AttributeError as error:
    print(error)
# '_GeneratorContextManager' object has no attribute 'func'
```

The decorated function works any number of times, because each call is served by a copy. Then someone notices the module-level `upload_timer` and uses it directly in a `with` block. That also works, once. But `__enter__` on a generator manager deletes its saved function and arguments, since it assumes nobody will need to recreate it. The decorator relied on exactly those attributes, so a function that was never touched starts raising `AttributeError` from inside `contextlib`. The rule follows directly: never bind a generator manager to a name. Write `@stage_timer("upload")` on the function itself, and call `stage_timer(...)` fresh at every `with` site.

---

### Fixing the Class Version

You can't override `_recreate_cm()` in your own class. Its docstring calls it a private interface meant only for `_GeneratorContextManager`. The supported fix is to stop keeping per-entry state in plain attributes. A stack handles nesting, and `threading.local` gives each thread its own stack:

```python
import threading
import time
from contextlib import ContextDecorator


class StageTimer(ContextDecorator):
    """Report stage timings; safe under recursion and across threads."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self._per_thread = threading.local()

    def _start_times(self) -> list[float]:
        """Return this thread's stack of start times, creating it once."""
        return self._per_thread.__dict__.setdefault("start_times", [])

    def __enter__(self) -> "StageTimer":
        self._start_times().append(time.perf_counter())
        return self

    def __exit__(self, *exc_info: object) -> None:
        started = self._start_times().pop()
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"{self.stage}: {elapsed_ms:.0f} ms")


@StageTimer("render")
def render_tile(zoom: int, max_zoom: int) -> None:
    """Render one tile, then recurse into the next zoom level."""
    time.sleep(0.01)
    if zoom < max_zoom:
        render_tile(zoom + 1, max_zoom)


render_tile(0, 2)
# render: 10 ms
# render: 20 ms
# render: 30 ms
```

Calls nest, so the last start time pushed belongs to the call that exits first, and a LIFO stack matches them exactly. The `threading.local` object hands each thread a separate `__dict__`, so concurrent handlers never touch each other's stacks. The class is now **reentrant**: one instance can be entered again while it is still active. That's the property a decorator needs. If the stack and the thread-local feel like more machinery than the job deserves, take that as the hint to write the manager as a generator instead.

---

### What the Wrapper Cannot Reach

`ContextDecorator` builds a plain synchronous wrapper: enter, call, exit. That's correct only when the work happens inside the call. For coroutine functions and generator functions, the call does none of the work:

```python
import asyncio
import inspect
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager


@contextmanager
def stage_timer(stage: str) -> Iterator[None]:
    """Report how long one stage takes; the start time lives in the frame."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"{stage}: {elapsed_ms:.0f} ms")


@stage_timer("fetch elevation")
async def fetch_elevation(column: int, row: int) -> float:
    """Pretend to ask a remote service for terrain height in metres."""
    await asyncio.sleep(0.05)
    return 412.5


@stage_timer("stream features")
def stream_features(count: int) -> Iterator[str]:
    """Pretend to read map features one at a time from disk."""
    for index in range(count):
        time.sleep(0.01)
        yield f"road-{index}"


print(inspect.iscoroutinefunction(fetch_elevation))  # False
print(asyncio.run(fetch_elevation(2200, 1343)))
# fetch elevation: 0 ms
# 412.5
print(list(stream_features(3)))
# stream features: 0 ms
# ['road-0', 'road-1', 'road-2']


@asynccontextmanager
async def async_stage_timer(stage: str) -> AsyncIterator[None]:
    """The async twin: its decorator form awaits the wrapped coroutine."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"{stage}: {elapsed_ms:.0f} ms")


@async_stage_timer("fetch elevation")
async def fetch_elevation_timed(column: int, row: int) -> float:
    """Same remote call, timed correctly this time."""
    await asyncio.sleep(0.05)
    return 412.5


print(inspect.iscoroutinefunction(fetch_elevation_timed))  # True
print(asyncio.run(fetch_elevation_timed(2200, 1343)))
# fetch elevation: 50 ms
# 412.5
```

Calling `fetch_elevation` only creates a coroutine object. The wrapper enters the timer, gets the coroutine back almost instantly, exits, and reports 0 ms. The real work runs later, when `asyncio.run` drives the coroutine, with no manager around it. The generator function behaves the same way: the timer has already closed before `list()` pulls the first row. Swap the timer for a lock and you get a lock released before the protected code runs. There's a second symptom too. The wrapper is an ordinary `def`, so `inspect.iscoroutinefunction` now returns `False`, and frameworks that use that check to choose between `await` and a thread pool will route the handler wrong.

Since Python 3.10, `@asynccontextmanager` objects inherit from `AsyncContextDecorator`, whose wrapper is an `async def` that uses `async with` and awaits the call. That times the actual work and keeps the function recognizably async. Generator functions have no equivalent. Put the `with` inside the generator body instead.

The wrapper has two other blind spots. It throws away whatever `__enter__` returns, so a manager whose value matters, such as a transaction that hands back a connection, has nothing useful to offer the decorated function. It also inherits the manager's suppression, and that is far easier to miss on a function than on a block:

```python
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def tolerate_missing_tiles() -> Iterator[None]:
    """Log a missing source file instead of crashing the batch."""
    try:
        yield
    except FileNotFoundError as error:
        print(f"skipped: {error.filename}")


@tolerate_missing_tiles()
def tile_checksum(path: str) -> int:
    """Read a tile from disk and return a cheap checksum."""
    with open(path, "rb") as tile_file:
        return sum(tile_file.read()) % 65_536


checksum = tile_checksum("/no/such/tile.png")
print(checksum)
# skipped: /no/such/tile.png
# None
```

The annotation promises an `int`. When the manager swallows the exception, the wrapper's `return` statement never runs, so the caller receives `None`. In a `with` block, the reader can see the fallback right next to the code. As a decorator, the fallback sits one line above the `def` and becomes part of the function's contract without appearing in its signature.

---

### What It Costs

Decoration is O(1) per call, and the constant depends on the kind of manager:

```python
import timeit
from collections.abc import Iterator
from contextlib import ContextDecorator, contextmanager


class EmptyManager(ContextDecorator):
    """A class-based manager that does nothing on either side."""

    def __enter__(self) -> "EmptyManager":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


@contextmanager
def empty_generator_manager() -> Iterator[None]:
    """A generator-based manager that does nothing on either side."""
    yield


def tile_key(zoom: int) -> int:
    """A function cheap enough that the wrapper dominates its cost."""
    return zoom + 1


candidates = {
    "bare function": tile_key,
    "class-based": EmptyManager()(tile_key),
    "generator-based": empty_generator_manager()(tile_key),
}
calls = 500_000
for label, candidate in candidates.items():
    seconds = timeit.timeit(lambda: candidate(12), number=calls)
    print(f"{label:>15}: {seconds / calls * 1e9:5.0f} ns per call")
#   bare function:    51 ns per call
#     class-based:   406 ns per call
# generator-based:  1090 ns per call
```

These are numbers from Python 3.12.3 on one machine, and yours will differ. The ratio is what matters. The class-based wrapper adds two method calls. The generator-based wrapper also builds a new manager object and a new generator on every call, which makes it about 2.7 times as expensive as the class version. On a function that does I/O, a microsecond is noise. On a function called millions of times in a tight loop, measure it before you decorate it.

---

### Conclusion

`ContextDecorator` really does remove the duplicate timer, the duplicate lock wrapper and the duplicate audit hook. One implementation can serve both `with` and `@`. Before you put one above a `def`, check four things. A class-based manager is a single instance shared by every call, so per-entry state needs a stack, and threads need `threading.local`. A generator-based manager is recreated per call, which makes it the safer default, as long as nobody also uses the same object in a `with` block. Async functions need `@asynccontextmanager` and generator functions need the `with` inside their body. And a manager that suppresses exceptions turns a failing function into one that quietly returns `None`. If all four come out fine, delete the duplicate helper.
