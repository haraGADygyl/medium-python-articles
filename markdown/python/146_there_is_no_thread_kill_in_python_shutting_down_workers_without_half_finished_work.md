# There Is No `Thread.kill()` in Python: Shutting Down Workers Without Half-Finished Work

#### Python won't stop a thread from the outside, and the workaround people find online breaks data in a way the obvious test never shows. Here is how to stop threads and tasks so every unit of work is either done or not started

**By Tihomir Manushev**

*Nov 24, 2026 · 10 min read*

---

A warehouse service moves stock between bins on a background thread. Deploys restart it, and the shutdown code wants the thread gone *now*. Someone searches "python kill thread", finds a snippet that calls `PyThreadState_SetAsyncExc` through `ctypes`, and pastes it in. Shutdowns get fast. A week later, the nightly stock count comes up one unit short, then another, always on deploy days.

`threading.Thread` has `start`, `join` and `is_alive`, and nothing that stops it. That isn't an oversight. A thread stopped at an arbitrary point can leave behind work that is half done: a counter changed on one side of a transfer but not the other, a file with half a record in it, a lock that nobody will ever release.

Python's answer is that a worker stops itself, at a point it chooses. This article measures what the forced kill breaks, builds the cooperative version with `threading.Event`, covers the two places it fails (a blocking queue and daemon threads), and then looks at `Task.cancel()`, which asyncio can afford to offer because it knows exactly where the exception will land. Every number comes from Python 3.12.3 on Linux.

---

### What a Forced Kill Breaks

CPython has a C function, `PyThreadState_SetAsyncExc`, that schedules an exception in another thread. Its documentation says to call it from your own C extension, precisely so that nobody uses it casually. `ctypes` gets around that in two lines:

```python
import ctypes
import threading
import time

TOTAL_UNITS = 1_000


class Halt(Exception):
    """Raised inside a thread from the outside."""


def force_raise(thread: threading.Thread) -> None:
    """Ask CPython to raise Halt in another thread at its next check."""
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread.ident), ctypes.py_object(Halt))


def take(bins: dict[str, int], name: str) -> None:
    """Remove one unit from a bin."""
    bins[name] -= 1


def put(bins: dict[str, int], name: str) -> None:
    """Add one unit to a bin."""
    bins[name] += 1


def move_unit(bins: dict[str, int], source: str, target: str) -> None:
    """Take one unit out of source, then put it into target."""
    take(bins, source)
    put(bins, target)


def shuffle_stock(bins: dict[str, int]) -> None:
    """Move one unit back and forth between two bins, forever."""
    try:
        while True:
            move_unit(bins, "aisle-3", "aisle-7")
            move_unit(bins, "aisle-7", "aisle-3")
    except Halt:
        pass


def one_kill() -> int:
    """Start a mover, kill it, and return the units on the shelves."""
    bins = {"aisle-3": TOTAL_UNITS, "aisle-7": 0}
    mover = threading.Thread(target=shuffle_stock, args=(bins,))
    mover.start()
    time.sleep(0.002)
    force_raise(mover)
    mover.join()

    return bins["aisle-3"] + bins["aisle-7"]


counts = [one_kill() for _ in range(200)]
broken = sum(1 for units in counts if units != TOTAL_UNITS)

print(f"{broken} of {len(counts)} kills left the stock wrong")
# 74 of 200 kills left the stock wrong
```

The mover never loses a unit on its own; every `move_unit` takes one and puts one. Yet 74 of 200 kills left the shelves holding 999 units, and across ten runs the count ranged from 72 to 94. Each time, the exception landed after `take` returned and before `put` ran, and the unit vanished.

The gotcha is in how I got there. My first version did both steps inline in the loop body, and 0 of 200 kills broke it. The interpreter only checks for a pending exception at certain points, such as the start of a function call or the jump back to the top of a loop, and the inline version had no such point between its two halves. Move one step into a helper function, an ordinary refactor, and the failure rate goes from zero to over a third. A test of the hack proves nothing about the next version of the code.

The forced exception also can't reach a thread that is blocked in C:

```python
def nap_then_report() -> None:
    """Block in one long call."""
    started = time.perf_counter()

    try:
        time.sleep(3)
    except Halt:
        print(f"Halt arrived after {time.perf_counter() - started:.2f} s")


sleeper = threading.Thread(target=nap_then_report)
sleeper.start()
time.sleep(0.1)
force_raise(sleeper)
sleeper.join()
# Halt arrived after 3.00 s
```

The kill was sent at 0.1 s and took effect at 3 s, when `time.sleep` returned to the interpreter. A thread stuck on a socket read stays stuck. So the hack corrupts the threads that are running and doesn't stop the ones that are stuck. Java reached the same conclusion: it deprecated `Thread.stop` in 1998, and since Java 20 the method only throws `UnsupportedOperationException`.

---

### Asking a Thread to Stop

The cooperative version gives the worker a **`threading.Event`**, a thread-safe flag, and the worker checks it *between* units of work. A unit always finishes, because the worker never looks at the flag in the middle of one. Here is a restocking thread that writes an order every two seconds, in two versions:

```python
from collections.abc import Callable

type Worker = Callable[[threading.Event, list[str]], None]


def restock_napping(stop: threading.Event, orders: list[str]) -> None:
    """Write a restock order, then sleep for the interval."""
    while not stop.is_set():
        orders.append(f"order-{len(orders) + 1}")
        time.sleep(2.0)


def restock_waiting(stop: threading.Event, orders: list[str]) -> None:
    """Write a restock order, then wait for the interval or a stop."""
    while not stop.is_set():
        orders.append(f"order-{len(orders) + 1}")
        stop.wait(2.0)


def time_shutdown(worker_body: Worker) -> None:
    """Start a worker, ask it to stop, and time how long it takes."""
    stop = threading.Event()
    orders: list[str] = []
    worker = threading.Thread(target=worker_body, args=(stop, orders))
    worker.start()
    time.sleep(0.3)
    asked = time.perf_counter()
    stop.set()
    worker.join()
    waited = time.perf_counter() - asked
    print(f"{worker_body.__name__}: stopped in {waited * 1000:.1f} ms, "
          f"{len(orders)} order(s)")


time_shutdown(restock_napping)
time_shutdown(restock_waiting)
# restock_napping: stopped in 1700.1 ms, 1 order(s)
# restock_waiting: stopped in 0.1 ms, 1 order(s)
```

Both stop cleanly, but the napping version sits out the rest of its `time.sleep` before it sees the flag. `stop.wait(2.0)` blocks for up to two seconds *or until someone sets the flag*, whichever comes first, and returns `True` in the second case. Any sleep inside a stoppable worker should be an `Event.wait`.

---

### A Thread Blocked on a Queue Can't See the Flag

The flag only works if the worker gets back to the check. A worker blocked in `queue.get()` with an empty queue never does:

```python
import queue


def pack_forever(jobs: queue.Queue[str], stop: threading.Event,
                 packed: list[str]) -> None:
    """Pack shipments as they arrive, checking the flag between them."""
    while not stop.is_set():
        shipment = jobs.get()
        time.sleep(0.05)  # pick, box and label
        packed.append(shipment)


def pack_until_stopped(jobs: queue.Queue[str], stop: threading.Event,
                       packed: list[str]) -> None:
    """Pack shipments, waking at least every 100 ms to check the flag."""
    while not stop.is_set():
        try:
            shipment = jobs.get(timeout=0.1)
        except queue.Empty:
            continue

        time.sleep(0.05)  # pick, box and label
        packed.append(shipment)


type Packer = Callable[[queue.Queue[str], threading.Event, list[str]], None]


def run_packer(packer: Packer, shipments: int, settle: float) -> None:
    """Queue some shipments, stop the packer after settle seconds."""
    jobs: queue.Queue[str] = queue.Queue()
    stop = threading.Event()
    packed: list[str] = []
    worker = threading.Thread(target=packer, args=(jobs, stop, packed),
                              daemon=True)
    worker.start()

    for number in range(shipments):
        jobs.put(f"SHP-{501 + number}")

    time.sleep(settle)
    asked = time.perf_counter()
    stop.set()
    worker.join(timeout=1.0)
    waited = time.perf_counter() - asked
    state = "still running" if worker.is_alive() else "stopped"
    print(f"{packer.__name__}: {state} after {waited * 1000:.0f} ms, "
          f"packed {len(packed)}, left {jobs.qsize()}")


run_packer(pack_forever, shipments=3, settle=0.5)
run_packer(pack_until_stopped, shipments=10, settle=0.125)
# pack_forever: still running after 1000 ms, packed 3, left 0
# pack_until_stopped: stopped after 25 ms, packed 3, left 7
```

`pack_forever` emptied the queue and went back to `get()`, where it will wait for a shipment that never comes. Note that `join(timeout=1.0)` doesn't tell you that: it returns `None` either way, and only `is_alive()` shows the thread survived. Check it after every timed join.

`pack_until_stopped` puts a timeout on the wait, so it sees the flag within 100 ms. The flag arrived 25 ms into the third shipment, so the packer finished that box, stopped, and left seven shipments in the queue for the next run. Python 3.13 adds `Queue.shutdown()`, which wakes blocked `get` calls directly, and a sentinel value in the queue works on any version; either removes the polling delay.

---

### Daemon Threads Are Killed, Not Stopped

`daemon=True` looks like a shutdown strategy: the interpreter doesn't wait for daemon threads at exit. It ends them abruptly instead, wherever they are, without running their `finally` blocks:

```python
import subprocess
import sys


def worker_source(daemon: bool) -> str:
    """Build a script whose sync thread cleans up in a finally block."""
    return f"""
import threading
import time


def sync_inventory() -> None:
    try:
        print("sync started", flush=True)
        time.sleep(5)
    finally:
        print("sync cleaned up", flush=True)


threading.Thread(target=sync_inventory, daemon={daemon}).start()
time.sleep(0.1)
print("main done", flush=True)
"""


for daemon in (True, False):
    started = time.perf_counter()
    result = subprocess.run([sys.executable, "-c", worker_source(daemon)],
                            capture_output=True, text=True)
    took = time.perf_counter() - started
    print(f"daemon={daemon}: exited after {took:.1f} s, "
          f"printed {result.stdout.splitlines()}")
# daemon=True: exited after 0.1 s, printed ['sync started', 'main done']
# daemon=False: exited after 5.0 s, printed ['sync started', 'main done',
#   'sync cleaned up']
```

The daemon run never printed `sync cleaned up`. Open files don't get flushed, and transactions don't get committed or rolled back. Use daemon threads only for work that can be lost at any instant, such as a progress spinner or a metrics sampler. Everything else should be a normal thread with a stop flag that the main thread sets and then joins.

---

### Stopping a Pool on SIGTERM

A deploy usually ends a service with `SIGTERM`, and a service with several workers needs one place where that signal becomes the stop flag. Python runs signal handlers on the main thread, so the handler only has to set the `Event`. The main thread then gives all workers one shared deadline:

```python
import os
import signal


def run_packing_shift() -> None:
    """Run three packers until SIGTERM, then stop them within a deadline."""
    jobs: queue.Queue[str] = queue.Queue()
    stop = threading.Event()
    packed: list[str] = []
    signal.signal(signal.SIGTERM, lambda signum, frame: stop.set())
    packers = [threading.Thread(target=pack_until_stopped,
                                args=(jobs, stop, packed), name=f"packer-{n}")
               for n in range(3)]

    for packer in packers:
        packer.start()

    for number in range(40):
        jobs.put(f"SHP-{601 + number}")

    threading.Timer(0.3, os.kill, args=(os.getpid(), signal.SIGTERM)).start()
    stop.wait()
    deadline = time.monotonic() + 2.0

    for packer in packers:
        packer.join(timeout=max(0.0, deadline - time.monotonic()))

    stuck = [packer.name for packer in packers if packer.is_alive()]
    print(f"packed {len(packed)}, left {jobs.qsize()}, stuck {stuck}")


run_packing_shift()
# packed 18, left 22, stuck []
```

The `threading.Timer` stands in for the deploy tool, sending the process its own `SIGTERM` after 300 ms. Each packer finished the box in its hands and stopped. The 22 shipments still in the queue were never started, which is the outcome you want: nothing is lost, and nothing is half packed. The deadline is shared rather than given to each `join`, so three slow workers can't turn a two-second budget into six. Any thread left in `stuck` is the one to log and investigate, since it is blocked somewhere the flag can't reach.

---

### `Task.cancel()`: an Exception at a Line You Can See

asyncio does have a kill switch. `task.cancel()` throws `CancelledError` into the coroutine, and it can be offered safely because a coroutine only runs between `await`s. The exception arrives at the `await` where the task is suspended, never between two plain statements. That makes the risky points visible in the source:

```python
import asyncio
from collections.abc import Awaitable

type Step = Callable[[dict[str, int], str, str], Awaitable[None]]


async def save_count(name: str, count: int) -> None:
    """Pretend to write one bin's count to the stock database."""
    await asyncio.sleep(0.01)


async def save_transfer(source: str, target: str) -> None:
    """Pretend to record a whole transfer in one transaction."""
    await asyncio.sleep(0.01)


async def transfer(bins: dict[str, int], source: str, target: str) -> None:
    """Take a unit, save the source, add it, save the target."""
    bins[source] -= 1
    await save_count(source, bins[source])
    bins[target] += 1
    await save_count(target, bins[target])


async def transfer_whole(bins: dict[str, int], source: str,
                         target: str) -> None:
    """Record the transfer first, then apply both halves with no await."""
    await save_transfer(source, target)
    bins[source] -= 1
    bins[target] += 1


async def shuttle(step: Step, bins: dict[str, int]) -> None:
    """Move units back and forth until cancelled."""
    while True:
        await step(bins, "aisle-3", "aisle-7")
        await step(bins, "aisle-7", "aisle-3")


async def cancel_shuttle(step: Step) -> None:
    """Cancel a shuttle at two moments and count the units."""
    for delay in (0.005, 0.015):
        bins = {"aisle-3": 1_000, "aisle-7": 0}
        task = asyncio.create_task(shuttle(step, bins))
        await asyncio.sleep(delay)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        print(f"{step.__name__} cancelled at {delay * 1000:.0f} ms: "
              f"{sum(bins.values())} units")


asyncio.run(cancel_shuttle(transfer))
asyncio.run(cancel_shuttle(transfer_whole))
# transfer cancelled at 5 ms: 999 units
# transfer cancelled at 15 ms: 1000 units
# transfer_whole cancelled at 5 ms: 1000 units
# transfer_whole cancelled at 15 ms: 1000 units
```

`transfer` has an `await` between its two halves, and a cancel at 5 ms lands right there, losing a unit. You can see that from the code without running it. `transfer_whole` awaits once, for a single transaction, and then changes both counts with no `await` in between, so a cancel either happens before anything changed or after everything did. With a real database, a cancelled transaction rolls back, so nothing is half-written there either. The rule is short: never put an `await` between two changes that must happen together.

---

### The `CancelledError` You Must Re-raise

Since Python 3.8, `CancelledError` subclasses `BaseException`, so `except Exception` no longer catches it by accident. Catching it on purpose, for cleanup, is fine, as long as the handler raises it again. Here is what happens when it doesn't:

```python
async def recount_aisle(swallow: bool) -> str:
    """Count an aisle bin by bin, writing a note if interrupted."""
    for bin_number in range(10):
        try:
            await asyncio.sleep(0.1)  # scan one bin
        except asyncio.CancelledError:
            print(f"  interrupted at bin {bin_number}")

            if not swallow:
                raise

    return "recount complete"


async def with_deadline(swallow: bool) -> None:
    """Give the recount 250 ms."""
    started = time.perf_counter()

    try:
        async with asyncio.timeout(0.25):
            result = await recount_aisle(swallow)

        print(f"  returned {result!r}")
    except TimeoutError:
        print("  TimeoutError")

    print(f"  swallow={swallow}: done at {time.perf_counter() - started:.2f} s")


asyncio.run(with_deadline(swallow=False))
asyncio.run(with_deadline(swallow=True))
#   interrupted at bin 2
#   TimeoutError
#   swallow=False: done at 0.25 s
#   interrupted at bin 2
#   returned 'recount complete'
#   swallow=True: done at 0.95 s
```

`asyncio.timeout` works by cancelling the task and turning the `CancelledError` into `TimeoutError` on the way out. The swallowing recount ate the cancellation and kept counting, so the 250 ms deadline ran to 0.95 s and raised nothing. The same task, cancelled directly, finishes with a normal result and reports `task.cancelled()` as `False`. `TaskGroup`, `wait_for` and `asyncio.run`'s own shutdown all rely on cancellation reaching the top, so one handler that swallows it breaks all of them. Put cleanup in `finally`, or end an `except CancelledError` block with a bare `raise`.

---

### Conclusion

Python leaves out `Thread.kill()` because no outside party knows where the thread's work is safe to interrupt. The `ctypes` workaround showed both halves of the problem: it lost a unit in 72 to 94 of every 200 kills once one step moved into a helper, and it couldn't interrupt a thread blocked in `time.sleep` at all.

For threads, give every worker a `threading.Event`, check it between units of work, wait with `Event.wait` instead of `time.sleep`, put timeouts on blocking `get` calls, and follow every `join(timeout=...)` with `is_alive()`. Keep daemon threads for work that can be lost. For tasks, `cancel()` is safe because it lands at an `await`, so keep `await`s out of the middle of anything that must happen as a whole, and always re-raise `CancelledError`. A worker that stops at a boundary it chose leaves nothing for the next run to repair.
