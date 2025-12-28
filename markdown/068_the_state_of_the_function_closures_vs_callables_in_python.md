# The State of the Function: Closures vs. Callables in Python
#### Understanding the mechanics of nonlocal, __closure__ cells, and CPython bytecode to optimize stateful logic

**By Tihomir Manushev**  
*Dec 25, 2025 · 7 min read*

---

In the architectural landscape of Python, we are often presented with a deceptively simple requirement: we need a function that remembers.

Perhaps you are implementing a retry mechanism with exponential backoff, a debouncer for an API client, or a signal processing filter. The logic requires executing an action, but the result of that action depends on what happened during the previous execution.

In strictly procedural languages, developers might reach for the global scope (a cardinal sin in modern engineering). In purely functional languages, one might pass the state recursively. But Python, being a multi-paradigm pragmatist, offers us two distinct, powerful mechanisms to bundle behavior with state: the Object-Oriented Class (specifically one implementing `__call__`) and the Lexical Closure.

While the “Gang of Four” Command Pattern is traditionally taught using classes, modern Python — treating functions as first-class citizens — often allows for cleaner, more memory-efficient implementations using closures. However, choosing the wrong tool can lead to maintenance nightmares or subtle performance bottlenecks.

In this deep dive, we will move beyond syntax and explore the CPython internals, memory models, and bytecode mechanics that differentiate these two approaches.

---

### The Object-Oriented Approach: The Callable Protocol

In Python, “callable” is a protocol, not just a property of functions. Any object can behave like a function if its class implements the `__call__` dunder method.

This is the standard Object-Oriented (OO) solution to state retention. You encapsulate state in instance attributes (`self.x`) and behavior in the `__call__` method.

Let’s imagine we are processing a stream of noisy temperature data from an IoT sensor. We need a filter that smooths this data using an Exponential Moving Average. This requires the filter to “remember” the previous calculated average.

Here is the production-grade, Type-Hinted Class implementation:

```python
from dataclasses import dataclass

@dataclass
class EMAFilter:
    """
    Computes an Exponential Moving Average.
    State is stored in instance attributes.
    """
    alpha: float
    _current_avg: float | None = None

    def __call__(self, new_sample: float) -> float:
        if self._current_avg is None:
            self._current_avg = new_sample
        else:
            # Standard EMA formula
            self._current_avg = (self.alpha * new_sample) + \
                                ((1 - self.alpha) * self._current_avg)
        
        return self._current_avg

# Usage
smoothing_strategy = EMAFilter(alpha=0.1)

# The object looks and acts like a function
print(f"Sample 1: {smoothing_strategy(20.0):.2f}")
print(f"Sample 2: {smoothing_strategy(22.0):.2f}")
print(f"Sample 3: {smoothing_strategy(30.0):.2f}")
```

When `smoothing_strategy(20.0)` is executed, CPython performs a lookup for the `__call__` method on the type of the instance. It binds `self` to the instance and executes the method body. The state (`_current_avg`) is stored in the object’s `__dict__` (or a fixed memory slot if `__slots__` is used).

**Pros:**

*   **Introspection:** You can easily inspect `smoothing_strategy.alpha` or `smoothing_strategy._current_avg` from the outside (useful for debugging).
*   **Extensibility:** You can add methods like `reset()` or `update_alpha()`.
*   **Typing:** It integrates cleanly with `typing.Protocol` and nominal typing systems.

---

### The Functional Approach: Lexical Closures

The alternative approach leverages Python’s first-class functions. We can define a function inside another function. If the inner function references variables from the outer function’s scope, it “closes over” those variables, keeping them alive even after the outer function has returned.

Here is the same EMA logic, implemented using a closure:

```python
from typing import Callable

def make_ema_filter(alpha: float) -> Callable[[float], float]:
    """
    Factory that returns a stateful closure for EMA calculation.
    """
    current_avg: float | None = None

    def smoother(new_sample: float) -> float:
        nonlocal current_avg # Crucial: allows modification of the outer scope
        
        if current_avg is None:
            current_avg = new_sample
        else:
            current_avg = (alpha * new_sample) + \
                          ((1 - alpha) * current_avg)
        
        return current_avg

    return smoother

# Usage
functional_smoother = make_ema_filter(alpha=0.1)

print(f"Sample 1: {functional_smoother(20.0):.2f}")
print(f"Sample 2: {functional_smoother(22.0):.2f}")
```

#### The nonlocal Keyword

In Python 2, this pattern was difficult because inner functions could read variables from the outer scope, but assigning to them would implicitly create a new local variable, breaking the link to the outer scope.

Python 3 introduced `nonlocal`, which explicitly tells the interpreter: “I am not defining a new variable; I am updating the reference to the variable defined in the enclosing scope.”

---

### Deep Dive: CPython Internals and Memory
#### 1. Anatomy of a Closure

To understand which approach is “better,” we must look at what CPython does under the hood.

When `make_ema_filter` returns the `smoother` function, the `smoother` object carries a hidden payload. It has a special attribute called `__closure__`.

```python
print(functional_smoother.__closure__)
# Output: (<cell at 0x...: float object at 0x...>,)
```

The `__closure__` attribute is a tuple of cells. Because the stack frame of `make_ema_filter` is gone after it returns, Python cannot store `current_avg` on the stack. Instead, Python detects that `current_avg` is a “free variable” (referenced but not defined in the inner function). It allocates a cell object on the heap to hold the reference to the float value.

Both the outer function and the inner function point to this cell. When `smoother` updates `current_avg`, it is updating the contents of that cell.

#### 2. Bytecode Analysis: LOAD_ATTR vs. LOAD_DEREF

Let’s inspect the bytecode to see the performance implications.

**The Class Approach (Method Call):**
`dis.dis(EMAFilter.__call__)`

Inside `EMAFilter.__call__`, accessing `self.alpha` involves:
1.  `LOAD_FAST` (load self)
2.  `LOAD_ATTR` (resolve alpha)

`LOAD_ATTR` is traditionally expensive. It involves traversing the MRO (Method Resolution Order) and checking the instance `__dict__`. While Python 3.11+ has introduced “specializing adaptive interpreters” to cache these lookups, it still involves dynamic dispatch.

**The Closure Approach (Function Call):**
Inside `smoother`, accessing `alpha` involves:
1.  `LOAD_DEREF` (load from closure cell)

`LOAD_DEREF` is a pointer dereference into the `__closure__` tuple. It is structurally static; the interpreter knows exactly where that variable lives at compile time. It bypasses the dynamic attribute lookup mechanism entirely.

#### 3. Memory Footprint

*   **Classes:** An instance usually requires a `__dict__` (a hash map) to store attributes, plus the overhead of the instance structure itself. This is relatively heavy. Using `__slots__` can optimize this, reducing the memory to just the size of the pointers.
*   **Closures:** A closure is a function object plus a small tuple of cell objects. For retaining a small amount of state (1–3 variables), closures generally consume less memory than full class instances.

---

### Best Practice: When to Use Which?
#### Use Closures When:

We have established that closures are slightly faster (due to `LOAD_DEREF`) and often more concise. Does that mean we should abandon classes? Absolutely not.

*   **The Interface is Single-Method:** If your class only has `__init__` and `__call__`, it is a “smell” that you are writing Java in Python. A closure is the Pythonic replacement for a single-method interface.
*   **State is Private:** Closures provide strong data hiding. There is no easy way for external code to reach into `functional_smoother` and mess with `current_avg` without using introspection hacks. The state is effectively private.
*   **Functional Composition:** You are working with higher-order functions (decorators, partials) where passing simple callables is expected.

#### Use Callable Classes When:

*   **Complex State:** If you have more than 3–4 state variables, `nonlocal` declarations become messy. A data class provides structure.
*   **Multiple Entry Points:** If you need to `reset()` the filter or inspect its configuration property, a class is mandatory. A closure typically only has one entry point (the function call).
*   **Type Hierarchies:** If you need `smoother` to be an instance of a specific abstract base class for type checking purposes (nominal typing), you must use a class.

---

### The Modern Hybrid: Using Protocols

In modern Python 3.10+, we can sometimes get the best of both worlds by strictly typing our functional interfaces while using lightweight implementations.

If you choose the functional route, do not leave the return type vague. Use `typing.Callable` or `typing.Protocol` to ensure your consumers know exactly what they are dealing with.

```python
from typing import Protocol

# Define the interface explicitly
class FilterStrategy(Protocol):
    def __call__(self, value: float) -> float: ...

# The factory returns something that adheres to the Protocol
def get_filter(kind: str) -> FilterStrategy:
    if kind == "ema":
        return make_ema_filter(0.1)
    # ... other strategies
    raise ValueError("Unknown filter")
```

---

### Conclusion

The debate between closures and callable classes is, at its heart, a debate between functional and object-oriented design paradigms.

Closures offer a lightweight, performant mechanism for state retention that relies on the elegant concept of lexical scoping and stack-frame cells. They represent the “purest” form of the Command pattern: a packet of logic with attached state, stripped of the boilerplate of class definitions.

However, classes remain the bedrock of structured application design. When the “command” grows in complexity, requires inspection, or demands a richer interface than a single call, the overhead of the `self` dot-lookup is a small price to pay for the clarity of an explicit data structure.

As a senior engineer, your role is to identify the “complexity tipping point.” Start with a function. When you find yourself needing a reset button, refactor to a class. But never write a class just to wrap a single variable and a single method.
