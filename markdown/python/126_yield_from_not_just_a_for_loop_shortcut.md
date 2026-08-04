# yield from: Not Just a For-Loop Shortcut

#### What `for x in sub: yield x` misses about return values, send routing, and exception propagation

**By Tihomir Manushev**

*Apr 11, 2026 · 7 min read*

---

The standard introduction to `yield from` says it is sugar for `for x in sub: yield x`. For trivial iteration over a list, the two really are equivalent — and that is where most tutorials stop. But PEP 380 did not introduce `yield from` to save typing. It introduced it because the manual loop is structurally broken the moment you need anything beyond yielding values: capturing the subgenerator's return value, routing `send()` calls through delegation, propagating exceptions, or letting `close()` clean up nested coroutines.

`yield from` is a delegation operator. It wires the outer generator and the inner generator into a single virtual generator from the caller's perspective. Yields, sends, throws, closes, and returns all flow through the connection. The for-loop "equivalent" handles exactly one of those — values out — and silently drops the rest.

This article walks through what `yield from` actually does, why a tree traversal makes the difference visible, and how to capture the subgenerator's return value.

---

### The Tree-Traversal Sweet Spot

Where `yield from` first earns its keep is recursion over nested structures. Consider a comment thread — a parent comment with a list of replies, each reply having its own replies:

```python
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class Comment:
    """A comment node in a discussion thread."""
    id: int
    text: str
    replies: list["Comment"] = field(default_factory=list)


def walk(node: Comment) -> Iterator[Comment]:
    """Depth-first traversal: yield this comment, then all descendants."""
    yield node
    for reply in node.replies:
        yield from walk(reply)
```

The traversal is two lines. Without `yield from`, the recursive case needs a second loop:

```python
def walk_manual(node: Comment) -> Iterator[Comment]:
    yield node
    for reply in node.replies:
        for descendant in walk_manual(reply):
            yield descendant
```

Behavior is identical when all you want is values. Run it on a small thread:

```python
thread = Comment(1, "great post", [
    Comment(2, "agreed", [Comment(4, "+1")]),
    Comment(3, "not sure", [
        Comment(5, "why?", [Comment(6, "because...")]),
    ]),
])

for c in walk(thread):
    print(c.id, c.text)
# 1 great post
# 2 agreed
# 4 +1
# 3 not sure
# 5 why?
# 6 because...
```

The output proves the depth-first walk reaches every node. For pure iteration, the two implementations behave the same. The story changes the moment the subgenerator does more than yield values.

---

### What yield from Actually Does

PEP 380 specifies `yield from sub` as a delegation operator, not a flow-control shortcut. Five behaviors flow through it:

1. **Values out.** Each value yielded by the subgenerator becomes a value of the outer generator.
2. **Return values in.** When the subgenerator finishes (raises `StopIteration`), the value carried by `StopIteration.value` becomes the value of the `yield from` expression itself — meaning `result = yield from sub()` captures it.
3. **`send()` routed in.** A value passed via `gen.send(v)` from outside flows directly to the subgenerator's suspended `yield`, not the outer one.
4. **`throw()` routed in.** An exception injected via `gen.throw(exc)` is raised at the subgenerator's suspended `yield`, where its `try`/`except` can handle it.
5. **`close()` propagated.** Closing the outer generator closes the inner one too, so cleanup code in nested `finally` blocks runs.

The `for x in sub: yield x` version implements only behavior 1. The other four are silently dropped — no error, no warning, just missing semantics. That is the structural break PEP 380 fixed.

---

### Capturing the Return Value

The most visible payoff is behavior 2. A subgenerator that yields some values and then `return`s a final result lets the outer generator consume both — yields go to the caller, the return value goes to the outer generator. Here is a batched-aggregation pattern:

```python
from typing import Iterator


def sum_positives(numbers: list[int]) -> Iterator[int]:
    """Yield each positive number; return the running total when done."""
    total = 0
    for n in numbers:
        if n < 0:
            return total
        yield n
        total += n
    return total


def aggregate(batches: list[list[int]]) -> Iterator[int]:
    """Yield every batch's positive values; return the grand total across batches."""
    grand_total = 0
    for batch in batches:
        batch_total = yield from sum_positives(batch)
        grand_total += batch_total
    return grand_total
```

Run it across three batches — one clean, one stopped early by a negative, one short:

```python
gen = aggregate([[1, 2, 3], [4, 5, -1], [10]])
yielded: list[int] = []
try:
    while True:
        yielded.append(next(gen))
except StopIteration as stop:
    print(yielded)      # [1, 2, 3, 4, 5, 10]
    print(stop.value)   # 25
```

The `yielded` list captures every positive value across batches. `stop.value` carries the grand total — `6 + 9 + 10 = 25`. The crucial expression is `batch_total = yield from sum_positives(batch)`: when `sum_positives` returns, the value of the `yield from` expression is the returned total, which the outer generator assigns and accumulates.

Now rewrite `aggregate` with the manual for-loop version:

```python
def aggregate_manual(batches: list[list[int]]) -> Iterator[int]:
    grand_total = 0
    for batch in batches:
        for value in sum_positives(batch):
            yield value
        # the subgenerator's return value is silently lost here
    return grand_total
```

Run it on the same input:

```python
gen2 = aggregate_manual([[1, 2, 3], [4, 5, -1], [10]])
print(list(gen2))  # [1, 2, 3, 4, 5, 10]
```

The yielded values match — but `grand_total` stays at `0` because the `for` loop has no way to capture the `StopIteration.value`. The return values from each `sum_positives` call vanish into the runtime, leaving the aggregation incorrect. No error fires; the numbers just come out wrong.

---

### Routing send() Through Delegation

Behavior 3 — `send()` flowing through delegation — is what makes `yield from` essential for coroutine-style code. When the outer generator is currently delegating to a subgenerator, a `send(value)` call goes directly to the subgenerator's suspended `yield`. The outer generator does not see the value at all.

```python
from typing import Generator


def doubler() -> Generator[None, int, None]:
    """Consume integers via send(); print each doubled; return on 0."""
    while True:
        value = yield
        if value == 0:
            return
        print(f"doubled: {value * 2}")


def pipeline() -> Generator[None, int, None]:
    """Bracket a doubler with setup/teardown messages."""
    print("pipeline: starting")
    yield from doubler()
    print("pipeline: done")
```

Drive it from the outside:

```python
p = pipeline()
next(p)                # pipeline: starting
p.send(3)              # doubled: 6
p.send(5)              # doubled: 10
try:
    p.send(0)          # pipeline: done
except StopIteration:
    pass
```

`p.send(3)` does not go to `pipeline`. The pipeline is suspended at `yield from doubler()`, and `send(3)` is routed straight to `doubler`'s `value = yield`. The doubler prints `doubled: 6` and yields again. When `p.send(0)` is called, the doubler `return`s, the `yield from` expression completes, control flows back to `pipeline`, the teardown message prints, and the outer generator falls off its end — raising `StopIteration`.

Without `yield from`, this routing is impossible to express cleanly. A manual loop would receive every `send()` value in the outer generator, leaving you to forward it to the inner one by hand — and exceptions, returns, and `close()` would still be lost.

---

### Conclusion

`yield from` is not syntax sugar. It is a delegation operator that turns nested generators into a single virtual one from the caller's perspective. Yields flow up, return values flow back through `StopIteration.value`, `send()` and `throw()` route into the suspended subgenerator, and `close()` cascades cleanup through the chain. The for-loop "equivalent" handles only the first behavior, silently dropping the other four. For tree traversals it looks like a stylistic choice. For anything that captures return values, accepts injected input, or coordinates exception handling, it is the only option.
