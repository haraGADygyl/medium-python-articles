# Infinite Generators: Taming count, cycle, and repeat with islice and takewhile

#### Three itertools producers that never stop, the two tools that make them finite, and the one that quietly copies your whole stream into memory

**By Tihomir Manushev**

*Jul 17, 2026 · 7 min read*

---

`itertools.count()` will hand you integers until the heat death of the universe. `itertools.cycle()` loops its input forever. `itertools.repeat()` yields the same value without end. These are not bugs or edge cases — they are the point. An infinite generator is a value stream you *bound at the point of use*, not at the point of creation, which lets you describe "all the IDs" or "the shift rotation" once and take exactly as many as you need later.

The danger is that one careless call turns that elegance into a hang. Wrap `count()` in `list()`, pass `cycle()` to `sum()`, or hand either to `sorted()`, and your program stops responding and climbs toward an out-of-memory kill — because those functions demand a *last* element that will never arrive. The skill is knowing which operations are safe on an endless stream and which are a trap.

This article covers the three producers, the two consumers that make them finite — `islice` and `takewhile` — a gotcha that turns `takewhile` into silently wrong results, and the memory surprise hiding inside `cycle`. Every output below is real.

---

### Three Producers That Never Stop

`count(start, step)` is a lazy, unbounded `range` with no stop value — perfect for generating identifiers or an axis of evenly spaced numbers. `cycle(iterable)` repeats a finite sequence endlessly, which is exactly a round-robin. `repeat(value)` yields one value forever, or a fixed number of times if you give it a count:

```python
from itertools import count, cycle, repeat, islice

print(list(islice(count(1000, 5), 5)))
# [1000, 1005, 1010, 1015, 1020]

shifts = cycle(["early", "late", "night"])
print(list(islice(shifts, 7)))
# ['early', 'late', 'night', 'early', 'late', 'night', 'early']

print(list(repeat(0, 4)))
# [0, 0, 0, 0]
```

Each producer yields one value at a time and holds essentially nothing — a `count()` object is a few bytes regardless of how high it will eventually go. That **O(1)** footprint is what makes them safe to create and pass around; the cost only appears when you try to collect them. `repeat` shines paired with `zip`, supplying a constant alongside a real sequence without building a matching list:

```python
print(list(zip(["a", "b", "c"], repeat("?"))))
# [('a', '?'), ('b', '?'), ('c', '?')]
```

The `zip` stops when the finite `["a", "b", "c"]` runs out, so pairing a bounded iterable with an infinite one is one of the safe operations — the finite side sets the limit.

That same pattern is a `count`-powered `enumerate` with a start value of your choosing. `enumerate` always begins at whatever you pass it, but pairing `count` with `zip` composes cleanly with other producers and reads clearly when you want numbering to start at one:

```python
labels = ["disk", "cpu", "net"]
print(list(zip(count(1), labels)))
# [(1, 'disk'), (2, 'cpu'), (3, 'net')]
```

`count(1)` is infinite, but `zip` halts the moment `labels` is exhausted, so no explicit bound is needed — the finite operand is the bound. This is the mental model to carry into every pipeline below: an infinite stream is safe precisely as long as *something* finite is deciding when to stop.

---

### islice: Slicing an Iterator

You can't write `count()[:5]` — iterators don't support subscripting. `islice` is the slice notation for anything iterable: `islice(iterable, stop)` takes the first `stop` items, and the full `islice(iterable, start, stop, step)` skips and strides like a slice, with one restriction — no negative indices, because counting from the end is impossible on a stream that has no end.

```python
print(list(islice(count(), 2, 10, 2)))
# [2, 4, 6, 8]
```

The crucial behavior most people miss: `islice` **advances and consumes** the underlying iterator rather than viewing it. Slice the same iterator twice and the second call continues where the first stopped — it does not restart:

```python
stream = count()
print(list(islice(stream, 3)))   # [0, 1, 2]
print(list(islice(stream, 3)))   # [3, 4, 5]  -- continues, not restarts
```

That consuming behavior is a feature: it's how you pull an endless source in fixed-size batches, grabbing the next chunk each time. Python 3.12 gives this common pattern a dedicated built-in, `batched`, which packages an iterable into tuples of a chosen size:

```python
from itertools import batched
print(list(islice(batched(count(1), 3), 4)))
# [(1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)]
```

`batched(count(1), 3)` is itself infinite — it yields triples forever — so it's still `islice` that caps it at four batches. The lesson generalizes: any tool built on an infinite source stays infinite until something explicitly bounds it.

---

### takewhile and dropwhile: Bounding by Condition

`islice` bounds a stream by *count*. `takewhile` bounds it by *condition*: it yields elements while a predicate holds and stops permanently the instant one fails. Its mirror image, `dropwhile`, discards the leading run that satisfies the predicate and yields everything from the first failure onward.

```python
from itertools import takewhile, dropwhile

readings = [12, 15, 18, 9, 21, 14]
print(list(takewhile(lambda x: x < 20, readings)))   # [12, 15, 18, 9]
print(list(dropwhile(lambda x: x < 20, readings)))   # [21, 14]
```

`takewhile` returned the leading run under 20 and stopped at 21 — note it *kept* the 9, because 9 is still part of the unbroken prefix; it only cares about the first element that fails. This makes it the natural way to consume an infinite stream "until a condition breaks" — read a sensor's `count()`-driven feed until a value crosses a threshold, and `takewhile` both bounds the stream and terminates the program. It's also the classic partner for `any()` and short-circuit consumers: the producer is endless, the condition ends it.

---

### The Trap: takewhile Is Not a Filter

Here is where `takewhile` bites. It looks like `filter`, and on the wrong data it produces confidently wrong output. `takewhile` stops at the first failure and never looks again; `filter` tests every element and keeps all that pass. On data where the predicate isn't monotonic, they diverge hard:

```python
samples = [2, 4, 6, 7, 8, 10]
print(list(takewhile(lambda x: x % 2 == 0, samples)))   # [2, 4, 6]
print(list(filter(lambda x: x % 2 == 0, samples)))       # [2, 4, 6, 8, 10]
```

`takewhile` hit the odd `7`, concluded the run was over, and threw away the `8` and `10` that came after — even though they satisfy the predicate. `filter` kept them. The rule: `takewhile` answers "the leading prefix that all passes," `filter` answers "every element that passes." Use `takewhile` only when the data is ordered so that once the condition fails it stays failed — a sorted sequence, a monotonic counter, a stream you genuinely want to stop reading at the first violation. Reach for `filter` when you want all matching elements regardless of position — but never on an infinite source, because `filter` has no reason to stop and will run forever.

---

### cycle's Hidden Buffer

`count` and `repeat` remember almost nothing. `cycle` is different, and the difference is a memory trap. To replay its input forever, `cycle` must *remember* that input — so on the first pass it copies every element it sees into an internal buffer, then serves from the copy. You can prove it feeds `cycle` a single-pass generator, which normally cannot be replayed, and watch it loop anyway:

```python
from itertools import cycle

one_shot = (n * n for n in range(4))
looped = cycle(one_shot)
print([next(looped) for _ in range(9)])
# [0, 1, 4, 9, 0, 1, 4, 9, 0]
```

The generator `one_shot` can only be walked once, yet `cycle` replayed it — because it stashed `0, 1, 4, 9` in memory during the first lap. That means the memory cost of `cycle` is proportional to the length of its input, not the constant footprint of `count` or `repeat`. Cycling a short list of shift names is free; cycling a million-row result set silently buffers all million rows, and cycling an *unbounded* generator tries to buffer infinity. Keep `cycle`'s input small and finite, and never feed it another infinite iterator.

---

### Conclusion

Infinite producers invert where you make decisions: `count`, `cycle`, and `repeat` let you declare an endless stream cheaply and decide how much of it you want at the moment you consume it. The whole discipline is to *always* place a bound between the producer and any function that needs a last element. Cap by count with `islice`, cap by condition with `takewhile`, or let a finite `zip` partner set the limit — but never let `list()`, `sum()`, `sorted()`, or `max()` touch an unbounded stream directly, because they will wait forever for an end that isn't coming.

Keep the two sharp edges in mind. `takewhile` is a prefix, not a filter, so it belongs only on data where a failed condition stays failed. And `cycle` buys its endless replay with memory proportional to its input, so keep that input small. Get those right, and infinite generators become what they were designed to be — a way to write "as many as I need" instead of guessing the number up front.
