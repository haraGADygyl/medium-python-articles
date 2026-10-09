# Python's `else` Belongs on Loops and `try` Too — and It Does Not Mean "Otherwise"

#### On `for`, `while` and `try`, the `else` block runs when nothing went wrong, which makes it read like "then" and lets you delete your flag variables

**By Tihomir Manushev**

*Oct 9, 2026 · 8 min read*

---

Most Python developers have written `found = False` above a loop, flipped it to `True` before a `break`, and tested it with `if not found:` afterwards. It works, so it lasts. Python has a built-in way to do the same thing, but the keyword for it puts people off: `else`, attached to the loop itself.

The keyword is badly named. After `if`, `else` means "otherwise". After `for`, `while` and `try` it means close to the opposite: "then, if the block finished without being cut short." People who know the feature exists still misread it, and code reviewers are suspicious of it. When it's used well, though, it removes a flag variable and a whole class of bugs that come with flags.

This article covers what `else` does on each of the three statements, which jumps skip it, the indentation mistake that changes its meaning entirely, and when an ordinary function with `return` is the better choice. The examples come from a bike-share dispatcher that assigns riders to docking stations and processes a live feed of bike counts.

---

### The Flag That Breaks on the Second Group

Here's the dispatcher with a flag. Groups of riders want to ride together, so each group needs a station with enough free bikes. Each group goes to the first station that can serve it, or onto a waitlist if none can:

```python
from dataclasses import dataclass


@dataclass
class Station:
    """One bike-share docking station and its live bike count."""

    name: str
    free_bikes: int
    renting: bool = True

    def can_serve(self, riders: int) -> bool:
        """Say whether this station can hand out bikes to a whole group."""
        return self.renting and self.free_bikes >= riders


@dataclass
class RideGroup:
    """A group that wants to ride together, booked under one leader."""

    leader: str
    riders: int


def dispatch_with_flag(
    groups: list[RideGroup], stations: list[Station]
) -> tuple[dict[str, str], list[str]]:
    """Seat each group at the first station that fits, or waitlist it."""
    assignments: dict[str, str] = {}
    waitlist: list[str] = []
    found = False
    for group in groups:
        for station in stations:
            if station.can_serve(group.riders):
                station.free_bikes -= group.riders
                assignments[group.leader] = station.name
                found = True
                break
        if not found:
            waitlist.append(group.leader)
    return assignments, waitlist


def morning_stations() -> list[Station]:
    """Build a fresh copy of the 8 a.m. station snapshot."""
    return [
        Station("Harbour Gate", 2),
        Station("Old Mill", 5, renting=False),
        Station("Clock Square", 4),
    ]


groups = [RideGroup("Vesna", 3), RideGroup("Radko", 6), RideGroup("Ilian", 2)]
print(dispatch_with_flag(groups, morning_stations()))
# ({'Vesna': 'Clock Square', 'Ilian': 'Harbour Gate'}, [])
```

Radko's group of six has disappeared. No station can serve them, yet they aren't on the waitlist either. The flag was reset once, before the outer loop, instead of once per group. Vesna's booking set it to `True`, and it stayed `True` for every group after her. This is the usual way a flag goes wrong. It's state that lives outside the loop it describes, so its lifetime has to be managed by hand, and nothing warns you when you get it wrong.

Now the same function with `else` on the inner loop:

```python
def dispatch(
    groups: list[RideGroup], stations: list[Station]
) -> tuple[dict[str, str], list[str]]:
    """Seat each group at the first station that fits, or waitlist it."""
    assignments: dict[str, str] = {}
    waitlist: list[str] = []
    for group in groups:
        for station in stations:
            if station.can_serve(group.riders):
                station.free_bikes -= group.riders
                assignments[group.leader] = station.name
                break
        else:  # no break
            waitlist.append(group.leader)
    return assignments, waitlist


print(dispatch(groups, morning_stations()))
# ({'Vesna': 'Clock Square', 'Ilian': 'Harbour Gate'}, ['Radko'])
```

The `else` belongs to the inner `for`, so every group gets a fresh decision without anyone having to reset anything. The loop either found a station and broke out, or it ran out of stations and fell into the `else`. With no variable to reset, the bug above can't happen.

---

### Read It as `nobreak`

The clearest way to read a loop's `else` is to rename it in your head to `nobreak`. The block runs when the loop ends because it ran out of items. Anything that ends the loop early skips it. It helps to check that rule against every way control can leave a loop:

```python
def scan_docks(dock_codes: list[str], action: str) -> str:
    """Walk the dock status codes and react to the fault code E7."""
    for code in dock_codes:
        if code != "E7":
            continue
        if action == "break":
            break
        if action == "return":
            return "returned from inside the loop"
        if action == "raise":
            raise RuntimeError("dock fault E7")
    else:
        return "else ran"
    return "skipped else, reached the line after the loop"


for action in ["break", "return", "raise", "continue"]:
    try:
        print(f"{action:>8}: {scan_docks(['A1', 'E7', 'B2'], action)}")
    except RuntimeError as error:
        print(f"{action:>8}: {error}")
print(f"{'empty':>8}: {scan_docks([], 'break')}")
#    break: skipped else, reached the line after the loop
#   return: returned from inside the loop
#    raise: dock fault E7
# continue: else ran
#    empty: else ran
```

`break`, `return` and an exception all skip the `else`. `continue` doesn't, because `continue` only ends the current iteration, and the loop still runs to the end of its items. The empty list is the case people forget. A loop over nothing never gets a chance to break, so its `else` runs straight away. For a search, that's correct: an empty station list really does mean no station was found.

CPython doesn't have a special opcode for any of this. If you run `dis` on a `for`/`else`, the `else` body is just the code that follows `END_FOR`, where control lands when the iterator is exhausted. The `break` compiles to a `JUMP_FORWARD` that goes past it. The construct costs nothing at runtime. The search is still O(n), and you save one variable store and one test.

---

### `while`/`else`: When the Condition Runs Out

The same rule applies to `while`. The `else` runs when the loop ends because its condition became falsy, and a `break` skips it. That fits retry loops with a budget, where running out of attempts is the failure case:

```python
from collections.abc import Iterator


def release_bike(dock_id: str, replies: Iterator[str], budget: int = 3) -> None:
    """Ask a dock to unlock, retrying until the attempt budget runs out."""
    attempts_left = budget
    while attempts_left:
        attempts_left -= 1
        reply = next(replies)
        print(f"{dock_id}: {reply}")
        if reply == "released":
            break
    else:
        raise TimeoutError(f"{dock_id} still locked after {budget} tries")


release_bike("CS-04", iter(["busy", "busy", "released"]))
# CS-04: busy
# CS-04: busy
# CS-04: released

try:
    release_bike("HG-11", iter(["busy", "jammed", "busy", "released"]))
except TimeoutError as error:
    print(error)
# HG-11: busy
# HG-11: jammed
# HG-11: busy
# HG-11 still locked after 3 tries
```

The success path breaks out. Exhausting the budget falls into `else`, which raises. The second dock would have released on its fourth try, but the budget allowed three. The corollary matters too. On a `while True:` loop the condition can never become falsy, so its `else` can't run. The only way out of that loop is `break`, and `break` skips `else`.

---

### `try`/`else`: Guard Only the Lines That Can Fail

`else` on a `try` statement runs when the `try` block raised nothing. It can look redundant, since you could just put those lines at the end of the `try` block. The bike feed shows why that's a mistake. Each message carries a station ID and a change in its bike count. Some messages arrive truncated, and the feed occasionally mentions a station that the dispatcher has never registered:

```python
import json

feed = [
    '{"station": "CS-04", "delta": -2}',
    '{"station": "CS-04", "delta": ',
    '{"station": "OM-02", "delta": 1}',
]


def apply_feed_wide(messages: list[str], bikes: dict[str, int]) -> None:
    """Apply count changes; the try block guards every line."""
    for raw in messages:
        try:
            update = json.loads(raw)
            station_id = update["station"]
            delta = update["delta"]
            bikes[station_id] += delta
        except (json.JSONDecodeError, KeyError) as error:
            print(f"skipped bad message: {type(error).__name__}")


bikes = {"CS-04": 4, "HG-11": 2}
apply_feed_wide(feed, bikes)
print(bikes)
# skipped bad message: JSONDecodeError
# skipped bad message: KeyError
# {'CS-04': 2, 'HG-11': 2}
```

The `except KeyError` was there for messages that are missing a field. It also catches the `KeyError` from `bikes[station_id]`, which is a different problem: the message was fine, but the station registry is out of date. That gets logged as a "bad message" and dropped. A `try` block covers every line inside it, so each extra line widens what the handler catches without saying so.

The obvious fix is to move the update below the `try` statement. It breaks in a worse way:

```python
def apply_feed_after(messages: list[str], bikes: dict[str, int]) -> None:
    """Apply count changes; the update sits after the try statement."""
    for raw in messages:
        try:
            update = json.loads(raw)
            station_id = update["station"]
            delta = update["delta"]
        except (json.JSONDecodeError, KeyError) as error:
            print(f"skipped bad message: {type(error).__name__}")
        bikes[station_id] += delta


bikes = {"CS-04": 4, "HG-11": 2, "OM-02": 0}
apply_feed_after(feed, bikes)
print(bikes)
# skipped bad message: JSONDecodeError
# {'CS-04': 0, 'HG-11': 2, 'OM-02': 1}
```

This handler logs and carries on, so the update line runs whether parsing succeeded or not. When the truncated message fails to parse, `station_id` and `delta` still hold the previous message's values, because a loop doesn't give each iteration a fresh scope. The `-2` gets applied twice, and Clock Square reports zero bikes while two are sitting in its docks. Outside a loop, the same layout raises `NameError` on the first bad message, which is at least loud.

The `else` clause expresses what the code means: apply the update only if parsing succeeded, and don't guard it with the parsing handler:

```python
def apply_feed(messages: list[str], bikes: dict[str, int]) -> None:
    """Apply count changes; only parsing is guarded."""
    for raw in messages:
        try:
            update = json.loads(raw)
            station_id = update["station"]
            delta = update["delta"]
        except (json.JSONDecodeError, KeyError) as error:
            print(f"skipped bad message: {type(error).__name__}")
        else:
            bikes[station_id] += delta


bikes = {"CS-04": 4, "HG-11": 2}
try:
    apply_feed(feed, bikes)
except KeyError as error:
    print(f"unregistered station {error}, counts so far: {bikes}")
# skipped bad message: JSONDecodeError
# unregistered station 'OM-02', counts so far: {'CS-04': 2, 'HG-11': 2}
```

The truncated message is skipped without reusing stale values. The unregistered station raises a real `KeyError`, because an exception raised inside `else` is never handled by the `except` clauses of the same statement. This matters most in EAFP code, the "easier to ask forgiveness than permission" style that uses `try` for control flow. That style only works when each `try` block is narrow enough that the `except` clause catches exactly the failure it was written for.

When `finally` is added, the order is fixed: `try`, then either `except` or `else`, then `finally`. A `return` inside `try` skips `else`, but `finally` still runs:

```python
def checkout(dock_id: str, outcome: str) -> str:
    """Trace which clauses of one try statement run for each outcome."""
    try:
        print(f"try: unlock {dock_id}")
        if outcome == "fault":
            raise OSError("solenoid did not move")
        if outcome == "early":
            return "returned from try"
    except OSError as error:
        print(f"except: {error}")
    else:
        print("else: start the rental clock")
    finally:
        print("finally: write the audit row")
    return "reached the end"


for outcome in ["ok", "fault", "early"]:
    print(f"-> {checkout('CS-04', outcome)}")
# try: unlock CS-04
# else: start the rental clock
# finally: write the audit row
# -> reached the end
# try: unlock CS-04
# except: solenoid did not move
# finally: write the audit row
# -> reached the end
# try: unlock CS-04
# finally: write the audit row
# -> returned from try
```

The same rule covers `continue` and `break`. When a `try` statement sits inside a loop, either one leaves the `try` block early, so the `else` is skipped.

---

### One Indent Level Changes Everything

The most expensive `else` bug comes from indentation. Indent the loop's `else` one level deeper and it attaches to the `if`, and the code still runs:

```python
def dispatch_misaligned(
    groups: list[RideGroup], stations: list[Station]
) -> tuple[dict[str, str], list[str]]:
    """The same loop with else one indent level too deep."""
    assignments: dict[str, str] = {}
    waitlist: list[str] = []
    for group in groups:
        for station in stations:
            if station.can_serve(group.riders):
                station.free_bikes -= group.riders
                assignments[group.leader] = station.name
                break
            else:
                waitlist.append(group.leader)
    return assignments, waitlist


print(dispatch_misaligned(groups, morning_stations()))
# ({'Vesna': 'Clock Square', 'Ilian': 'Harbour Gate'},
#  ['Vesna', 'Vesna', 'Radko', 'Radko', 'Radko'])
```

The `if`/`else` now runs once per station rather than once per group. Vesna is assigned and also waitlisted twice, once for each station that couldn't take her before Clock Square could. Add a comment like `# no break` on every loop `else`, so a reader can see which statement it belongs to.

Two more habits help. A loop `else` with no `break` in the loop always runs, which makes it pointless, and Pylint flags it as `useless-else-on-loop`. And `break` only leaves the innermost loop, so an `else` on an outer loop says nothing about whether an inner loop broke.

Sometimes neither flags nor `else` is the right tool. When the search only needs to produce a value, `next()` with a default does it in one expression:

```python
def first_fit(group: RideGroup, stations: list[Station]) -> Station | None:
    """Return the first station that can serve the group, if any."""
    return next((s for s in stations if s.can_serve(group.riders)), None)


print(first_fit(RideGroup("Radko", 6), morning_stations()))  # None
print(first_fit(RideGroup("Ilian", 2), morning_stations()))
# Station(name='Harbour Gate', free_bikes=2, renting=True)
```

Use `for`/`else` when the found branch does work, such as updating counts, or when the not-found branch must raise or record something. If the loop body grows beyond a few lines, move it into a function that returns on success. A `return` ends the search as clearly as `else` does, and most readers already know how it works. One more note: `match` has no `else`. Its catch-all is `case _:`.

---

### Conclusion

On loops and `try`, `else` is a "then" clause. A loop's `else` runs when the loop ends without a `break`, which includes a loop over an empty iterable. A `while` loop's `else` runs when its condition becomes falsy. A `try` statement's `else` runs when the `try` block raised nothing, and its `except` handlers don't cover it. Use it to replace search flags that someone will eventually forget to reset, and to keep each `try` block down to the lines that can actually raise the exception you're catching. Mark every loop `else` with a `# no break` comment and check its indentation. If the loop starts to look complicated, a small function with `return` is usually easier to read than any `else`.
