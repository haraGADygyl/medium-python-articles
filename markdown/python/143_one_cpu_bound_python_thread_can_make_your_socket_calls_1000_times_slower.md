# One CPU-Bound Python Thread Can Make Your Socket Calls 1,000 Times Slower

#### The GIL's 5-millisecond switch interval is not a time slice. It is how long a waiting thread must sit before it may ask for the lock, and a thread waking from I/O pays that wait every time

**By Tihomir Manushev**

*Nov 10, 2026 · 8 min read*

---

The lookup service answered a local request in ten microseconds. It ran a thread per connection, spent its life waiting on sockets, and nobody had thought about it in months. Then a teammate moved the shipping-rate rebuild out of a cron job and into a background thread of the same process, so the table would stay fresh. One core out of twelve went busy, and every lookup started taking ten milliseconds.

Nothing in that change looks dangerous. Threads are supposed to suit I/O, because blocking calls release the **Global Interpreter Lock (GIL)**, and the rebuild was using a core nobody else wanted. Both statements are true, and the service still got a thousand times slower. The expensive moment is not when a thread gives up the GIL. It is when the thread wants it back.

This article measures that cost on CPython 3.12.3, traces the number to the interpreter's source, shows a C call that ignores the whole mechanism, and compares the fixes. Every timing comes from one 12-CPU Linux machine, so expect your own numbers to differ.

---

### Threads Add Nothing to CPU Work

Start with the half everyone knows, because the rest of the article depends on the workload it uses. The rebuild below is pure-Python arithmetic, and the helper splits a fixed amount of it across a number of threads.

```python
import threading
import time


def rebuild_rates(rounds: int) -> int:
    """Recompute a shipping-rate table in pure Python."""
    total = 0

    for step in range(rounds):
        total += step % 7

    return total


def rebuild_in_threads(workers: int, rounds: int) -> float:
    """Split the rebuild across threads and return elapsed seconds."""
    pool = [
        threading.Thread(target=rebuild_rates, args=(rounds // workers,))
        for _ in range(workers)
    ]
    started = time.perf_counter()

    for thread in pool:
        thread.start()

    for thread in pool:
        thread.join()

    return time.perf_counter() - started


if __name__ == "__main__":
    for workers in (1, 2, 4, 8):
        elapsed = rebuild_in_threads(workers, 40_000_000)
        print(f"{workers} threads: {elapsed:.2f} s")

    # 1 threads: 1.67 s
    # 2 threads: 1.68 s
    # 4 threads: 1.67 s
    # 8 threads: 1.69 s
```

A thread must hold the GIL to run bytecode, so eight threads take turns at work one thread could do alone. The gain is zero. The often-repeated warning that threads make CPU work dramatically slower did not show up here: the waiting threads sleep instead of spinning, and a 1.7-second run only contains a few hundred hand-offs.

So far the GIL looks like a missed opportunity and nothing worse.

---

### A Thread That Only Waits

Now the lookup service, reduced to its skeleton. A socket pair removes the network from the measurement, leaving only the kernel and the interpreter.

```python
import socket
import statistics


def serve_lookups(conn: socket.socket) -> None:
    """Echo each request back until the peer hangs up."""
    while request := conn.recv(32):
        conn.sendall(request)


def median_round_trip_ms(samples: int) -> float:
    """Time request/response pairs over a local socket pair."""
    client, server = socket.socketpair()
    worker = threading.Thread(target=serve_lookups, args=(server,))
    worker.start()
    timings = []

    for _ in range(samples):
        started = time.perf_counter()
        client.sendall(b"sku-1042")
        client.recv(32)
        timings.append(time.perf_counter() - started)

    client.close()
    worker.join()
    server.close()

    return statistics.median(timings) * 1000


if __name__ == "__main__":
    print(f"quiet: {median_round_trip_ms(2000):.3f} ms")  # quiet: 0.010 ms
```

The main thread plays the client and a second thread plays the server. Ten microseconds per round trip, with two threads handing the work back and forth through the kernel, is the baseline that Python threads are justly praised for.

---

### Add One Busy Neighbor

The context manager below keeps a task running on background threads for the length of a `with` block. The task here is a slice of the same rebuild.

```python
from collections.abc import Callable, Iterator
from contextlib import contextmanager


@contextmanager
def alongside(task: Callable[[], object], copies: int = 1) -> Iterator[None]:
    """Keep calling task on background threads during the block."""
    stop = threading.Event()

    def repeat() -> None:
        while not stop.is_set():
            task()

    threads = [threading.Thread(target=repeat) for _ in range(copies)]

    for thread in threads:
        thread.start()

    try:
        yield
    finally:
        stop.set()

        for thread in threads:
            thread.join()


def rebuild_slice() -> int:
    """Run one small unit of the background rebuild."""
    return rebuild_rates(100_000)


if __name__ == "__main__":
    with alongside(rebuild_slice):
        print(f"one busy: {median_round_trip_ms(300):.3f} ms")

    with alongside(rebuild_slice, copies=3):
        print(f"three busy: {median_round_trip_ms(300):.3f} ms")

    # one busy: 10.166 ms
    # three busy: 38.205 ms
```

One busy thread moved the median from 0.010 ms to 10.166 ms. The machine had CPUs to spare, so this was never a shortage of processor. Three busy threads pushed it to between 35 and 41 ms across five runs.

---

### The Switch Interval Is a Waiting Room

Most explanations say Python pauses the running thread every 5 milliseconds. CPython has no such timer. The logic lives in `take_gil` in `Python/ceval_gil.c`, and it runs on the side of the thread that *wants* the lock.

The waiter sleeps on a condition variable for the switch interval, which `sys.getswitchinterval()` reports as `0.005`. If that wait times out, the lock is still held, and no switch happened in the meantime, the waiter sets a flag called `gil_drop_request`. The running thread checks that flag only at certain points in the bytecode, such as backward jumps in loops and function entry. When it sees the flag it releases the GIL, then waits until another thread has actually taken it, so it cannot immediately grab the lock back.

Two consequences follow. A thread that nobody is waiting on keeps the GIL for as long as it runs bytecode, because no waiter means no request. And five milliseconds is not a slice of CPU time the thread is entitled to. It is a waiting room every thread must sit in before it can even knock.

Now the arithmetic works out. `recv` releases the GIL before it blocks, and the busy thread takes it at once. When data arrives, the receiving thread comes back from the kernel with no lock and sits out a full interval. A round trip has two blocking receives, one on each side, so it costs two intervals: 10 ms, against 10.166 measured. A short `sendall` took about 10 microseconds under the same load, so it evidently gets the lock back before the busy thread can claim it.

The added latency is therefore O(blocking wakeups × interval), and it does not depend on how little work each wakeup does. Chatty code suffers most. By that arithmetic, a request making 20 database round trips, each with one blocking receive, picks up about 100 ms. With three busy threads the bill grew faster than the thread count, which fits the source: any switch among the others restarts the waiter's patience. David Beazley reported this pattern as the "convoy effect" in Python issue 7946 in 2010, and CPython 3.12 with its default build still behaves this way.

---

### The C Call That Ignores the Request

The drop request only works where the interpreter checks for it, and a C function running inside a single bytecode instruction never checks. The helper below records the longest silence of a thread that tries to tick once per millisecond.

```python
def longest_stall_ms(workload: Callable[[], object]) -> float:
    """Run workload while a ticker thread records its longest gap."""
    gaps: list[float] = []
    finished = threading.Event()

    def tick() -> None:
        previous = time.perf_counter()

        while not finished.is_set():
            time.sleep(0.001)
            now = time.perf_counter()
            gaps.append(now - previous)
            previous = now

    ticker = threading.Thread(target=tick)
    ticker.start()
    time.sleep(0.05)
    workload()
    finished.set()
    ticker.join()

    return max(gaps) * 1000


if __name__ == "__main__":
    loop_stall = longest_stall_ms(lambda: rebuild_rates(30_000_000))
    sum_stall = longest_stall_ms(lambda: sum(range(100_000_000)))
    print(f"Python loop: {loop_stall:.1f} ms")  # Python loop: 6.2 ms
    print(f"sum(range()): {sum_stall:.1f} ms")  # sum(range()): 1297.4 ms
```

Both workloads run for over a second. The Python loop reaches a check point on every iteration, so the ticker waits about one interval at worst. `sum` over a `range` is one call into C, and the ticker stays frozen for all 1.3 seconds of it. Sorting three million random floats stalled the same ticker for 800 ms, and `pow(3, 5_000_000)` for 819 ms. This is the gotcha in "just use the built-in, it's faster": the fast C call that holds the GIL throughout is the one that starves everything else.

---

### What Actually Fixes It

The real fix is to stop competing for the lock. There are two ways: do the CPU work in C code that releases the GIL, or do it in another process, which has a GIL of its own.

```python
import hashlib
import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

PAYLOAD = os.urandom(4_000_000)


def hash_payload() -> bytes:
    """Hash a buffer large enough for hashlib to drop the GIL."""
    return hashlib.sha256(PAYLOAD).digest()


if __name__ == "__main__":
    with alongside(hash_payload):
        print(f"hashlib: {median_round_trip_ms(2000):.3f} ms")

    spawn = get_context("spawn")

    with ProcessPoolExecutor(max_workers=1, mp_context=spawn) as pool:
        with alongside(lambda: pool.submit(rebuild_slice).result()):
            print(f"process: {median_round_trip_ms(2000):.3f} ms")

    # hashlib: 0.011 ms
    # process: 0.010 ms
```

Both return to the baseline. `hashlib` releases the GIL for buffers of 2,048 bytes or more, and `zlib.compress` on the same buffer measured the same. In the second case the background thread only waits on a future, so it asks almost nothing of the GIL.

The `spawn` context is not decoration. The first version of this script used Linux's default `fork` on Python 3.12, and it hung forever: the forked worker inherited a copy of the socket pair, so `client.close()` never produced end-of-file for the server, and `worker.join()` never returned. Forking from a threaded process is a bad bargain anyway, and Python 3.12 emits a `DeprecationWarning` for it.

The tempting third option is a knob: shrink the interval.

```python
import sys


def measure_interval(interval: float) -> tuple[float, float]:
    """Return median round trip (ms) and 4-thread rebuild time (s)."""
    sys.setswitchinterval(interval)

    try:
        with alongside(rebuild_slice):
            latency = median_round_trip_ms(300)

        return latency, rebuild_in_threads(4, 40_000_000)
    finally:
        sys.setswitchinterval(0.005)


if __name__ == "__main__":
    for interval in (0.005, 0.001, 0.0001, 0.00001):
        latency, rebuild = measure_interval(interval)
        print(f"{interval * 1000:g} ms: {latency:.3f} ms, {rebuild:.2f} s")

    # 5 ms: 10.163 ms, 1.72 s
    # 1 ms: 2.161 ms, 1.77 s
    # 0.1 ms: 0.339 ms, 1.95 s
    # 0.01 ms: 0.158 ms, 2.21 s
```

Dropping to 0.1 ms buys a 30-fold latency improvement, and it cost the rebuild between 5 and 13 percent across four runs, which is a fair trade for a stopgap. It is still 34 times the quiet baseline, it applies to the whole process, and it does nothing about a long C call. Treat it as a mitigation while you move the work elsewhere.

Two habits help find this in production. Latency that clusters near multiples of 5 ms is a strong hint, since a healthy I/O path has no reason to land there. And an event loop is no escape, because `select` releases the GIL like any other blocking call. A coroutine awaiting `asyncio.sleep(0.001)` resumed after a median of 1.07 ms in a quiet process and 6.15 ms beside one busy thread. Free-threaded builds of Python 3.13 and later remove the GIL and with it this toll, but they are not measured here.

---

### Conclusion

The GIL's reputation rests on the wrong number. The missing speedup on CPU work is easy to see and easy to plan around. The expensive part is the toll on threads that barely run: every blocking call that returns has to wait for the lock, and beside a busy thread that wait is a full switch interval. Long C calls skip the request altogether.

When a process serves I/O, keep pure-Python computation out of it. Push that work to a process pool started with `spawn`, or to C code that releases the GIL, and reach for `sys.setswitchinterval` only as a stopgap. Then measure your own round trips with a busy neighbor running, because a quiet benchmark will never show you this bill.
