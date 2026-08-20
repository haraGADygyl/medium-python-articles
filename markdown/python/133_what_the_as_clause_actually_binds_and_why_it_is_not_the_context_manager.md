# What the `as` Clause Actually Binds — and Why It Is Not the Context Manager

#### The object after `with` and the name after `as` are two different things. `open()` hides that fact, and the bug surfaces the first time you write a manager of your own.

**By Tihomir Manushev**

*Aug 20, 2026 · 8 min read*

---

Almost every Python developer learns the `with` statement through a single example:

```python
with open("readings.csv", encoding="utf-8") as data_file:
    header = data_file.readline()
```

From that one line, a reasonable person concludes that `data_file` *is* the context manager — the thing whose setup and teardown the `with` statement controls. It is a natural reading, and it is wrong. `data_file` is whatever `__enter__` chose to hand back, and the file object returns itself only because that happens to be convenient for files.

The distinction stays invisible until you write a context manager whose `__enter__` returns something more useful than `self` — and then a whole class of confusing behaviour appears at once. Teardown seems to fire on the wrong object. A name you expected to be `None` outlives the block. An `as` target silently becomes `None`.

What follows is the exact sequence Python runs at both ends of a `with` block, why the object bound by `as` is a separate design decision from the manager itself, and the two mistakes that decision invites.

---

### The Protocol Is Two Methods and a Return Value

A context manager is any object implementing `__enter__` and `__exit__`. Python calls `__enter__` when control reaches the top of the block, and `__exit__` when control leaves it by any route. A manager that narrates both makes the ordering concrete:

```python
from types import TracebackType


class TracedContext:
    """A context manager that narrates every step of the protocol."""

    def __enter__(self) -> str:
        print("  __enter__ called on TracedContext")
        return "the value __enter__ returned"

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        print(f"  __exit__ called on {type(self).__name__}")


manager = TracedContext()
print("before the block")
with manager as bound_name:
    print(f"  inside the block, bound_name = {bound_name!r}")
    print(f"  bound_name is manager? {bound_name is manager}")
print("after the block")
```

```
before the block
  __enter__ called on TracedContext
  inside the block, bound_name = 'the value __enter__ returned'
  bound_name is manager? False
  __exit__ called on TracedContext
after the block
```

Three facts fall out of that trace. Python evaluates the expression after `with` to get the manager. It calls `__enter__` on that manager and binds the **return value** — not the manager — to the name after `as`. And when the block ends, it calls `__exit__` on the manager again, not on whatever `as` captured.

That last point is the one worth committing to memory. The manager and the bound name can be entirely unrelated objects, and teardown always belongs to the manager. `bound_name` here is a plain string with no `__exit__` at all, and the block still tears down correctly.

The three parameters on `__exit__` carry information about an exception that escaped the block, or three `None`s when the block finished cleanly. What `__exit__` does with them — and what its return value means — is a large enough subject to deserve its own treatment; for now, note only that the signature is fixed and that Python calls the method either way.

---

### Why `open()` Taught You the Wrong Lesson

File objects blur the distinction because `TextIOWrapper.__enter__` returns `self`. The manager and the bound name really are the same object there:

```python
import tempfile
from pathlib import Path

scratch = Path(tempfile.gettempdir()) / "seeing_conditions.txt"
scratch.write_text("clear\n")

handle = open(scratch, encoding="utf-8")
with handle as text_file:
    print(f"as bound the manager itself? {text_file is handle}")  # True
print(f"still bound after the block, but closed: {text_file.closed}")  # True

scratch.unlink()
```

Returning `self` is a perfectly good choice for a file — there is nothing more useful to hand back. But it means the canonical teaching example is precisely the case where the two roles collapse into one, which is why the model most developers carry around does not survive contact with a manager that makes the other choice.

---

### Handing Back Something Better Than `self`

Returning a different object is not a trick; it is often the better design. It lets the manager keep its lifecycle machinery private and hand the block a narrow, purpose-built handle.

Consider an automated telescope. The session owns the hardware — unparking the mount, parking it again no matter how the night ends. What the code inside the block actually wants is somewhere to record exposures:

```python
from dataclasses import dataclass, field
from types import TracebackType


@dataclass
class ExposureLog:
    """Records the frames captured during a single observing session."""

    frames: list[tuple[str, float]] = field(default_factory=list)

    def capture(self, target: str, seconds: float) -> None:
        """Record one exposure against a catalogue target."""
        self.frames.append((target, seconds))

    @property
    def total_seconds(self) -> float:
        return sum(seconds for _, seconds in self.frames)


class ObservingSession:
    """Opens the dome, hands back a log, and always parks the mount."""

    def __init__(self, mount_name: str) -> None:
        self.mount_name = mount_name
        self.log = ExposureLog()
        self.is_parked = False

    def __enter__(self) -> ExposureLog:
        print(f"unparking {self.mount_name}")
        return self.log

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.is_parked = True
        print(f"parking {self.mount_name} after {self.log.total_seconds:.0f}s of exposure")
```

Using it makes the separation obvious:

```python
session = ObservingSession("Ridgeline-14")

with session as tonight:
    tonight.capture("NGC 7000", 120.0)
    tonight.capture("M31", 300.0)
    print(f"  as bound a {type(tonight).__name__}")       # ExposureLog
    print(f"  the manager is a {type(session).__name__}")  # ObservingSession

print(f"mount parked: {session.is_parked}")               # True
print(f"frames still readable: {tonight.frames}")
```

```
unparking Ridgeline-14
  as bound a ExposureLog
  the manager is a ObservingSession
parking Ridgeline-14 after 420s of exposure
mount parked: True
frames still readable: [('NGC 7000', 120.0), ('M31', 300.0)]
```

The block never touches the mount, cannot accidentally re-park it, and gets an object whose entire API is the four lines of `ExposureLog`. That is the argument for returning something other than `self`: the `as` target becomes a capability you deliberately grant, rather than the whole manager with all its internals exposed.

The same pattern is why `sqlite3` connections hand a transaction context back, and why a test harness might yield a recorder rather than the harness itself.

The indirection costs nothing worth measuring. A `with` block compiles to a `BEFORE_WITH` opcode plus the two method calls, and since Python 3.11's zero-cost exception handling, the implicit `try`/`finally` adds no runtime overhead on the path where nothing raises — the unwinding tables are consulted only when an exception actually propagates. Two attribute lookups and two calls per block is the entire price, which is why wrapping even a tight loop body in a context manager is a readability decision rather than a performance one.

---

### `with` Does Not Create a Scope

Look at the final line of that output again. After the block ends, `tonight` is still bound and its frames are still readable.

This surprises people arriving from languages where a block introduces a scope. In Python, only functions, classes, comprehensions, and modules create scopes — `with`, `if`, `for`, and `while` do not. A name bound by `as` behaves like any other local: it outlives the statement that created it.

That is genuinely useful. Collecting a result inside a `with` block and reading it afterwards needs no `nonlocal` dance and no pre-declaration. But it carries a sharp edge, visible in the file example earlier: after the block, `text_file` is still bound to a perfectly real object that happens to be closed. The name surviving does not mean the resource survived. Reading from it raises `ValueError: I/O operation on closed file`, and the traceback points at a line where the variable looks entirely valid.

The rule to carry: `as` binds a name with ordinary function scope, and `__exit__` decides whether the object behind that name is still worth anything.

---

### The Gotcha: `__enter__` That Returns Nothing

The most common bug in a hand-written context manager is a missing `return`:

```python
class MissingReturn:
    """__enter__ falls off the end, so it returns None."""

    def __enter__(self) -> None:
        print("  setting up")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        print("  tearing down")


with MissingReturn() as nothing:
    print(f"  as bound: {nothing!r}")  # None
```

Nothing raises. Setup runs, teardown runs, and `as` quietly binds `None` — because a function that falls off its end returns `None`, and `__enter__` is just a function. The failure surfaces later as `AttributeError: 'NoneType' object has no attribute ...` somewhere in the block, pointing nowhere near the actual mistake.

Two habits prevent it. Annotate `__enter__` with its real return type, so a type checker flags the mismatch before runtime. And when the manager has nothing meaningful to offer, `return self` — it costs one line and makes the `as` target useful rather than a trap. Omit the `as` clause entirely when you truly do not need the value; it has always been optional.

---

### Entering Several Managers at Once

Since Python 3.10, parentheses let you enter several managers in one statement, each with its own `as` target, across as many lines as readability wants. A manager that announces itself makes the ordering visible:

```python
class Stage:
    """Announces its own entry and exit so ordering is visible."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __enter__(self) -> str:
        print(f"enter {self.label}")
        return self.label.upper()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        print(f"exit  {self.label}")


with (
    Stage("dome") as dome_handle,
    Stage("camera") as camera_handle,
    Stage("guider") as guider_handle,
):
    print(f"  bound: {dome_handle}, {camera_handle}, {guider_handle}")
```

```
enter dome
enter camera
enter guider
  bound: DOME, CAMERA, GUIDER
exit  guider
exit  camera
exit  dome
```

Managers enter left to right and exit right to left. That LIFO ordering is not cosmetic — it is what makes the form safe, because a manager can depend on everything opened before it and still be torn down before its dependencies are. The statement is exactly equivalent to nesting the blocks, so a failure partway through entry still unwinds whatever already entered.

When the number of managers is not known until runtime, this syntax cannot help — that is what `contextlib.ExitStack` exists for.

---

### Conclusion

The `with` statement runs a protocol with two halves that most code never has to separate: the **manager**, which owns setup and teardown, and the **value**, which `__enter__` returns for the block to work with. `open()` returns `self` and fuses the two, which is why the distinction feels invented until the first time it bites.

Keep three things straight. `as` binds whatever `__enter__` returns, which may be an object with no relationship to the manager. `__exit__` is always invoked on the manager, whatever `as` captured. And the name that `as` creates has ordinary function scope, outliving the block along with any object that the teardown has already rendered useless.

Once the two roles are distinct in your head, `__enter__`'s return value stops being an accident and becomes a design decision — the narrow handle you hand the block, chosen deliberately, instead of the whole machine.
