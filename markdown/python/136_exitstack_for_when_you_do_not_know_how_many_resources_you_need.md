# `ExitStack`: For When You Do Not Know How Many Resources You Need

#### Nested `with` blocks fix the resource count when you write the code — `ExitStack` moves that decision to runtime without giving up a single cleanup guarantee

**By Tihomir Manushev**

*Sep 14, 2026 · 8 min read*

---

A `with` statement is a promise made at write time. Two managers on one line means two resources, entered left to right and released right to left, even if the block raises. That promise is exactly as wide as the source code. When the number of resources comes from a config file, a database row, or whichever instruments happen to be plugged into the bench today, the syntax runs out.

What most codebases do next is a list, a loop, and a `try`/`finally` written by hand. It looks correct, it passes review, and it leaks the moment one cleanup step fails, because a loop stops at the first exception, and so does a hand-rolled unwind.

`contextlib.ExitStack` is the standard library's answer. It is a context manager that holds other context managers, plus any cleanup functions you give it, and unwinds all of them in reverse order when its own block ends. What follows builds the hand-rolled version, breaks it, and then covers what `ExitStack` does that the loop cannot: surviving a failing cleanup, mixing managers with plain callbacks, and transferring ownership out of a constructor that failed halfway.

---

### The loop everyone writes first

The examples use a test lab. Each bench instrument is a connection that must be released, and a sweep connects to however many instruments the test plan lists. `StickyRelay` is the same connection with a release that raises, which is what a relay welded shut looks like to the driver.

```python
class InstrumentLink:
    """A connection to one bench instrument in a test lab."""

    def __init__(self, name: str, fails_on_connect: bool = False) -> None:
        self.name = name
        self.fails_on_connect = fails_on_connect

    def __enter__(self) -> "InstrumentLink":
        if self.fails_on_connect:
            raise ConnectionError(f"{self.name} did not answer")
        print(f"connected {self.name}")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        print(f"released {self.name}")

    def measure(self) -> float:
        """Stand-in for a real reading."""
        return round(len(self.name) * 1.37, 2)


class StickyRelay(InstrumentLink):
    """An instrument whose release itself fails."""

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        raise OSError(f"{self.name} relay stuck closed")
```

The manual sweep calls the protocol directly. It records each instrument as it connects, so a connection failure partway through only unwinds what actually opened, and it releases in reverse order:

```python
def run_sweep_by_hand(bench: list[InstrumentLink]) -> list[float]:
    """Open every instrument, take one reading each, release them all."""
    opened: list[InstrumentLink] = []
    try:
        for link in bench:
            opened.append(link.__enter__())
        return [link.measure() for link in opened]
    finally:
        for link in reversed(opened):
            link.__exit__(None, None, None)


print(run_sweep_by_hand([InstrumentLink("oscilloscope"),
                         InstrumentLink("multimeter")]))
# connected oscilloscope
# connected multimeter
# released multimeter
# released oscilloscope
# [16.44, 13.7]
```

This is better than most versions in the wild, and it is still wrong. Put a sticky relay in the middle of the bench:

```python
stuck_bench = [
    InstrumentLink("oscilloscope"),
    StickyRelay("load-bank"),
    InstrumentLink("multimeter"),
]
try:
    run_sweep_by_hand(stuck_bench)
except OSError as error:
    print(f"sweep failed: {error}")
# connected oscilloscope
# connected load-bank
# connected multimeter
# released multimeter
# sweep failed: load-bank relay stuck closed
```

The oscilloscope was never released. The `OSError` escaped from inside the `finally` loop, and a loop has no idea that later iterations still matter. Fixing it by hand means a `try` inside the loop, somewhere to keep the first error, a decision about which exception wins, and passing the original exception into every `__exit__` instead of `None, None, None`. That is the logic of the `with` statement, reimplemented one bug at a time.

---

### Handing the bookkeeping to `ExitStack`

`ExitStack.enter_context()` calls a manager's `__enter__`, pushes its `__exit__` onto an internal stack, and returns whatever `__enter__` returned. When the `with ExitStack()` block ends, normally or by exception, the stack pops every exit in last-in, first-out order:

```python
from contextlib import ExitStack


def run_sweep(bench: list[InstrumentLink]) -> list[float]:
    """The same sweep, with the bookkeeping handed to ExitStack."""
    with ExitStack() as stack:
        opened = [stack.enter_context(link) for link in bench]
        return [link.measure() for link in opened]


try:
    run_sweep(stuck_bench)
except OSError as error:
    print(f"sweep failed: {error}")
# connected oscilloscope
# connected load-bank
# connected multimeter
# released multimeter
# released oscilloscope
# sweep failed: load-bank relay stuck closed
```

Same bench, same stuck relay, and this time the oscilloscope is released. `ExitStack` catches the relay's exception, keeps unwinding, and re-raises it once every remaining exit has run. The comprehension reads like the naive version. The guarantee behind it is the one nested `with` blocks give you.

A failure while *entering* is handled too. If the third instrument refuses to connect, `enter_context` raises before anything is pushed for it, so only the two that connected get released:

```python
flaky_bench = [
    InstrumentLink("oscilloscope"),
    InstrumentLink("multimeter"),
    InstrumentLink("spectrum-analyzer", fails_on_connect=True),
]
try:
    run_sweep(flaky_bench)
except ConnectionError as error:
    print(f"sweep aborted: {error}")
# connected oscilloscope
# connected multimeter
# released multimeter
# released oscilloscope
# sweep aborted: spectrum-analyzer did not answer
```

The cost is what you would expect. Registering an exit is an O(1) append to a `collections.deque`, and unwinding is O(n) in the number of registrations, a linear walk you were going to pay in the loop anyway.

---

### What happens to the exception you already had

When the block itself raises and a cleanup raises too, one exception has to win. `ExitStack` follows the same rule as nested `with` statements: the newer exception propagates, and the original is attached as its `__context__`, so the traceback shows both.

```python
try:
    with ExitStack() as stack:
        stack.enter_context(InstrumentLink("oscilloscope"))
        stack.enter_context(StickyRelay("load-bank"))
        raise ValueError("reading out of range")
except OSError as error:
    print(f"raised:  {error!r}")
    print(f"context: {error.__context__!r}")
# connected oscilloscope
# connected load-bank
# released oscilloscope
# raised:  OSError('load-bank relay stuck closed')
# context: ValueError('reading out of range')
```

Suppression carries through as well. Each exit receives the exception that is live at the moment it runs. If one exit returns a truthy value to swallow the error, the exits registered before it see a clean exit, exactly as the outer blocks of a nested `with` would.

---

### Cleanup that is not a context manager

Plenty of cleanup is a plain function call: return a booking, delete a row, restore a global. `stack.callback(fn, *args, **kwargs)` registers any callable to run during unwinding, alongside the managers and in the same LIFO order. It returns the callable unchanged, so it also works as a decorator:

```python
reserved_benches: set[str] = set()


def run_reserved_sweep(bench_id: str,
                       bench: list[InstrumentLink]) -> list[float]:
    """Book the bench, sweep it, and always hand the booking back."""
    with ExitStack() as stack:
        reserved_benches.add(bench_id)
        stack.callback(reserved_benches.discard, bench_id)

        @stack.callback
        def report() -> None:
            print(f"{bench_id} free: {bench_id not in reserved_benches}")

        opened = [stack.enter_context(link) for link in bench]
        return [link.measure() for link in opened]


print(run_reserved_sweep("bench-7", [InstrumentLink("thermal-chamber")]))
print(f"after the block: {reserved_benches}")
# connected thermal-chamber
# released thermal-chamber
# bench-7 free: False
# [20.55]
# after the block: set()
```

Read the fourth line of output carefully, because it is the most common `ExitStack` mistake. `report` was registered *after* the booking release, so it runs *before* it and reports the bench as still booked. The booking does get returned, as the last line proves, just one step later than the report assumed. A cleanup that inspects the result of another cleanup has to be registered first. Write registrations in setup order, and the teardown order follows.

Callbacks receive no exception information. When a cleanup step needs to know whether the block failed, register it with `stack.push()` instead, which accepts any callable with the `__exit__` signature, including the option to suppress.

---

### Ownership transfer with `pop_all()`

The hardest case is a constructor that acquires several resources. If the third acquisition fails, the first two must be released, because the caller never receives an object to close. If all of them succeed, nothing may be released, because the object owns them now. A `with` block cannot express "clean up only on failure", and that is precisely what `pop_all()` is for:

```python
class Rig:
    """Owns a set of instrument links for longer than one with block."""

    def __init__(self, bench: list[InstrumentLink]) -> None:
        with ExitStack() as stack:
            self.links = [stack.enter_context(link) for link in bench]
            self._teardown = stack.pop_all()

    def close(self) -> None:
        """Release every link the constructor acquired, newest first."""
        self._teardown.close()


try:
    Rig(flaky_bench)
except ConnectionError as error:
    print(f"no rig: {error}")
# connected oscilloscope
# connected multimeter
# released multimeter
# released oscilloscope
# no rig: spectrum-analyzer did not answer

rig = Rig([InstrumentLink("oscilloscope"), InstrumentLink("multimeter")])
print("rig ready")
rig.close()
# connected oscilloscope
# connected multimeter
# rig ready
# released multimeter
# released oscilloscope
```

`pop_all()` moves every registered exit into a brand-new `ExitStack` and leaves the original empty. When construction fails, the exception fires before `pop_all()` is reached, so the local stack still holds the links and releases them. When construction succeeds, the local stack is empty by the time its block closes, and the new stack, now stored on `self`, owns the teardown until `close()` runs it. Two lines turn a leaky constructor into a transactional one.

---

### Gotchas worth knowing

**Pass the manager, not its class.** `enter_context` checks the argument's *type* for `__enter__` and `__exit__`. Handing it a class, which is an easy slip when a factory and a class share a name, fails immediately:

```python
try:
    with ExitStack() as stack:
        stack.enter_context(InstrumentLink)
except TypeError as error:
    print(error)
# 'builtins.type' object does not support the context manager protocol
```

That message is the Python 3.12 wording. Before 3.11, the same mistake raised `AttributeError` instead, so code that catches the error by type has to know which one it gets.

**An `ExitStack` outside `with` cleans up nothing on its own.** Creating one and registering managers is legal, and nothing unwinds until you call `close()`. The `pop_all()` pattern relies on that, and everything else should use the `with` form.

**It is not Go's `defer`.** `defer` is tied to the enclosing function. An `ExitStack` is an object, scoped to a block, that you can build conditionally, store on an instance, and close from somewhere else entirely. That flexibility is the reason to use it and also the reason to keep its lifetime obvious.

**Async code has its own class.** `AsyncExitStack` adds `enter_async_context()` and `push_async_callback()` for `async with` managers and coroutine cleanups, with identical unwinding rules.

---

### Conclusion

Nested `with` statements are the right tool when you can count your resources in the source. When the count is only known at runtime, `ExitStack` keeps every guarantee those statements give: reverse-order release, partial-failure unwinding, exception chaining and suppression. It also adds three things they cannot do: plain-function callbacks, runtime-sized entry, and ownership transfer through `pop_all()`.

The practical rule is short. If you catch yourself writing a list of opened resources and a loop in a `finally`, replace both with `enter_context` in a comprehension. Register cleanups in the order you set things up. And when a constructor acquires more than one resource, end it with `pop_all()` so that a failure halfway through leaves nothing behind.
