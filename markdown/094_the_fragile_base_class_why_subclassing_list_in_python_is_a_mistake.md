# The Fragile Base Class: Why Subclassing list in Python is a Mistake
#### Deep dive into the pitfalls of subclassing built-ins and leveraging the Sequence Protocol for robust data structures

**By Tihomir Manushev**  
*Jan 28, 2026 · 8 min read*

---

In the ecosystem of object-oriented programming, there is perhaps no mantra more repeated — and more frequently ignored — than “Composition over Inheritance.” In Python, this principle is not merely a stylistic suggestion; it is a defensive necessity, particularly when dealing with the language’s built-in collection types.

A common scenario for a senior developer runs as follows: You need a list that only accepts positive integers, or perhaps a dictionary that automatically logs every insertion to a database. The immediate impulse is to inherit from `list` or `dict`, override `__setitem__` or `append`, and call it a day. It feels natural. It feels “Pythonic.”

However, this approach is fraught with peril. In CPython (the standard Python implementation), built-in types are optimized for performance in ways that often flagrantly violate standard object-oriented polymorphism rules. When you inherit directly from `list`, you are entering a minefield where overridden methods are silently ignored, leading to subtle data corruption bugs that only manifest in edge cases.

In this article, we will dissect the internal mechanics of why subclassing built-ins is dangerous, and we will demonstrate how to build robust, production-grade custom sequences using composition and the Python Sequence Protocol.

---

### The Core Problem: CPython’s Shortcuts

To understand why inheritance fails us here, we must look under the hood of the interpreter.

Python code interacts with C structures. When you create a class `class MyList(list):`, you are inheriting from a type implemented in C. To maintain the blistering speed of standard lists, the C code for `list` methods often calls other C functions directly, bypassing the Python class hierarchy lookup (the MRO, or Method Resolution Order).

For example, the `list.extend()` method implementation in C does not iterate over the input and call `self.append()` or `self.__setitem__` for each element. Instead, it performs a low-level memory copy or resize operation. If you have painstakingly overridden `append()` in your subclass to perform validation, `extend()` will completely bypass it. Your constraints are ignored, and invalid data enters your structure.

This is not a bug; it is a design choice favoring speed over purity. However, for the application engineer, it means that `list` does not behave like a standard Python class designed for extension.

---

### The Broken Implementation

Let’s look at a concrete example of this failure. Suppose we want a `ProhibitedList` that prevents the number 13 from being added.

```python
class ProhibitedList(list):
    def append(self, item):
        if item == 13:
            raise ValueError("The number 13 is prohibited.")
        super().append(item)

    def __setitem__(self, index, item):
        if item == 13:
            raise ValueError("The number 13 is prohibited.")
        super().__setitem__(index, item)

# Let's test it
safe_store = ProhibitedList([1, 2, 3])

# This works as expected:
try:
    safe_store.append(13)
except ValueError as e:
    print(f"Caught expected error: {e}") 

# BUT, this bypasses our logic entirely:
safe_store.extend([10, 11, 12, 13]) 
print(f"Current state: {safe_store}") 
```

In the example above, `extend` (and the `+=` operator) knows nothing about our Python-level `append` override. To fix this using inheritance, you would have to override every single method that mutates the list (`extend`, `insert`, `__iadd__`, `__imul__`, etc.). This is tedious, error-prone, and fragile.

---

### The Solution: Composition and Protocols

The superior architectural pattern is Composition. Instead of being a list, your custom collection should *contain* a list. By wrapping a standard list in a private attribute and exposing only the methods you wish to support, you gain total control over the data ingress and egress.

Python’s reliance on Duck Typing (dynamic protocols) makes this incredibly easy. You do not need to inherit from a specific interface to be treated as a sequence. You simply need to implement:

1.  **`__len__`**: To answer “how big am I?”
2.  **`__getitem__`**: To answer “what is at index X?”

If you implement these two, your object effectively *is* a sequence. It can be iterated over, unwrapped, and used in `for` loops.

---

### Designing a Robust Sequence

Let us design a `TimeSeries` collection. This structure will hold floating-point readings from a sensor. It must ensure that all data points are floats, and it should support slicing. Crucially, when we slice this object, we expect to get a new `TimeSeries` instance back, not a raw list.

We will rely on the `typing` module (standard in Python 3.10+) for clarity, but the mechanics are pure Python data model.

```python
from collections.abc import Sequence, Iterator
from typing import overload, Union, TypeAlias
import reprlib

# Modern type alias for clarity
Number: TypeAlias = int | float

class TimeSeries:
    """
    An immutable sequence of sensor readings.
    Ensures all data is stored as floats.
    """
    
    __slots__ = ('_readings',)

    def __init__(self, data: Sequence[Number]) -> None:
        # We copy the data to ensure encapsulation and enforce type safety
        self._readings: list[float] = [float(x) for x in data]

    def __len__(self) -> int:
        return len(self._readings)

    # We use @overload to tell static type checkers what to expect
    @overload
    def __getitem__(self, index: int) -> float: ...

    @overload
    def __getitem__(self, index: slice) -> 'TimeSeries': ...

    def __getitem__(self, index: int | slice) -> Union[float, 'TimeSeries']:
        cls = type(self)
        
        # Handle Slicing
        if isinstance(index, slice):
            # We delegate the slicing logic to the underlying list,
            # but wrap the result back in our class.
            return cls(self._readings[index])
        
        # Handle Integer Indexing
        # We rely on the underlying list to raise IndexError if needed
        return self._readings[index]

    def __iter__(self) -> Iterator[float]:
        # Delegating iteration is often faster than relying on __getitem__
        return iter(self._readings)

    def __repr__(self) -> str:
        # Use reprlib to safely print large datasets without flooding the console
        components = reprlib.repr(self._readings)
        # reprlib returns string like "[1.0, 2.0, ...]", we want "TimeSeries([1.0, ...])"
        return f'{type(self).__name__}({components})'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TimeSeries):
            return self._readings == other._readings
        if isinstance(other, list):
            return self._readings == other
        return NotImplemented
```

*   **The Storage Strategy:** We define `_readings` as our internal storage. By defining `__slots__ = ('_readings',)`, we tell PVM (Python Virtual Machine) not to create a `__dict__` for instances of this class. This saves significant memory if we are instantiating thousands of small `TimeSeries` objects, effectively making our object as lightweight as a standard wrapper.
*   **The Slice-Aware `__getitem__`:** This is the most critical part of the sequence protocol. Python passes a slice object (e.g., `slice(0, 5, None)`) to `__getitem__` when you request `obj[0:5]`. If we simply returned `self._readings[index]`, the user would get a standard list back. This breaks method chaining and polymorphism. If the user sliced a `TimeSeries`, they expect a `TimeSeries` back so they can continue to use its specific methods. By catching `isinstance(index, slice)` and returning `cls(self._readings[index])`, we preserve the type identity of our collection.
*   **Defensive Initialization:** In `__init__`, we don’t just assign `self._readings = data`. If we did that, and `data` was a mutable list passed by the caller, the caller could modify the list externally, corrupting our object’s state. By doing a list comprehension `[float(x) for x in data]`, we achieve two goals:
    1.  Sanitization: We force conversion to float immediately.
    2.  Immutability (Internal): We create a private copy of the data.

---

### Best Practice Implementation: Mutable Collections

If you actually need a mutable list (like the `ProhibitedList` we failed to build earlier), composition is still the answer. However, implementing `insert`, `del`, `pop`, `remove`, `append`, and `extend` manually is tedious.

In these cases, Python provides a specific tool in the `collections` module: `UserList`.

`UserList` is a class written in pure Python specifically designed to be inherited. Unlike `list`, `UserList` stores its data in an instance attribute named `data` (a standard list). When you call `extend` on a `UserList`, it iterates and calls `append` via Python, respecting your overrides.

However, since we are strictly discussing composition, let’s look at how to implement a fully robust, mutable `TransactionQueue` using composition that handles the tricky parts of list emulation.

```python
from collections.abc import MutableSequence

class TransactionQueue(MutableSequence):
    """
    A queue that logs operations and prevents specific IDs.
    Implements MutableSequence to get free mixin methods like 'append',
    'reverse', 'pop' based on our core implementation.
    """

    def __init__(self, initial_data=None):
        self._db = list(initial_data) if initial_data else []
        self._banned_ids = {13, 666}

    def _check_valid(self, value):
        if value in self._banned_ids:
            raise ValueError(f"Transaction ID {value} is banned.")

    def __len__(self):
        return len(self._db)

    def __getitem__(self, index):
        return self._db[index]

    def __setitem__(self, index, value):
        # We must handle both single updates and slice updates
        if isinstance(index, slice):
            for item in value:
                self._check_valid(item)
        else:
            self._check_valid(value)
        
        self._db[index] = value

    def __delitem__(self, index):
        del self._db[index]

    def insert(self, index, value):
        self._check_valid(value)
        self._db.insert(index, value)
    
    # By inheriting from collections.abc.MutableSequence, 
    # we get append, extend, iadd, etc., for free!
    # They are implemented in the ABC to call our insert() and __setitem__().
```

---

### The Role of Abstract Base Classes (ABCs)

In `TransactionQueue`, we inherit from `collections.abc.MutableSequence`. This is not the same as inheriting from `list`. The `MutableSequence` ABC does not provide storage; it provides logic.

Because we implemented the abstract methods (`__len__`, `__getitem__`, `__setitem__`, `__delitem__`, `insert`), the ABC dynamically provides us with concrete implementations of `append`, `extend`, `pop`, `remove`, and `reverse`.

Crucially, the ABC’s implementation of `extend` is written in Python, essentially looping and calling our `insert` or `append`. This ensures our validation logic in `_check_valid` is never bypassed.

---

### Performance Considerations

One might argue that composition introduces overhead. This is technically true. Every time we access `TimeSeries[i]`, Python must lookup `__getitem__`, execute our wrapper logic, and then access the underlying list.

However, in 99% of Python applications, this overhead is negligible compared to the business logic processing the data. The safety gained — knowing that your data integrity constraints cannot be bypassed — far outweighs the nanosecond-scale cost of a double pointer dereference.

If raw speed is the absolute bottleneck (e.g., matrix multiplication), you should be using numpy arrays or pandas dataframes, not standard Python lists, subclassed or otherwise.

---

### Conclusion

When building custom collections in Python 3, the “Is-A” relationship often deceives us. A `ProhibitedList` is a list in concept, but making it a subclass of the built-in `list` implementation is an architectural trap due to CPython’s internal optimizations.

By embracing Composition, we gain:

*   **Encapsulation:** We expose only what is needed.
*   **Safety:** We prevent C-level shortcuts from bypassing our validation logic.
*   **Clarity:** We explicitly define the behavior of slicing and storage.

Whether you are wrapping a simple list in a class that implements `__len__` and `__getitem__`, or leveraging `collections.abc` to fill in the blanks, remember: hold your data, don’t inherit it.
