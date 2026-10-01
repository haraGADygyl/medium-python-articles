# Four `contextlib` Helpers That Delete Boilerplate You Are Still Writing

#### `suppress`, `closing`, `nullcontext` and `redirect_stdout` each replace a block of defensive code, and each one has an edge that cuts

**By Tihomir Manushev**

*Oct 1, 2026 · 8 min read*

---

Every codebase has them. A `try`/`except KeyError: pass` around a dictionary delete. A `finally: connection.close()`. A function body written twice because sometimes it opens the file and sometimes the caller passes one in. A `sys.stdout = buffer` swap whose restore line is missing from the error path. Each one is a few lines of defensive code, written by hand and slightly differently every time.

`contextlib` has a ready-made context manager for each of them. Most Python developers know the names. Fewer know where each helper stops doing what its name promises. `suppress` abandons the rest of its block. `closing` is needed even on objects that already support `with`. `nullcontext` turns out to express ownership, not just "do nothing". And `redirect_stdout` captures less output than you expect while reaching further than you want.

The examples come from a podcast-hosting backend: episodes waiting to upload, a catalogue in SQLite, transcripts streamed line by line, and a legacy helper that can only `print`.

---

### `suppress` Ends the Block at the First Raise

`contextlib.suppress(*exceptions)` is a context manager whose `__exit__` returns `True` when the exception matches one of the types you named. That makes it a visible, named version of `try`/`except`/`pass`. The trap is in what happens to the rest of the block:

```python
from contextlib import suppress

pending_uploads = {"ep-101": "pilot.mp3"}
published: list[str] = []

with suppress(KeyError):
    del pending_uploads["ep-099"]
    published.append("ep-099")

print(published)  # []
```

The `del` raises `KeyError` on the first line of the block. `suppress` catches it at the *end* of the block, so the `append` never runs. A `try`/`except` behaves exactly the same way, but the shape of a `with` statement invites you to wrap a whole step. The code reads as "do this, ignoring `KeyError`" when what it does is "do this until the first `KeyError`, then silently skip the rest."

The fix is a habit: one statement inside `suppress`, and only the one that is allowed to fail.

```python
from contextlib import suppress

pending_uploads = {"ep-101": "pilot.mp3"}
published: list[str] = []

for episode_id in ("ep-099", "ep-101"):
    with suppress(KeyError):
        del pending_uploads[episode_id]
    published.append(episode_id)

print(published, pending_uploads)  # ['ep-099', 'ep-101'] {}
```

Two smaller rules. `suppress()` with no arguments suppresses nothing. And it never catches a type you didn't name, so `KeyboardInterrupt` still gets through unless you list it.

---

### `suppress` and Exception Groups (3.12)

`asyncio.TaskGroup` doesn't raise the exceptions its tasks raised. It raises an `ExceptionGroup` that wraps them. Before Python 3.12, `suppress(TimeoutError)` didn't match that group at all, because an `ExceptionGroup` is not a `TimeoutError`, so the whole group propagated. Since 3.12, `suppress` splits the group. It drops the leaves that match, and if anything is left, it re-raises the rest in a new group:

```python
import asyncio
from contextlib import suppress


async def ping_mirror(hostname: str, outcome: str) -> str:
    """Pretend to health-check one CDN mirror for the audio files."""
    await asyncio.sleep(0.01)
    if outcome == "slow":
        raise TimeoutError(f"{hostname} took too long")
    if outcome == "gone":
        raise ConnectionRefusedError(f"{hostname} refused the connection")
    return hostname


async def check_mirrors(plan: dict[str, str]) -> None:
    """Ignore slow mirrors; let every other failure through."""
    with suppress(TimeoutError):
        async with asyncio.TaskGroup() as group:
            for hostname, outcome in plan.items():
                group.create_task(ping_mirror(hostname, outcome))
    print("mirror check finished")


asyncio.run(check_mirrors({"fra-1": "ok", "sfo-2": "slow", "sin-1": "slow"}))
# mirror check finished

try:
    asyncio.run(check_mirrors({"fra-1": "slow", "sfo-2": "gone"}))
except* ConnectionRefusedError as remaining:
    print([str(error) for error in remaining.exceptions])
# ['sfo-2 refused the connection']
```

In the first run, both failures are timeouts, so nothing is left and the block completes. In the second run, the timeout from `fra-1` is dropped and the refused connection from `sfo-2` arrives in a fresh group, ready for `except*`. This is the behavior you want from a health check: slow mirrors are noise, but a dead mirror is news. On Python 3.11, the same code lets the whole group through, timeouts included.

---

### `closing` Is for Objects Whose `__exit__` Does the Wrong Thing

`closing(thing)` is a context manager whose `__exit__` calls `thing.close()`. The obvious use is an object that has a `close()` method but no context-manager protocol at all. The less obvious use matters more: objects that *do* support `with`, but whose `__exit__` does something other than close. `sqlite3.Connection` is the classic case:

```python
import sqlite3
from contextlib import closing

catalogue = sqlite3.connect(":memory:")
with catalogue:
    catalogue.execute("CREATE TABLE episodes (slug TEXT, minutes INTEGER)")
    catalogue.execute("INSERT INTO episodes VALUES ('pilot', 42)")

print(catalogue.execute("SELECT count(*) FROM episodes").fetchone())  # (1,)

with closing(sqlite3.connect(":memory:")) as scratch:
    scratch.execute("CREATE TABLE drafts (slug TEXT)")

try:
    scratch.execute("SELECT * FROM drafts")
except sqlite3.ProgrammingError as error:
    print(error)  # Cannot operate on a closed database.
```

The connection's `__exit__` commits the transaction, or rolls it back on an exception. It doesn't close anything, so the `SELECT` after the block still works. In a long-running service, every request that does `with sqlite3.connect(path) as conn:` leaves a connection and its file handle open until the garbage collector gets to them. `closing` gives you the meaning you assumed `with` had, and the second connection really is closed afterward.

When you want both behaviors, nest them. The outer `closing` owns the connection's lifetime, and the inner `with` owns the transaction:

```python
import sqlite3
from contextlib import closing

with closing(sqlite3.connect(":memory:")) as catalogue:
    with catalogue:
        catalogue.execute("CREATE TABLE episodes (slug TEXT, minutes INTEGER)")
        catalogue.executemany(
            "INSERT INTO episodes VALUES (?, ?)",
            [("pilot", 42), ("deep-copy", 37)],
        )
    total = catalogue.execute("SELECT sum(minutes) FROM episodes").fetchone()
    print(total)  # (79,)
```

Generators are the other case where `closing` pays for itself. A generator that wraps a resource in `try`/`finally` releases it only when it runs to the end or gets closed:

```python
from collections.abc import Iterator
from contextlib import closing


def stream_transcript(slug: str) -> Iterator[str]:
    """Yield transcript lines while holding a (pretend) file handle open."""
    print(f"open transcript for {slug}")
    try:
        for line_number in range(1, 1_000):
            yield f"{slug} line {line_number}"
    finally:
        print(f"close transcript for {slug}")


pilot_lines = stream_transcript("pilot")
for line in pilot_lines:
    break
print("loop done, handle still open")
# open transcript for pilot
# loop done, handle still open

with closing(stream_transcript("deep-copy")) as episode_lines:
    for line in episode_lines:
        break
print("block done")
# open transcript for deep-copy
# close transcript for deep-copy
# block done
# close transcript for pilot   <- only at interpreter shutdown
```

Breaking out of the first loop leaves the generator paused at its `yield`, and its `finally` waits for the garbage collector. In CPython that happens when the last reference disappears, which here is interpreter shutdown. On PyPy it happens whenever the collector runs. `closing` calls `gen.close()` at the end of the block. That raises `GeneratorExit` at the paused `yield`, so the `finally` runs right away. For async generators, `contextlib.aclosing` (added in 3.10) does the same job.

---

### `nullcontext` Expresses Ownership

A function that accepts either a path or an open stream has two different jobs. If it opens the path, it owns the file and must close it. If the caller passes in a stream, closing it would break the caller, and closing `sys.stdout` breaks every `print` that follows. The hand-written version branches twice: once to open, and once more in a `finally` to decide whether to close. `nullcontext` reduces that to one branch:

```python
import io
import sys
from contextlib import nullcontext
from typing import TextIO

EPISODES = [("pilot", 42), ("deep-copy", 37)]


def export_feed(destination: str | TextIO) -> None:
    """Write the episode feed to a path we own or a stream the caller owns."""
    if isinstance(destination, str):
        target = open(destination, "w", encoding="utf-8")
    else:
        target = nullcontext(destination)
    with target as feed:
        for slug, minutes in EPISODES:
            feed.write(f"{slug},{minutes}\n")


buffer = io.StringIO()
export_feed(buffer)
print(buffer.closed, repr(buffer.getvalue()))
# False 'pilot,42\ndeep-copy,37\n'

export_feed(sys.stdout)
# pilot,42
# deep-copy,37
print("stdout still usable")  # stdout still usable

export_feed("/tmp/feed.csv")
with open("/tmp/feed.csv", encoding="utf-8") as saved:
    print(saved.readline().strip())  # pilot,42
```

`nullcontext(enter_result)` returns `enter_result` from `__enter__` and does nothing in `__exit__`. The `with` statement now encodes who owns what. The branch that owns the file gets a real manager. The branch that borrows a stream gets a manager that leaves it alone. The writing loop exists once. Afterward, the caller's buffer is still open and `sys.stdout` still prints.

The same idea handles optional locking. A component that is sometimes shared between threads and sometimes not can pick its guard once, at construction:

```python
import threading
from contextlib import nullcontext


class PlayCounter:
    """Counts plays per episode, locking only when shared across threads."""

    def __init__(self, shared: bool) -> None:
        self.plays: dict[str, int] = {}
        self.guard = threading.Lock() if shared else nullcontext()

    def record(self, slug: str) -> None:
        with self.guard:
            self.plays[slug] = self.plays.get(slug, 0) + 1


solo = PlayCounter(shared=False)
solo.record("pilot")
print(solo.plays, type(solo.guard).__name__)  # {'pilot': 1} nullcontext
```

`record` contains no `if self.shared` check, and the single-threaded instance pays only for a pair of empty method calls. Since 3.10, `nullcontext` also works with `async with`, so the same trick covers an optional `asyncio.Lock`.

---

### `redirect_stdout` Captures Less Than You Think

For code you can't change, capturing what it prints is often the only way to get its output:

```python
import io
from contextlib import redirect_stdout


def legacy_render_show_notes(slug: str, minutes: int) -> None:
    """A third-party helper that can only print."""
    print(f"== {slug} ==")
    print(f"runtime: {minutes} min")


with redirect_stdout(io.StringIO()) as captured:
    legacy_render_show_notes("pilot", 42)

notes = captured.getvalue()
print(notes.splitlines())  # ['== pilot ==', 'runtime: 42 min']
```

`redirect_stdout` swaps `sys.stdout` for your target, returns the target from `__enter__`, and puts the original back on exit, including when the block raises. It's tidy, and it is also much narrower and much wider than it looks:

```python
import io
import logging
import os
import subprocess
import threading
from contextlib import redirect_stderr, redirect_stdout

uploads_log = logging.getLogger("uploads")
uploads_log.addHandler(logging.StreamHandler())
uploads_log.propagate = False


def heartbeat() -> None:
    """Another thread, unrelated to the capture, printing at the wrong time."""
    print("heartbeat from worker thread")


captured_out = io.StringIO()
with redirect_stdout(captured_out):
    print("python-level print")
    os.write(1, b"raw write to fd 1\n")  # goes to the terminal
    subprocess.run(["echo", "child output"], check=True)  # terminal too
    worker = threading.Thread(target=heartbeat)
    worker.start()
    worker.join()

captured_err = io.StringIO()
with redirect_stderr(captured_err):
    uploads_log.warning("upload retried")  # goes to the real stderr

print(captured_out.getvalue().splitlines())
# ['python-level print', 'heartbeat from worker thread']
print(repr(captured_err.getvalue()))  # ''
```

The narrow part: it replaces the Python-level object named `sys.stdout`. Anything that writes to file descriptor 1 bypasses it. That includes `os.write`, C extensions that call `printf`, and child processes, which inherit the descriptor rather than the Python object. Capturing those needs `os.dup2` or `subprocess.run(capture_output=True)`. Anything that grabbed a reference before the swap also keeps the old stream. A `logging.StreamHandler()` stores `sys.stderr` when you construct it, so `redirect_stderr` captures nothing from it.

The wide part: `sys.stdout` is process-global. The heartbeat thread has nothing to do with the capture, yet its line landed in the buffer. In a threaded web server, two overlapping redirects mix their output together, and each one restores whatever stream it saw when it started, which may be the other one's buffer. That's why `redirect_stdout` belongs at the edges of a program: scripts, command-line wrappers, quick experiments. It doesn't belong in library code. If you own the function, give it a `file` parameter and use the `nullcontext` pattern above.

---

### Habits That Keep Them Honest

All four helpers are tiny classes. Their cost is one `__enter__`/`__exit__` call pair, which is constant and negligible next to the I/O they usually guard. The risk lies in how they read, not in how fast they run.

Keep exactly one statement inside `suppress`, and name the narrowest exception that statement can raise. A block of five lines under `suppress(Exception)` is a bug report that nobody will ever file.

Reach for `closing` whenever lifetime matters more than whatever the object's own `__exit__` does. SQLite connections and generators that hold handles are the two cases that show up in real code over and over.

Use `nullcontext` whenever a function sometimes owns a resource and sometimes borrows it. It also covers a lock that only some instances need.

Keep `redirect_stdout` at the outermost layer of a program. In tests, prefer your framework's capture. pytest's `capfd` works at the file-descriptor level, so it also catches what `redirect_stdout` misses.

---

### Conclusion

Each of these helpers replaces a block of defensive code with one line that says what you meant. Each also has a limit. `suppress` ends its block at the first matching exception, and since 3.12 it pulls matching exceptions out of exception groups. `closing` is what to use when an object's `__exit__` commits a transaction instead of closing anything. `nullcontext` lets a single `with` statement cover both owned and borrowed resources. `redirect_stdout` captures only Python-level writes, and it captures them from every thread in the process. Before you write the next `try`/`finally`, check whether `contextlib` already has it.
