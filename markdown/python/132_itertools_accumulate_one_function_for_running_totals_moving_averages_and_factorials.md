# itertools.accumulate: One Function for Running Totals, Moving Averages, and Factorials

#### The scan that keeps every step of a fold — swap the operator and the same function gives you running sums, factorials, or a rolling peak

**By Tihomir Manushev**

*Jul 17, 2026 · 7 min read*

---

`functools.reduce` folds an iterable down to a single value and throws away everything in between. Sum a list of daily sales and you get one number — the total — but not the balance after day one, day two, day three. Most of the time, the intermediate results are exactly what you want: a running total for a chart, a cumulative maximum for a high-water mark, a growing product for a factorial.

`itertools.accumulate` is `reduce` with a memory. It performs the same left fold but *yields every intermediate result* along the way — computer scientists call this a **scan**, and it turns a whole category of hand-written loops-with-an-accumulator-variable into one lazy call. The quiet superpower is that the operation is a parameter: keep the default and you get running sums, pass `operator.mul` and you get factorials, pass `max` and you get a rolling peak. One function, an entire family of cumulative folds.

This article maps that family with real output — running totals, products, extremes — covers the `initial` keyword and the left-fold subtlety that bites custom operators, and clears up a common misconception baked into the function's own reputation: `accumulate` gives you a *cumulative* average, not a fixed-window *moving* average, and those are different tools.

---

### Scan, Not Reduce

The defining difference is what comes out. `reduce` returns the final value; `accumulate` returns an iterator of every step that led there.

```python
from itertools import accumulate
from functools import reduce

daily = [12, 5, 8, 20, 3]

print(list(accumulate(daily)))                  # [12, 17, 25, 45, 48]
print(reduce(lambda a, b: a + b, daily))        # 48
```

Both compute the same running total internally; `accumulate` just hands you the whole trail — 12, then 12+5, then 12+5+8, and so on — while `reduce` keeps only the last. That trail is precisely what a cumulative chart, a running-balance column, or a progress-over-time report needs. And because `accumulate` is a lazy iterator, it produces those values one at a time in **O(1)** memory, never building an intermediate list unless you ask for one with `list()`. The output always has the same number of elements as the input.

---

### Swap the Operator, Change the Fold

By default `accumulate` adds. Its optional second argument is the binary function it folds with, and changing it changes the entire meaning while the machinery stays identical. Pass `operator.mul` and the running sum becomes a running product — which over the integers is the sequence of factorials:

```python
from operator import mul

print(list(accumulate(range(1, 6), mul)))       # [1, 2, 6, 24, 120]
```

Those are 1!, 2!, 3!, 4!, and 5! — each element is the previous one times the next integer. Pass `max` or `min` and you get **running extremes**, the value most people reach for a manual `if current > best` loop to compute:

```python
levels = [3, 7, 4, 9, 8, 2, 11]

print(list(accumulate(levels, max)))            # [3, 7, 7, 9, 9, 9, 11]
print(list(accumulate(levels, min)))            # [3, 3, 3, 3, 3, 2, 2]
```

The running maximum is the backbone of a genuinely useful calculation: drawdown, or how far something has fallen from its best so far. Fold prices with `max` to get the running peak, then subtract:

```python
prices = [100, 108, 102, 120, 95, 130]
peaks = list(accumulate(prices, max))
drawdowns = [round(price - peak, 1) for price, peak in zip(prices, peaks)]

print(peaks)        # [100, 108, 108, 120, 120, 130]
print(drawdowns)    # [0, 0, -6, 0, -25, 0]
```

The `-25` correctly marks the moment the price sat 25 below its highest point to date. No accumulator variable, no manual bookkeeping — the running peak is a fold, and the drawdown is a subtraction over it.

---

### The initial Keyword

Since Python 3.8, `accumulate` accepts an `initial` argument that seeds the fold before the first element. It's what you want for a running balance that starts from an opening value rather than from the first transaction:

```python
print(list(accumulate([10, 20, 30])))                # [10, 30, 60]
print(list(accumulate([10, 20, 30], initial=100)))   # [100, 110, 130, 160]
```

Note the length: `initial` prepends the seed as the first emitted value, so the output has **one more element** than the input. That off-by-one matters if downstream code zips the result against the original sequence — with `initial`, they no longer line up. It also makes `accumulate` total over an empty input: without a seed an empty iterable yields nothing, but with `initial` it still yields the seed.

---

### It's a Left Fold

`accumulate` folds left to right, calling your function as `func(accumulated_so_far, next_element)`. For commutative operators like `+`, `*`, `max`, and `min`, the argument order is invisible. For anything non-commutative — subtraction, division, string building — it is the whole story:

```python
from operator import sub

print(list(accumulate([100, 10, 5, 1], sub)))   # [100, 90, 85, 84]
```

Each step subtracts the next element *from* the accumulator: 100, then 100−10, then 90−5, then 85−1. If you write a custom two-argument function, remember the accumulator arrives first and the fresh element second; getting that backwards silently produces wrong numbers rather than an error, because the signature still matches.

---

### Lazy and Composable

`accumulate` returns an iterator, not a list, so it composes with the rest of `itertools` and stays finite-friendly on infinite sources. Feed it an endless counter and cap the result with `islice`, and you get, for instance, the triangular numbers without ever materializing an unbounded list:

```python
from itertools import count, islice

print(list(islice(accumulate(count(1)), 6)))    # [1, 3, 6, 10, 15, 21]
```

The running sum of 1, 2, 3, … is 1, 3, 6, 10, … — each triangular number. Because both `count` and `accumulate` are lazy, this pipeline holds nothing but its current state; `islice` decides how much of the infinite scan to draw. This is the payoff of `accumulate` being an iterator rather than a batch function: it slots into lazy pipelines instead of forcing a full pass up front.

---

### Beyond Numbers

Nothing about `accumulate` requires numbers — the fold works on any type its operator accepts. Pass `operator.or_` and you fold sets, giving a **running union**: the set of everything seen up to each step. That's a clean way to answer "which distinct event types had appeared by batch N?" as a single scan:

```python
from operator import or_

batches = [{"login", "view"}, {"view", "buy"}, {"refund"}]
print([sorted(s) for s in accumulate(batches, or_)])
# [['login', 'view'], ['buy', 'login', 'view'], ['buy', 'login', 'refund', 'view']]
```

Each element is the accumulated union so far, so the vocabulary of events only grows. (The sets are sorted here only to print deterministically — sets have no inherent order.) The same idea folds strings with concatenation, lists with `+`, or any associative combiner: if you can write the two-argument step, `accumulate` gives you its running history for free.

---

### Running vs Windowed: A Common Mix-Up

The word "moving average" attaches itself to `accumulate`, and it's worth being precise, because `accumulate` produces a **cumulative** (expanding) average, not a fixed-window **moving** average. A cumulative average includes *every* value seen so far, and you build it from a running sum:

```python
readings = [10, 20, 30, 40]
running_avg = [total / (i + 1) for i, total in enumerate(accumulate(readings))]
print(running_avg)      # [10.0, 15.0, 20.0, 25.0]
```

Each entry averages all readings up to that point — the window grows without bound. A true moving average averages only the last *N* values, and that is a genuinely different computation: the window slides, dropping old values as new ones arrive, which `accumulate` does not do. That job belongs to a `deque` with a fixed `maxlen`:

```python
from collections import deque

def moving_average(values: list[float], window: int) -> list[float]:
    buffer: deque[float] = deque(maxlen=window)
    result = []
    for value in values:
        buffer.append(value)
        result.append(sum(buffer) / len(buffer))
    return result

print(moving_average([10, 20, 30, 40, 50], 3))   # [10.0, 15.0, 20.0, 30.0, 40.0]
```

The last entry, `40.0`, averages only `30, 40, 50` — the trailing three — where a cumulative average would have returned `30.0` over all five. Reach for `accumulate` when the whole history should count; reach for a bounded `deque` when only a recent window should.

---

### Conclusion

`accumulate` is the scan hiding next to `reduce`: the same left fold, but it keeps every step instead of only the last. That single behavioral difference, combined with a swappable operator, collapses a surprising range of hand-rolled loops into one lazy call — running totals with the default, factorials with `operator.mul`, rolling peaks and drawdowns with `max`, seeded balances with `initial`. It yields in constant memory and composes with the rest of `itertools`, so it fits pipelines that `reduce` and a manual accumulator cannot.

Keep the three edges in mind: `initial` adds an element and shifts your alignment, the fold is left-associative so operator order matters for non-commutative functions, and `accumulate` gives a cumulative average, not a windowed one — a sliding window is a `deque`'s job. Learn to see "running anything" as a fold over a sequence, and `accumulate` becomes one of the most quietly versatile functions in the standard library.
