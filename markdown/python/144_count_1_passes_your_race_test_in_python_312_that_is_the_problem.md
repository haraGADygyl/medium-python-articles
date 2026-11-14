# `count += 1` Passes Your Race Test in Python 3.12. That Is the Problem

#### The interpreter only switches threads at certain bytecodes, so a racy counter can pass every stress test you throw at it, then lose most of its updates after a one-word change

**By Tihomir Manushev**

*Nov 14, 2026 · 8 min read*

---

The code review comment was short: "Eight threads write `scans += 1` to the same global. Isn't that a race?" The author did the responsible thing and wrote a stress test. Eight threads, two hundred thousand increments each, twenty repetitions, and an assertion that the total came out right. It passed twenty times out of twenty. The reviewer approved the change.

Both people did their jobs, and both took away the wrong lesson. The update *is* a race. It reads the counter, adds one, and writes it back as separate steps, and nothing stops another thread from running in between. The test passed because of where CPython 3.12 checks whether it should hand the GIL to another thread, and that is a detail of the interpreter, not of the code. Change the Python version, swap `len` for `max`, or turn the attribute into a property, and the same line loses more than half of its updates.

This article reproduces the passing test, reads the bytecode to show why it passes, breaks it three ways without touching the `+=`, and ends with what actually makes the update safe. Every number comes from runs on one Linux machine.

---

### The Test That Always Passes

Start with the stress test itself. Two helpers do the bookkeeping: `run_doors` starts the same work on eight threads and waits for them, and `report` repeats a trial and counts how many repetitions lost updates.

```python
import sys
import threading
from collections.abc import Callable

DOORS = 8
TIMES = 200_000
scans = 0


def run_doors(work: Callable[[], None]) -> None:
    """Run the same work on DOORS threads at once and wait for all of them."""
    threads = [threading.Thread(target=work) for _ in range(DOORS)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()


def report(label: str, trial: Callable[[], int], repeats: int = 20) -> None:
    """Repeat a trial that returns lost updates and summarize the damage."""
    losses = [trial() for _ in range(repeats)]
    failed = sum(1 for lost in losses if lost)
    print(f"{label}: {failed}/{repeats} runs lost updates, "
          f"worst {max(losses):,}")


def scan_badges() -> None:
    """Count badge scans at one conference entrance."""
    global scans

    for _ in range(TIMES):
        scans += 1


def lost_scans() -> int:
    """Reset the counter, run every door, and return the missing scans."""
    global scans
    scans = 0
    run_doors(scan_badges)

    return DOORS * TIMES - scans


gil_on = getattr(sys, "_is_gil_enabled", lambda: True)()
build = "" if gil_on else " free-threaded"
report(f"Python {sys.version.split()[0]}{build}", lost_scans)
# Python 3.12.3: 0/20 runs lost updates, worst 0
```

Each run expects 1,600,000 scans, and on Python 3.12 each run gets exactly that. `sys._is_gil_enabled()` arrived in 3.13, so the `getattr` default keeps the label working on older interpreters. Now run the same file under other interpreters:

```text
Python 3.9.25:  20/20 runs lost updates, worst 815,434
Python 3.10.22:  0/20 runs lost updates, worst 0
Python 3.11.14:  0/20 runs lost updates, worst 0
Python 3.12.3:   0/20 runs lost updates, worst 0
Python 3.13.9:   0/20 runs lost updates, worst 0
Python 3.14.0:   0/20 runs lost updates, worst 0
Python 3.14.8 free-threaded: 20/20 runs lost updates, worst 1,362,780
```

The worst-case counts move from one run to the next, but the pattern of passes and failures never did. On 3.9 the test fails on every run, and so does the free-threaded build of 3.14, which runs without a GIL and lost 85% of the scans in its worst run. The source file is the same, so the test is measuring the interpreter, not the code.

---

### Three Bytecodes and a Gap

The `dis` module shows what the loop body compiles to on 3.12:

```python
import dis

dis.dis(scan_badges)
# ...
#  38 LOAD_GLOBAL      4 (scans)
#  48 LOAD_CONST       1 (1)
#  50 BINARY_OP       13 (+=)
#  54 STORE_GLOBAL     2 (scans)
#  56 JUMP_BACKWARD   13 (to 32)
# ...
```

That is a **read-modify-write**: load the current value, compute a new one, store it. If another thread runs between `LOAD_GLOBAL` and `STORE_GLOBAL`, both threads load the same number, both add one, and one of the two increments is lost. The gap is there on every version of Python. What changed between versions is whether the interpreter will ever switch threads inside it.

A thread that wants the GIL doesn't take it by force. It waits for the switch interval (5 ms by default), then sets a flag called the **eval breaker** asking the running thread to let go. The running thread only reads that flag at certain instructions. Python 3.9 read it between most instructions, so a switch could land right after `LOAD_GLOBAL`, and on a busy counter it did, many times a second. Python 3.10 narrowed the checks to jumps and calls. In 3.12's source the checks sit at `RESUME` (the first instruction of every function call), at `JUMP_BACKWARD` (the bottom of every loop), and after most calls into C functions.

None of those appear between the load and the store above. On a GIL build of 3.10 through 3.14, a thread can only be switched out at `JUMP_BACKWARD`, after the store has already happened. The race is real, but the interpreter never takes the opening. Remove the GIL and both threads run truly in parallel, and the gap is open on every iteration.

This also explains a debugging trick that fails here. Lowering `sys.setswitchinterval` to one microsecond makes threads ask for the GIL far more often, and it still produced 0/20 on 3.12. Asking more often changes nothing when the running thread never checks inside the gap.

---

### Same `+=`, Three Ways to Lose

The protection lasts only while nothing between the load and the store runs a check. Here are three ordinary edits that add one.

**A builtin call.** Counting a batch instead of a single badge, on 3.12:

```python
batch = [1]


def scan_with_len() -> None:
    """Add the size of each batch."""
    global scans

    for _ in range(TIMES):
        scans += len(batch)


def scan_with_max() -> None:
    """Add the largest entry of each batch."""
    global scans

    for _ in range(TIMES):
        scans += max(batch)


def lost_with(work: Callable[[], None]) -> int:
    """Run any scanning function on every door and return lost scans."""
    global scans
    scans = 0
    run_doors(work)

    return DOORS * TIMES - scans


report("len", lambda: lost_with(scan_with_len))
report("max", lambda: lost_with(scan_with_max))
# len: 0/20 runs lost updates, worst 0
# max: 20/20 runs lost updates, worst 1,217,477
```

Both calls run after `LOAD_GLOBAL` reads the counter and before `STORE_GLOBAL` writes it. The specializing interpreter turns `len(batch)` into a dedicated instruction that skips the eval-breaker check, while `max` goes through the general builtin path, which checks after the C function returns. So `len` is safe on 3.11 and later, but not on 3.10, where every call checks. `max` loses updates on every version. Whether this line is correct depends on which builtin you call and which interpreter optimizations happen to apply to it.

**A property.** A refactor hides the counter behind a property to add validation later:

```python
class Gate:
    """A turnstile whose count goes through a property."""

    def __init__(self) -> None:
        self._scans = 0

    @property
    def scans(self) -> int:
        return self._scans

    @scans.setter
    def scans(self, value: int) -> None:
        self._scans = value


def lost_at_gate() -> int:
    """Increment a property from every door and return lost scans."""
    gate = Gate()

    def scan() -> None:
        for _ in range(TIMES):
            gate.scans += 1

    run_doors(scan)

    return DOORS * TIMES - gate.scans


report("property", lost_at_gate)
# property: 20/20 runs lost updates, worst 1,079,908
```

`gate.scans += 1` reads like it did before. But the setter is a Python function, and every call starts with `RESUME`. That check runs after the new value is computed and before `self._scans` is written: a switch point in the middle of the gap.

**A dictionary key.** Counting per entrance with a frozen dataclass as the key:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Door:
    """An entrance, hashable so it can key a dict."""

    hall: str
    number: int


def lost_by_key(key: object) -> int:
    """Increment one dict entry from every door and return lost scans."""
    tally = {key: 0}

    def scan() -> None:
        for _ in range(TIMES):
            tally[key] += 1

    run_doors(scan)

    return DOORS * TIMES - tally[key]


report("str key", lambda: lost_by_key("north-1"))
report("dataclass key", lambda: lost_by_key(Door("north", 1)))
# str key: 0/20 runs lost updates, worst 0
# dataclass key: 20/20 runs lost updates, worst 1,278,638
```

A string caches its hash and hashes in C. The dataclass generates `__hash__` as Python code, and the store into the dict calls it, which puts another `RESUME` between the read and the write.

The losses are huge, not a handful, for a reason worth knowing. A thread switched out mid-gap holds a stale value for as long as the other seven threads run, which can be several switch intervals. When it resumes, it writes that stale value back and erases everything they counted in the meantime.

---

### What Actually Makes It Safe

A lock turns the three steps into one critical section:

```python
class LockedGate(Gate):
    """A gate whose increments hold a lock across read and write."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    def scan(self) -> None:
        """Record one scan atomically."""
        with self._lock:
            self.scans += 1


def lost_locked(bypass: bool = False) -> int:
    """Use the locked method; optionally let one door skip the lock."""
    gate = LockedGate()

    def scan() -> None:
        for _ in range(TIMES):
            gate.scan()

    def careless() -> None:
        for _ in range(TIMES):
            gate.scans += 1

    threads = [threading.Thread(target=scan) for _ in range(DOORS - 1)]
    threads.append(threading.Thread(target=careless if bypass else scan))

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    return DOORS * TIMES - gate.scans


report("locked", lost_locked)
report("one door skips it", lambda: lost_locked(bypass=True))
# locked: 0/20 runs lost updates, worst 0
# one door skips it: 17/20 runs lost updates, worst 23
```

The first result holds on every interpreter in the table, the free-threaded one included, because it no longer depends on where switches can happen. The second shows the gotcha: `threading.Lock` is **advisory**. It doesn't guard the attribute, only the code that remembers to take it. Seven careful doors and one careless one lost updates in 17 runs out of 20. The worst run was short by only 23 scans out of 1.6 million, and that makes it worse: a total that is almost right is the kind of bug that survives for months. Keep the counter behind a single method so there is no unlocked spelling of the write.

The lock has a price. On one thread, 1.6 million locked increments took 0.57 s against 0.20 s for the bare property, so each acquire and release roughly triples the cost of an increment that is still O(1). Contention is the real bill: with eight threads fighting over the lock, the same work took 5.26 s against 0.30 s unlocked, because the threads spend their time handing the lock and the GIL back and forth instead of counting. If the threads don't need to see a running total, skip the sharing entirely:

```python
from concurrent.futures import ThreadPoolExecutor


def count_door(times: int) -> int:
    """Count one entrance privately and return its total."""
    local = 0

    for _ in range(times):
        local += 1

    return local


with ThreadPoolExecutor(DOORS) as pool:
    total = sum(pool.map(count_door, [TIMES] * DOORS))

print(f"{total:,}")  # 1,600,000
```

Each thread owns its counter, so there is nothing to race on, and the merge happens once, after the work is done. It finished in 0.05 s, a hundred times faster than the locked version.

---

### Writing a Race Test That Can Fail

A stress test that cannot fail tells you nothing. Three habits make one useful.

Run it on the free-threaded build. `uv python install 3.14t` gets you one, and on it the plain global counter failed every run. If the code is meant to be safe without the GIL, that is the interpreter to prove it on. `sys._is_gil_enabled()` tells you which mode a test actually ran in, and setting `PYTHON_GIL=1` on the same binary dropped the failures to 0/20, which shows that the GIL was what hid them.

Read the bytecode of a shared update before trusting it. If anything between the load and the store can call a function, through a property, a `__hash__`, an `__iadd__`, or a builtin that isn't specialized, assume a switch can land there.

Treat "it passed" as information about this interpreter, not about the code. The next minor version moves check points around as the specializing interpreter grows, which is exactly how `len` and `max` ended up on different sides of the line.

---

### Conclusion

`count += 1` is three steps with a gap between the read and the write. A GIL build of CPython 3.10 or later happens never to switch threads inside that gap for a plain global, so the race test passes. Python 3.9 and the free-threaded builds do switch there, and so does 3.12 itself as soon as a property, a Python `__hash__`, or the wrong builtin adds a check point.

Guard shared updates with a lock that every writer takes, or give each thread its own counter and merge at the end. Then run the race test somewhere it can fail: on a free-threaded build, where an unguarded counter loses updates on every run.
