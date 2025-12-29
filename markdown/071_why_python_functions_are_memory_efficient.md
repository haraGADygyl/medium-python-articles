# Why Python Functions are Memory Efficient
#### How replacing Strategy classes with simple functions leverages Python’s internal object model to optimize memory and performance

**By Tihomir Manushev**  
*Dec 29, 2025 · 8 min read*

---

In the canon of software engineering, the “Gang of Four” (GoF) Design Patterns book is akin to scripture. It categorized twenty-three patterns that solved recurring problems in Object-Oriented Programming (OOP). However, as languages have evolved from the rigidity of C++ and Java to the dynamism of Python, the lines between these patterns have blurred.

One of the most profound realizations for a senior Python engineer is that the language often implements these patterns for you, intrinsically.

Consider the Strategy Pattern. It allows you to define a family of algorithms, encapsulate each one, and make them interchangeable. Then, consider the Flyweight Pattern, used to minimize memory usage by sharing as much data as possible with similar objects.

In traditional languages, you implement Strategy with classes, and if you have too many strategy instances, you optimize them with Flyweight. In Python, if you simply use functions as first-class objects, you get the Flyweight optimization for free. This article explores the mechanics of why that happens and the deep architectural implications for your codebase.

---

### The “Java-in-Python” Anti-Pattern

To understand the solution, we must first look at the problem. Developers coming from static languages often treat Python as “Java without braces.” They build elaborate class hierarchies for behavior that requires no state.

Let’s imagine a Logistics application. We need to calculate shipping costs based on weight and distance. The algorithm changes based on the provider (DHL, FedEx, USPS).

Here is the “Classic OOP” implementation. It is rigorous, type-safe, and unfortunately, heavy.

```python
from abc import ABC, abstractmethod
from decimal import Decimal
from dataclasses import dataclass

# The abstract strategy interface
class ShippingStrategy(ABC):
    @abstractmethod
    def calculate(self, weight_kg: float, distance_km: float) -> Decimal:
        """Calculate shipping cost."""

# Concrete Strategy 1
class FedExStrategy(ShippingStrategy):
    def calculate(self, weight_kg: float, distance_km: float) -> Decimal:
        return Decimal('3.50') + (Decimal('0.40') * Decimal(str(weight_kg)))

# Concrete Strategy 2
class PostalServiceStrategy(ShippingStrategy):
    def calculate(self, weight_kg: float, distance_km: float) -> Decimal:
        return Decimal('1.00') + (Decimal('0.20') * Decimal(str(weight_kg)))

# The Context
@dataclass
class Shipment:
    weight: float
    distance: float
    strategy: ShippingStrategy

    def get_cost(self) -> Decimal:
        return self.strategy.calculate(self.weight, self.distance)

# Usage
# We instantiate a new strategy object for every shipment
package_a = Shipment(10.5, 100.0, FedExStrategy())
package_b = Shipment(2.0, 50.0, PostalServiceStrategy())
```

In the code above, `FedExStrategy` and `PostalServiceStrategy` are classes. When we perform `FedExStrategy()`, we are calling the constructor. This creates a new instance of the object in memory.

If we process 100,000 shipments in a batch job:

*   We allocate 100,000 `Shipment` objects (unavoidable).
*   We allocate 100,000 `ShippingStrategy` objects (completely avoidable).

Unless the developer manually implements a Registry or a Singleton pattern to reuse these strategy instances, the Python memory manager is forced to allocate, track, and eventually garbage-collect thousands of identical, stateless objects. Each object carries the overhead of the PyObject head structure and, depending on implementation, a `__dict__` for attributes it doesn’t even use.

---

### The Functional Refactor: Built-in Flyweights

Python functions are first-class objects. This means they can be passed around just like integers or strings. Crucially, a function defined in a module is created once when the module is imported.

Let’s refactor the shipping example to use functions. We will use modern Python 3.10+ typing to maintain the same level of interface safety as the Abstract Base Class.

```python
from decimal import Decimal
from dataclasses import dataclass
from typing import Callable, TypeAlias

# Define a TypeAlias for clarity
# This replaces the Abstract Base Class
ShippingCalculator: TypeAlias = Callable[[float, float], Decimal]

def calculate_fedex(weight_kg: float, distance_km: float) -> Decimal:
    """FedEx: High base rate, medium weight multiplier."""
    return Decimal('3.50') + (Decimal('0.40') * Decimal(str(weight_kg)))

def calculate_postal(weight_kg: float, distance_km: float) -> Decimal:
    """Postal: Low base rate, low weight multiplier."""
    return Decimal('1.00') + (Decimal('0.20') * Decimal(str(weight_kg)))

@dataclass
class Shipment:
    weight: float
    distance: float
    # The strategy is now just a function type
    calculator: ShippingCalculator 

    def get_cost(self) -> Decimal:
        # We invoke the function directly
        return self.calculator(self.weight, self.distance)

# Usage
# We pass the FUNCTION itself, not a call to it.
package_a = Shipment(10.5, 100.0, calculate_fedex)
package_b = Shipment(2.0, 50.0, calculate_postal)
```

The Flyweight Pattern describes an object that minimizes memory usage by sharing as much data as possible with other similar objects.

In the functional example above, `calculate_fedex` is a function object.

*   How many `Shipment` objects exist? 100,000.
*   How many `calculate_fedex` objects exist? One. Exactly one.

Regardless of how many shipments reference `calculate_fedex`, they all point to the exact same memory address where that function resides. The “intrinsic state” (the algorithm code) is stored in the function object. The “extrinsic state” (the weight and distance) is passed in as arguments. This is the textbook definition of the Flyweight pattern, and Python gives it to you simply for using `def`.

---

### Under the Hood: CPython Internals

To understand why this is so efficient, we need to look at how CPython (the standard Python implementation) handles functions versus objects.

**1. The PyFunctionObject**

When Python imports a module, it executes the `def` statements. This compiles the body of the function into a code object (`PyCodeObject`) containing the bytecode. It then wraps this code object in a function object (`PyFunctionObject`).

The function object is relatively small. It basically holds pointers to:

*   The compiled bytecode (`__code__`).
*   The global namespace (`__globals__`).
*   Default argument values (`__defaults__`).

This object is a singleton within the scope of the module.

**2. The Cost of Classes**

Contrast this with `FedExStrategy()`. Even if the class has no `__init__`, calling the class creates a new instance.

*   It allocates memory for the instance structure.
*   It runs the initializer chain.
*   It typically creates a `__dict__` for the instance (unless `__slots__` is used), which is a hash map waiting to be filled with attributes.

Even an empty class instance in Python consumes roughly 48 bytes + the dictionary overhead. A function reference is merely a pointer (8 bytes on a 64-bit system).

---

### Verification

We can verify this behavior using Python’s `id()` function, which returns the memory address of an object.

```python
# --- OOP Approach ---
s1 = FedExStrategy()
s2 = FedExStrategy()

print(f"OOP Identity Check: {id(s1) == id(s2)}") 
# Output: False
# s1 and s2 are distinct objects occupying different memory regions.

# --- Functional Approach ---
f1 = calculate_fedex
f2 = calculate_fedex

print(f"Functional Identity Check: {id(f1) == id(f2)}")
# Output: True
# f1 and f2 point to the exact same object.
```

---

### Performance Implications

The memory savings become significant at scale. If your application processes millions of transactions, replacing single-method strategy classes with stateless functions removes millions of allocations from the heap. This reduces memory fragmentation and, arguably more importantly, reduces “GC Pressure” (Garbage Collection Pressure).

The Python Garbage Collector (GC) is a generational reference-counting collector. Every time you create a new `FedExStrategy` instance, the GC has to track it. When the Shipment is done, the GC has to destroy it. By using the function (Flyweight), there is no creation or destruction lifecycle for the strategy component — it is static and eternal for the life of the process.

---

### When Functions Aren’t Enough

Is the class-based Strategy pattern dead? Not entirely.

The functional approach assumes the strategy is stateless. The `calculate_fedex` function relies only on its arguments (weight, distance). But what if the strategy needs to remember something?

Suppose a strategy needs to apply a discount only after the third time it is used, or it needs to pull dynamic configuration from a database upon initialization and cache it.

**Option 1: Closures (The Functional State)**

We can still avoid classes by using closures, which are functions that retain access to variables from their enclosing scope.

```python
def make_bulk_strategy(discount_threshold: int, discount_rate: Decimal) -> ShippingCalculator:
    # This outer function is a "Factory"
    
    def strategy(weight: float, distance: float) -> Decimal:
        base_cost = Decimal('1.00') * Decimal(str(distance))
        if weight > discount_threshold:
            return base_cost * (1 - discount_rate)
        return base_cost
        
    return strategy

# Create a customized strategy
configured_strategy = make_bulk_strategy(20, Decimal('0.15'))
```

Here, `configured_strategy` holds state (the threshold and rate) inside its `__closure__` attribute. It is still often lighter than a full class instance, though we lose the “Single Global Instance” benefit because we are creating a new closure every time we call the factory.

**Option 2: The Callable Class**

If the state is complex, or if the strategy requires multiple helper methods, a class is appropriate. However, to keep the API consistent with the functional approach, we should implement `__call__`.

```python
class DatabaseRateStrategy:
    def __init__(self, db_connection_str: str):
        self.rates = self._fetch_rates(db_connection_str)

    def _fetch_rates(self, conn_str: str) -> dict:
        # Complex logic to load data
        return {"base": Decimal('5.00')}

    def __call__(self, weight: float, distance: float) -> Decimal:
        # Makes the instance callable like a function
        return self.rates["base"] * Decimal(str(weight))
```

This allows our `Shipment` context to remain agnostic. It types the field as `Callable`, so it accepts simple functions or complex callable class instances.

---

### Best Practices for Modern Python

To leverage functions as strategies effectively in production code, follow these three directives:

1.  **Strict Type Hinting:** Never use `Callable` without arguments. `Callable[…, Any]` is a code smell. Be explicit: `Callable[[float, float], Decimal]`. This ensures that your “loose” functions adhere to a strict interface, checked by MyPy or Pyright.
2.  **Use dataclasses:** As shown in the examples, dataclasses reduce boilerplate and pair perfectly with functional attributes.
3.  **Module-Level Grouping:** If you have 20 different shipping strategies, don’t clutter your main logic. Place them in a `strategies.py` module. You can then use `inspect.getmembers()` to dynamically load them into a registry if you need “plugin” behavior — another advantage of modules being first-class objects.

---

### Conclusion

The “Gang of Four” patterns were written for a different era and different languages. While the intent of the Strategy and Flyweight patterns remains valid, their implementation in Python should look vastly different from C++.

By recognizing that Python functions are already stateless, shared, first-class objects, we can flatten our architecture. We remove the need for “Concrete Strategy” classes and the “Flyweight Factory” boilerplate. The result is code that is not only more readable and concise but also significantly more memory-efficient.

In Python, the most efficient code is often the code you don’t write. Don’t write a class when a function will do.
