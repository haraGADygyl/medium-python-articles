# Python Memoization: The Choice Between functools.cache and lru_cache
#### Understanding the mechanics, memory models, and internal algorithms of the standard library’s caching decorators

**By Tihomir Manushev**  
*Dec 18, 2025 · 7 min read*

---

In the landscape of high-performance Python, the most efficient code is the code you never have to execute.

As systems scale, we often encounter functions that are computationally expensive (CPU-bound) or suffer from high latency due to I/O operations (I/O-bound). When these functions are deterministic — meaning the same input always yields the same output — re-executing them with identical arguments is a waste of resources.

This is where memoization comes into play. Memoization is an optimization technique that caches the return values of expensive function calls and returns the cached result when the same inputs occur again.

For years, Python developers relied on rolling their own dictionaries to handle this, or they used `functools.lru_cache`. With the release of Python 3.9, a new player entered the arena: `functools.cache`. While they seem similar, choosing the wrong one can lead to catastrophic memory leaks in long-running applications.

In this deep dive, we will explore the mechanics of these decorators, dissect their internal memory models, and determine exactly when to use which tool in a production environment.

---

### The Cost of Redundancy

To understand the value of memoization, we must first visualize the cost of redundancy. Recursive algorithms are the textbook example. Let’s look at the Tribonacci sequence. Unlike the standard Fibonacci sequence (which sums the previous two numbers), Tribonacci sums the previous three.

Without optimization, calculating the 35th Tribonacci number requires millions of redundant function calls.

```python
import time
from collections.abc import Callable

# A simple timing decorator for our benchmarks
def timer(func: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        print(f"[{func.__name__}] Execution time: {end - start:.6f}s")
        return result
    return wrapper

def tribonacci_naive(n: int) -> int:
    if n < 3:
        return 1 if n == 2 else 0
    return tribonacci_naive(n - 1) + tribonacci_naive(n - 2) + tribonacci_naive(n - 3)

@timer
def run_naive():
    # This will be painfully slow
    print(f"Result: {tribonacci_naive(30)}")

run_naive()
```

The time complexity here is exponential. But notice that `tribonacci_naive(5)` is called thousands of times, always returning the same integer. This is the perfect candidate for `functools`.

---

### The Modern Sledgehammer: functools.cache

Introduced in Python 3.9, `@functools.cache` is the simpler, streamlined cousin of the older `lru_cache`. It creates a thin wrapper around a dictionary that stores the results of function calls.

The syntax is cleaner, and it is slightly faster than `lru_cache` because it lacks the overhead of managing eviction logic.

```python
import functools
import time
from collections.abc import Callable


# A simple timing decorator for our benchmarks
def timer(func: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        print(f"[{func.__name__}] Execution time: {end - start:.6f}s")
        return result

    return wrapper


# We apply the decorator directly to the recursive function
@functools.cache
def tribonacci_optimized(n: int) -> int:
    if n < 3:
        return 1 if n == 2 else 0
    return tribonacci_optimized(n - 1) + tribonacci_optimized(n - 2) + tribonacci_optimized(n - 3)


@timer
def run_optimized():
    # 300 is significantly larger than the previous 30
    # yet it runs instantly.
    result = tribonacci_optimized(300)
    print(f"Result (truncated): {str(result)[:10]}...")


run_optimized()
```

---

### The Shadow Side of Unbounded Growth

`functools.cache` is effectively `lru_cache(maxsize=None)`. This sounds convenient, but it carries a severe implication: it never forgets.

Every unique argument passed to `tribonacci_optimized` creates a new entry in the internal dictionary. In a recursive mathematical function, the input space is usually limited (e.g., integers 1 to 1000). However, in a web application processing user requests, the input space could be infinite.

If you use `@functools.cache` on a function that processes User IDs or Session Tokens, your process memory will grow monotonically until the operating system kills the application (OOM Kill).

Use `functools.cache` only when:

*   The input space is finite and small.
*   The script is short-lived (e.g., data analysis scripts, CLI tools).
*   You explicitly want to trade all available RAM for CPU speed.

---

### The Surgical Scalpel: functools.lru_cache

For long-running processes — like web servers (Django/FastAPI), Celery workers, or GUI applications — unbounded caching is dangerous. We need a cache that cleans itself up.

LRU stands for Least Recently Used. When the cache is full, adding a new entry forces the removal of the entry that hasn’t been accessed for the longest time.

---

### Configuring Boundaries

`lru_cache` accepts two primary arguments:

1.  **maxsize**: The maximum number of entries to keep. Defaults to 128.
2.  **typed**: If True, arguments of different types (e.g., 3 and 3.0) are cached separately.

Let’s simulate an I/O-bound operation, such as fetching a user’s configuration profile from a remote database.

```python
import time
from functools import lru_cache

# Simulate a database object
class MockDatabase:
    def __init__(self):
        self._data = {
            101: "Settings_A",
            102: "Settings_B",
            103: "Settings_C",
            104: "Settings_D"
        }

    @lru_cache(maxsize=3)
    def get_user_settings(self, user_id: int) -> str:
        print(f"--> DB HIT: Fetching data for user {user_id}...")
        time.sleep(0.2) # Simulate network latency
        return self._data.get(user_id, "Default")

db = MockDatabase()

print("--- Round 1: Cold Cache ---")
db.get_user_settings(101) # Cache: [101]
db.get_user_settings(102) # Cache: [101, 102]
db.get_user_settings(103) # Cache: [101, 102, 103] (Full)

print("\n--- Round 2: Cache Hits ---")
db.get_user_settings(101) # Hit. 101 moves to front. Cache: [102, 103, 101]

print("\n--- Round 3: Eviction ---")
# We request 104. Cache is full (maxsize=3).
# 102 is the Least Recently Used. It gets evicted.
db.get_user_settings(104) # Cache: [103, 101, 104]

print("\n--- Round 4: The Cost of Eviction ---")
# Requesting 102 again triggers a DB HIT because it was dropped.
db.get_user_settings(102)
```

In Round 3, requesting user 104 didn’t just add data; it silently destroyed the data for user 102 because `maxsize=3` was reached. In production, tuning maxsize is an art. Too small, and you get “cache thrashing” (constantly writing and evicting). Too large, and you waste RAM.

---

### Introspection

A powerful feature of `lru_cache` (and `cache`) is the ability to inspect performance at runtime. This is invaluable for debugging and monitoring.

```python
info = db.get_user_settings.cache_info()
print(f"\nCache Stats: {info}")
```

If your hits are low and misses are high, your maxsize is likely too small, or the data access pattern isn’t suitable for LRU caching.

---

### The Trap: Hashability and Mutable Arguments

The underlying mechanism of both decorators relies on a Python dict. The keys of this dictionary are created from the positional and keyword arguments passed to the function.

This imposes a strict constraint: **All arguments must be hashable.**

In Python, immutable types (integers, strings, tuples, frozensets) are hashable. Mutable types (lists, dictionaries, sets) are not.

```python
@functools.cache
def analyze_data(data_points: list[int]):
    return sum(data_points) / len(data_points)

# This crashes immediately
# analyze_data([10, 20, 30])
# TypeError: unhashable type: 'list'
```

To work around this, you must convert mutable arguments into immutable ones before passing them to the decorated function.

```python
@functools.cache
def analyze_data_safe(data_points: tuple[int, ...]):
    return sum(data_points) / len(data_points)

raw_data = [10, 20, 30]
# Convert list to tuple before call
analyze_data_safe(tuple(raw_data))
```

Alternatively, if you are designing a class method, ensure your custom objects implement `__hash__` and `__eq__` if you intend to pass instances as arguments to cached functions.

---

### typed=True: The Edge Case

By default, `lru_cache` treats 1 (int) and 1.0 (float) as the same key because `1 == 1.0` is True in Python.

However, in certain serialization or strict-typing contexts, returning an integer when a float was requested might cause bugs.

```python
@lru_cache(maxsize=16, typed=True)
def square(x):
    return x * x

print(square(3))   # Returns 9 (int), cached as Key: (3, int)
print(square(3.0)) # Returns 9.0 (float), cached as Key: (3.0, float)
```

With `typed=True`, these are stored as two separate entries, consuming two slots in the cache.

---

### Under the Hood: Thread Safety and CPython

It is important to note that both `cache` and `lru_cache` are thread-safe. The CPython implementation uses a lock to ensure that multiple threads trying to update the cache simultaneously won’t corrupt the internal linked list or dictionary.

However, the decorated function itself is not automatically made thread-safe. If your function modifies global state, the decorator won’t protect you from race conditions within the function body; it only protects the cache mapping itself.

The `lru_cache` implementation in CPython is particularly clever. It uses a dictionary to map keys to nodes in a doubly linked list.

*   **Access (Hit):** O(1). The node is moved to the head of the list (Most Recently Used).
*   **Insertion (Miss):** O(1). A new node is added to the head.
*   **Eviction:** O(1). The node at the tail (Least Recently Used) is removed.

This efficiency makes `lru_cache` suitable even for high-throughput code paths.

---

### Conclusion

While `functools.cache` offers syntactic sugar and a minor speed boost, it assumes you have infinite RAM. As a good engineer, default to `lru_cache` for any code destined for production services. Setting a conservative maxsize (e.g., 1024) provides a safety net that protects your application reliability, which is always worth more than the nanoseconds saved by skipping eviction logic.
