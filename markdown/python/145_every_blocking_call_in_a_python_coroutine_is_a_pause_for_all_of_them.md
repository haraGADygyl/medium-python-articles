# Every Blocking Call in a Python Coroutine Is a Pause for All of Them

#### asyncio never takes the CPU away from a task, so one `time.sleep`, one password hash, or one long loop freezes every other task, and nothing reports an error

**By Tihomir Manushev**

*Nov 20, 2026 · 10 min read*

---

A fleet telemetry gateway had one odd alert. Its monitor expected a heartbeat from the service every 100 ms, and every morning between seven and eight the heartbeats arrived late in bursts. The logs had no exceptions in them, the CPU sat at 15%, and the slow endpoint everyone suspected answered in a few milliseconds. The cause was the driver login. It checked each device token with `hashlib.pbkdf2_hmac`, a plain function call inside an `async def` handler, and each call took about 200 ms. For those 200 ms the event loop ran nothing else: no heartbeat, no telemetry, no other request. Seven o'clock is when the drivers log in.

An `async def` function doesn't run in the background. It runs on the event loop's thread, and the loop can only switch to another task when the current one gives up control. Any call that holds the thread without doing that is a pause for every task in the process.

This article builds a small probe that measures those pauses, uses it on the stalls that don't look like stalls, catches them with asyncio's debug mode, and compares the ways to move the work off the loop. Every number comes from Python 3.12.3 on one Linux machine.

---

### The Loop Only Moves When a Task Lets Go

The asyncio event loop is a scheduler with no power to interrupt. It takes a task that is ready, runs it until the coroutine **suspends**, then picks the next ready task. A coroutine suspends at an `await` on something that isn't finished yet: a socket with no data, a timer that hasn't fired, a future another task will complete. Everything between two suspensions, which asyncio calls a **step**, runs to completion with the whole thread to itself. This is **cooperative scheduling**. Threads are different: the interpreter makes a running thread hand over the GIL once another thread has waited for the switch interval. The event loop has nothing like that.

To see a pause, you need something that notices it. This probe asks to sleep for 10 ms over and over and records how late each wake-up comes:

```python
import asyncio
import time
from collections.abc import Awaitable, Callable

TICK = 0.01


async def heartbeat(lags: list[float], done: asyncio.Event) -> None:
    """Wake every TICK seconds and record how late each wake-up was."""
    while not done.is_set():
        asked = time.perf_counter()
        await asyncio.sleep(TICK)
        lags.append(time.perf_counter() - asked - TICK)


async def measure(label: str,
                  work: Callable[[], Awaitable[object]]) -> None:
    """Run work beside a heartbeat and report how late the beats came."""
    lags: list[float] = []
    done = asyncio.Event()
    beat = asyncio.create_task(heartbeat(lags, done))
    await asyncio.sleep(0.05)  # let the heartbeat start before measuring
    lags.clear()
    start = time.perf_counter()
    await work()
    took = time.perf_counter() - start
    done.set()
    await beat
    print(f"{label}: took {took * 1000:.0f} ms, "
          f"worst lag {max(lags) * 1000:.1f} ms, heartbeats {len(lags)}")
```

On an idle loop, the lag is a fraction of a millisecond, the time it takes the loop to notice the timer. A lag of 200 ms means some step held the thread for 200 ms. Here are two ways of waiting 200 ms:

```python
async def nap_politely() -> None:
    """Wait 200 ms the asyncio way."""
    await asyncio.sleep(0.2)


async def nap_rudely() -> None:
    """Wait 200 ms by blocking the whole thread."""
    time.sleep(0.2)


async def compare_naps() -> None:
    """Measure both naps against the heartbeat."""
    await measure("asyncio.sleep(0.2)", nap_politely)
    await measure("time.sleep(0.2)", nap_rudely)


asyncio.run(compare_naps())
# asyncio.sleep(0.2): took 202 ms, worst lag 0.1 ms, heartbeats 21
# time.sleep(0.2): took 200 ms, worst lag 200.2 ms, heartbeats 1
```

Both took the same time, but only the first one let the heartbeat run. `asyncio.sleep` registers a timer and suspends, so the loop gets the thread back. `time.sleep` puts the thread itself to sleep, so the heartbeat that should have run twenty times ran once, after the call returned.

---

### Stalls That Don't Look Like Sleeping

Nobody writes `time.sleep` in a coroutine on purpose. The stalls that reach production look like ordinary code:

```python
import hashlib


def derive_key(token: bytes) -> bytes:
    """Stretch a device token the way a login check does."""
    return hashlib.pbkdf2_hmac("sha256", token, b"fleet-salt", 600_000)


async def log_in_driver() -> None:
    """Check one driver's token inside the coroutine."""
    derive_key(b"truck-0042")


positions = {f"truck-{n:04}": (n * 0.01, n * 0.02) for n in range(500)}


async def cached_position(truck: str) -> tuple[float, float]:
    """Return a truck's last known position from memory."""
    return positions[truck]


async def sweep_positions() -> None:
    """Await a million cache lookups."""
    for _ in range(2_000):
        for truck in positions:
            await cached_position(truck)


async def hidden_stalls() -> None:
    """Measure the login check and the cache sweep."""
    await measure("pbkdf2 inline", log_in_driver)
    await measure("a million awaits", sweep_positions)


asyncio.run(hidden_stalls())
# pbkdf2 inline: took 213 ms, worst lag 212.9 ms, heartbeats 1
# a million awaits: took 108 ms, worst lag 107.5 ms, heartbeats 1
```

The 600,000 iterations are what OWASP recommends for PBKDF2 with SHA-256, so this is a correctly written login check that stalls the loop for 213 ms on every call.

The second case is the common mistake: "my loop has an `await` in it, so it yields." It doesn't. `await` on a coroutine runs it right away, in the same step, and only suspends if that coroutine reaches something that isn't ready. `cached_position` never does, so a million awaits ran as one 108 ms step. Tag a function `async` and it doesn't yield anything; only an `await` on a pending future hands the loop back.

The same goes for most libraries written before asyncio: `requests`, synchronous database drivers, `open().read()` on a large file, `json.loads` on a 50 MB body, `socket.getaddrinfo`, and a logging handler that writes to a network socket. Each holds the thread for as long as it runs. Inside an `async def`, the time each one takes is time every other task waits.

---

### Catching the Stall With Debug Mode

asyncio can report slow steps itself. Run with `asyncio.run(main(), debug=True)`, set `PYTHONASYNCIODEBUG=1`, or start Python with `-X dev`, and the loop times each step and logs the ones that take longer than `loop.slow_callback_duration`:

```python
async def load_route(route_id: int) -> None:
    """Fetch a delivery route with a blocking client."""
    time.sleep(0.15)


async def poll_sensors() -> None:
    """Read five sensors, blocking 50 ms each, yielding in between."""
    for _ in range(5):
        time.sleep(0.05)
        await asyncio.sleep(0)


async def dispatch() -> None:
    """Run both jobs concurrently."""
    await asyncio.gather(load_route(7), poll_sensors())


asyncio.run(dispatch(), debug=True)
# Executing <Task finished name='Task-2' coro=<load_route() done, defined
#   at dispatch.py:5> result=None created at ...> took 0.150 seconds
```

The route load is caught. The sensor poll is not, although it blocked the loop for 250 ms in total. The default threshold is 100 ms, and each of its five steps took 50 ms, so none of them qualified. For a service with a 100 ms heartbeat, that default is far too generous. Lower it:

```python
async def dispatch_strict() -> None:
    """Report any step slower than 20 ms, then poll the sensors."""
    asyncio.get_running_loop().slow_callback_duration = 0.02
    await poll_sensors()


asyncio.run(dispatch_strict(), debug=True)
# Executing <Task pending name='Task-6' coro=<dispatch_strict() running
#   at dispatch.py:30> ...> took 0.050 seconds
# ...four more lines like it
```

Now all five steps show up, along with a second gotcha. The report names the task and the line where its *outermost* coroutine is waiting, which here is `await poll_sensors()`, not the `time.sleep` that blocked. It tells you which task to look at, not which line. Name your tasks with `asyncio.create_task(coro, name="sensor-poll")` so the report says something more useful than `Task-6`.

Debug mode records a creation traceback for every task and callback, so keep it to development and tests. In production, the heartbeat probe costs one timer every 10 ms. Export its worst lag as a metric, and you'll see stalls without paying for debug mode.

---

### Moving the Work Off the Loop

`asyncio.to_thread` runs a function on a worker thread from the loop's default thread pool and gives you an awaitable for the result. The coroutine suspends while it waits, so the loop keeps running. The question is what the worker thread does with the GIL:

```python
def checksum(readings: int) -> int:
    """Fold a run of readings into one number, in pure Python."""
    total = 0

    for value in range(readings):
        total = (total * 31 + value) % 1_000_003

    return total


async def log_in_off_loop() -> None:
    """Check the token on a worker thread."""
    await asyncio.to_thread(derive_key, b"truck-0042")


async def checksum_inline() -> None:
    """Fold the readings on the loop's own thread."""
    checksum(3_000_000)


async def checksum_off_loop() -> None:
    """Fold the readings on a worker thread."""
    await asyncio.to_thread(checksum, 3_000_000)


async def threaded() -> None:
    """Compare inline and threaded versions of both jobs."""
    await measure("pbkdf2 to_thread", log_in_off_loop)
    await measure("checksum inline", checksum_inline)
    await measure("checksum to_thread", checksum_off_loop)


asyncio.run(threaded())
# pbkdf2 to_thread: took 212 ms, worst lag 1.1 ms, heartbeats 22
# checksum inline: took 199 ms, worst lag 199.1 ms, heartbeats 1
# checksum to_thread: took 198 ms, worst lag 5.2 ms, heartbeats 15
```

The login check went from a 213 ms stall to about 1 ms of lag, because `hashlib` releases the GIL while it hashes, and the loop thread runs freely beside it. The pure-Python checksum is different. Its thread holds the GIL, and each time the heartbeat's timer fires, the loop thread has to wait for the switch interval, 5 ms by default, before the worker is asked to let go. The result is a lag of 5.2 ms on every beat, and fifteen heartbeats where there should have been twenty. That is much better than 199 ms, but CPU-bound Python code on a thread still slows the loop down.

For pure-Python CPU work, use a process. `loop.run_in_executor` takes any `concurrent.futures` executor, and a `ProcessPoolExecutor` runs the function with its own interpreter and its own GIL:

```python
from concurrent.futures import ProcessPoolExecutor


async def checksum_in_process(pool: ProcessPoolExecutor) -> None:
    """Fold the readings in a worker process."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(pool, checksum, 3_000_000)


async def in_processes(pool: ProcessPoolExecutor) -> None:
    """Start the worker once, then measure."""
    await checksum_in_process(pool)
    await measure("checksum process", lambda: checksum_in_process(pool))


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=2) as pool:
        asyncio.run(in_processes(pool))
# checksum process: took 197 ms, worst lag 0.3 ms, heartbeats 21
```

The lag drops to a millisecond or less, close to an idle loop. The pool is created outside `asyncio.run` because shutting it down waits for the workers, which is itself a blocking call. The cost is moving data: arguments and results are pickled across a pipe, so this pays off when the work is large compared to its inputs. Here the input is one integer. The `__main__` guard keeps it working under the `spawn` and `forkserver` start methods, where each worker imports the module.

---

### The Thread You Can't Cancel

A timeout around `to_thread` cancels the *await*, not the thread:

```python
def export_manifest(started: float) -> str:
    """Write the day's manifest with a slow, blocking client."""
    time.sleep(2)
    print(f"export finished at {time.perf_counter() - started:.2f} s")

    return "manifest.csv"


async def export_with_deadline(started: float) -> None:
    """Give the export half a second."""
    try:
        export = asyncio.to_thread(export_manifest, started)
        await asyncio.wait_for(export, timeout=0.5)
    except TimeoutError:
        print(f"timed out at {time.perf_counter() - started:.2f} s")


started = time.perf_counter()
asyncio.run(export_with_deadline(started))

print(f"asyncio.run returned at {time.perf_counter() - started:.2f} s")
# timed out at 0.50 s
# export finished at 2.00 s
# asyncio.run returned at 2.00 s
```

The coroutine gave up at 0.5 s, but Python has no way to stop a running thread, so the export kept going. `asyncio.run` then waited for the default executor to shut down, and the program exited at 2 s anyway. If the blocking call can hang, give it a timeout of its own, such as a socket timeout or a driver's query timeout. `wait_for` can't stop it.

---

### `await asyncio.sleep(0)` Is a Stopgap

When the CPU work is your own loop, you can split it and hand the loop a turn between pieces. `asyncio.sleep(0)` is a special case that suspends without creating a timer: the task goes to the back of the ready queue, and everything that was waiting runs first.

```python
from functools import partial


async def checksum_in_slices(readings: int, size: int) -> int:
    """Fold readings in slices, giving the loop a turn after each."""
    total = 0

    for first in range(0, readings, size):
        for value in range(first, min(first + size, readings)):
            total = (total * 31 + value) % 1_000_003

        await asyncio.sleep(0)

    return total


async def sliced() -> None:
    """Try slice sizes from coarse to fine."""
    for size in (100_000, 10_000, 100, 10):
        await measure(f"slices of {size:,}",
                      partial(checksum_in_slices, 3_000_000, size))


print(asyncio.run(checksum_in_slices(3_000_000, 10_000))
      == checksum(3_000_000))  # True

asyncio.run(sliced())
# slices of 100,000: took 202 ms, worst lag 18.0 ms, heartbeats 9
# slices of 10,000: took 205 ms, worst lag 2.0 ms, heartbeats 19
# slices of 100: took 288 ms, worst lag 0.3 ms, heartbeats 30
# slices of 10: took 1033 ms, worst lag 1.4 ms, heartbeats 105
```

The result doesn't change, and with slices of 10,000 the lag falls to 2 ms at no extra cost. Go finer and each slice pays for a trip through the loop: slices of 10 made the job five times slower. The right size depends on how long one item takes, so it changes with the machine and the input. It also only works for loops you wrote. You can't put `sleep(0)` inside `pbkdf2_hmac` or `json.loads`. Use it to fix a stall today, and move the work to an executor when you can.

---

### Conclusion

The event loop can't take control away from a task. A coroutine keeps the thread until it awaits something that isn't ready, and a blocking call, a C function that runs for a while, or a chain of awaits that never suspend all keep it for every task. Nothing raises an error. The only symptom is that everything else is late.

Measure it with a heartbeat that records its own lag, and run development builds with debug mode and a `slow_callback_duration` lower than your latency budget. Send blocking I/O and GIL-releasing C calls to `asyncio.to_thread`, send pure-Python CPU work to a process pool, and give every blocking call a timeout of its own, since cancelling the await leaves the thread running.
