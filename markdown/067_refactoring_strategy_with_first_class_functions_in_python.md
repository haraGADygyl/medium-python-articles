# Refactoring Strategy with First-Class Functions in Python
#### How to leverage Python’s first-class functions to reduce lines of code, improve memory efficiency, and simplify your architecture

**By Tihomir Manushev**  
*Dec 24, 2025 · 8 min read*

---

In the pantheon of software engineering, the “Gang of Four” (GoF) Design Patterns book is akin to scripture. It provided a common vocabulary for complex architectural problems. However, scriptures are often interpreted literally rather than contextually. When developers migrate from statically typed, pure object-oriented languages (like Java or C++) to Python, they often bring along a heavy suitcase of architectural patterns that simply aren’t necessary.

The Strategy Pattern is the most common casualty of this translation error.

In a traditional implementation, the Strategy pattern requires an interface (Abstract Base Class), a context class, and multiple concrete strategy classes. It is a ceremony of inheritance and polymorphism designed to allow algorithms to be interchangeable.

But Python is not Java. In Python, functions are first-class citizens. They are objects. They can be passed, stored, introspected, and executed. When we embrace this fact, the Strategy pattern collapses from a sprawling class hierarchy into a lightweight, idiomatic, and highly readable functional composition.

In this article, we will dismantle the classic object-oriented boilerplate and reconstruct a production-grade Strategy pattern using Python 3.10+ semantics, type hinting, and functional dispatch.

---

### The “Classic” Implementation: A Study in Excess

Let us imagine a logistics domain. We need to calculate shipping costs for packages based on different carriers (Air, Ground, Sea). The rules vary: some charge by weight, some by volume, and some offer flat rates.

If we were following a strictly object-oriented textbook, we would start by defining an interface to ensure every strategy adheres to a contract.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class Package:
    weight_kg: Decimal
    volume_m3: Decimal
    destination_zone: str

class ShippingStrategy(ABC):
    """The Abstract Base Class defining the interface."""
    
    @abstractmethod
    def calculate(self, package: Package) -> Decimal:
        pass

# Concrete Strategy 1
class AirExpress(ShippingStrategy):
    def calculate(self, package: Package) -> Decimal:
        # $10 base + $5 per kg
        return Decimal("10.00") + (package.weight_kg * Decimal("5.00"))

# Concrete Strategy 2
class GroundStandard(ShippingStrategy):
    def calculate(self, package: Package) -> Decimal:
        # $2 base + $1 per kg
        return Decimal("2.00") + (package.weight_kg * Decimal("1.00"))

# Concrete Strategy 3
class SeaFreight(ShippingStrategy):
    def calculate(self, package: Package) -> Decimal:
        # $50 flat rate for large volume
        if package.volume_m3 > Decimal("1.0"):
             return Decimal("50.00")
        return Decimal("25.00")

class ShippingCostCalculator:
    """The Context class."""
    
    def __init__(self, strategy: ShippingStrategy):
        self.strategy = strategy

    def get_cost(self, package: Package) -> Decimal:
        return self.strategy.calculate(package)
```

This code works. It is type-safe and polymorphic. But look at the “ceremony” required to perform simple arithmetic.

1.  **Class Proliferation:** We have created four classes to wrap three formulas.
2.  **Stateless Objects:** The `AirExpress` and `SeaFreight` instances hold no state (`self` is unused in the methods, aside from method signature compliance). We are instantiating objects just to execute a single method.
3.  **Verbosity:** We have lines of boilerplate code (inheritance, `def calculate`, `pass`) that contribute nothing to the business logic.

In Python, a single-method class that holds no state is a code smell. It’s usually just a function crying for liberation.

---

### The Paradigm Shift: Functions are First-Class Objects

In C++ or old-school Java, you need a class to bundle code (behavior) so it can be passed around. In Python, code is already an object. A function defined with `def` is an instance of the function class.

If we refactor the example above, we can discard the `ShippingStrategy` ABC entirely. We don’t need an abstract class to define an interface; we can use Type Hints to define a signature contract.

Here is the Pythonic refactoring:

```python
from decimal import Decimal
from typing import Callable, TypeAlias
from dataclasses import dataclass

@dataclass
class Package:
    weight_kg: Decimal
    volume_m3: Decimal
    destination_zone: str

# Define the interface using a TypeAlias for readability
PricingFn: TypeAlias = Callable[[Package], Decimal]

def air_express(package: Package) -> Decimal:
    return Decimal("10.00") + (package.weight_kg * Decimal("5.00"))

def ground_standard(package: Package) -> Decimal:
    return Decimal("2.00") + (package.weight_kg * Decimal("1.00"))

def sea_freight(package: Package) -> Decimal:
    if package.volume_m3 > Decimal("1.0"):
         return Decimal("50.00")
    return Decimal("25.00")

@dataclass
class Shipment:
    package: Package
    # The strategy is just a callable field
    pricing_rule: PricingFn 

    def calculate_cost(self) -> Decimal:
        # We invoke the function directly
        return self.pricing_rule(self.package)

pkg = Package(
    weight_kg=Decimal("10"),
    volume_m3=Decimal("0.5"),
    destination_zone="US-EAST"
)

# Pass the function itself, not an instance of a class
shipment = Shipment(package=pkg, pricing_rule=air_express)
cost = shipment.calculate_cost()
print(cost)
```

*   **Visual Noise Reduction:** We reduced the line count significantly. The business logic is front and center, not buried inside class definitions.
*   **Memory Efficiency (The Flyweight Effect):** In the object-oriented approach, every time you instantiated a `ShippingCostCalculator`, you likely instantiated a new `AirExpress` object. While Python is efficient, creating objects involves memory allocation, `__init__` calls, and garbage collection overhead. In the functional approach, `air_express` is a module-level function created once when the Python process starts. It acts as a natural Flyweight. No matter how many `Shipment` objects you create, they all reference the exact same function object.
*   **Removal of self:** We eliminated the `self` parameter, which was misleading since the strategies didn’t access instance state anyway.

---

### Advanced Refactoring: The Decoupled Registry

One valid criticism of the simple functional approach is discoverability. In the OOP version, you can look at the subclasses of `ShippingStrategy` to find all available options. How do we manage a growing list of functional strategies without hard-coding a list?

We can use the Decorator Pattern to create a self-registering plugin system. This is a powerful technique often seen in web frameworks (like Flask or FastAPI) but is equally applicable to internal business logic.

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, TypeAlias


@dataclass
class Package:
    weight_kg: Decimal
    volume_m3: Decimal
    destination_zone: str


# Define the interface using a TypeAlias for readability
PricingFn: TypeAlias = Callable[[Package], Decimal]

# The Registry
_PRICING_STRATEGIES: list[PricingFn] = []


def register_strategy(active: bool = True):
    """
    A decorator to register a pricing function.
    Can be toggled off via the 'active' flag.
    """

    def decorator(fn: PricingFn) -> PricingFn:
        if active:
            _PRICING_STRATEGIES.append(fn)
        return fn

    return decorator


@register_strategy()
def air_express(package: Package) -> Decimal:
    """Fast but expensive."""
    return Decimal("10.00") + (package.weight_kg * Decimal("5.00"))


@register_strategy()
def ground_standard(package: Package) -> Decimal:
    """Slow but cheap."""
    return Decimal("2.00") + (package.weight_kg * Decimal("1.00"))


@register_strategy(active=False)
def experimental_drone(package: Package) -> Decimal:
    """Not approved by regulators yet."""
    return Decimal("100.00")


def find_best_rate(package: Package) -> Decimal:
    """
    Meta-Strategy: iterates over all registered strategies
    to find the lowest cost.
    """
    if not _PRICING_STRATEGIES:
        raise ValueError("No pricing strategies registered!")

    costs = [strategy(package) for strategy in _PRICING_STRATEGIES]
    return min(costs)
```

By adding `@register_strategy()` above our function definitions, we invert the control dependency. The `find_best_rate` function doesn’t need to know the names of the strategies. It simply iterates over `_PRICING_STRATEGIES`.

When the module is imported, Python executes the decorators, populating the list automatically. This makes adding a new strategy as simple as writing a function and tagging it. No other code needs to change — a perfect adherence to the Open/Closed Principle.

---

### Internal Mechanics: Why `__call__` Matters

To truly understand why functions can replace Strategy classes, we must look at the CPython internals.

When you define a class in Python and give it a method, you are creating a type.

```python
class MyStrategy:
    def calculate(self): ...
```

When you call `instance.calculate()`, Python performs a descriptor lookup to bind the function to the instance, inserting `self` as the first argument.

However, if we look at the C source code for Python, everything that can be called (functions, methods, classes) implements the `__call__` protocol (specifically, the `tp_call` slot in the C structure).

When we define a Strategy class with only a `calculate` method, we are essentially building a wrapper around `__call__`. Refactoring this to a function removes the wrapper. The function object itself supports `__call__`.

If you absolutely need to maintain state (e.g., a strategy that remembers how many times it has been called), you can still use a class, but you should implement `__call__` directly to make the instance behave like a function:

```python
class StatefulStrategy:
    def __init__(self, discount: Decimal):
        self.discount = discount
        self.usage_count = 0

    def __call__(self, package: Package) -> Decimal:
        self.usage_count += 1
        base_cost = Decimal("10.00")
        return base_cost - self.discount
```

This hybrid approach allows this class instance to be passed into our `Shipment` object just like our plain functions, because our type hint `PricingFn` (Callable) accepts anything that implements `__call__`.

---

### Performance Analysis

Let’s briefly analyze the computational complexity and memory footprint of these approaches.

**Time Complexity:**
Both the Class-based and Function-based approaches operate in O(1) dispatch time. However, the function call is slightly faster in pure CPU cycles because it avoids the attribute lookup of `self.strategy.calculate`. It jumps straight to the code object execution.

**Space Complexity:**
This is where the functional approach wins significantly.

*   **Class Strategy:** Requires one PyObject for the instance, plus a `__dict__` (usually) for attributes. If you process 1,000,000 orders and create a new Strategy object for each, you trigger massive Garbage Collection (GC) pressure.
*   **Functional Strategy:** Requires a single PyFunctionObject loaded in memory. References to this function are pointers (64 bits). You can process 1,000,000 orders passing the same pointer. There is zero garbage collection overhead for the strategy itself.

---

### Best Practices for Production

When implementing this in a real-world Python 3.10+ application, follow these guidelines:

1.  **Use `typing.Protocol` or `Callable`:** Strictly type hint your context class. Do not leave the strategy argument as `Any`.
2.  **Prefer Functions for Stateless Logic:** If the strategy only transforms inputs to outputs without side effects or history, use a function.
3.  **Use Modules as Namespaces:** Instead of grouping strategies as static methods inside a class, group them in a module (e.g., `logistics.strategies`).
4.  **Document with Docstrings:** Since you lose the explicit method name override from an ABC, ensure your function docstrings are descriptive.

---

### Conclusion

The Strategy Pattern remains a cornerstone of clean software design, encapsulating the concept of interchangeable algorithms. However, the mechanism of implementation must evolve with the language.

In Python, treating functions as second-class citizens that must be wrapped in classes is an architectural debt. By embracing functions as first-class objects, we reduce boilerplate, improve memory locality, and write code that is arguably more readable and easier to test.

The next time you find yourself writing an Abstract Base Class with a single method named `execute` or `run`, stop. You probably just need a function.
