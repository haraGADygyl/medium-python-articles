# Reflection in Python: Building Auto-Discovering Architectures
#### Leveraging Python’s dynamic nature to implement the Open/Closed Principle without class inheritance

**By Tihomir Manushev**  
*Dec 28, 2025 · 6 min read*

---

In the world of statically typed languages like C++ or Java, the relationship between a caller and a callee is historically rigid. You define an interface, implement a concrete class, and instantiate it. The compiler locks this relationship in place long before the code runs.

Python, however, is a dynamic language. In CPython, a module is not just a namespace; it is a first-class object (`PyModule_Type`) containing a dictionary (`__dict__`) that maps variable names to values. This fundamental architectural difference allows us to invert control in powerful ways.

Instead of hard-coding a registry of available algorithms (a common maintenance headache known as the “Registry of Death”), we can leverage introspection. We can write code that examines other code at runtime, automatically discovering and dispatching strategies without manual registration.

In this article, we will explore how to modernize the Strategy Pattern using the `inspect` module, replacing rigid class hierarchies with fluid, auto-discovering functional architectures.

---

### The Problem: The Open/Closed Violation

Imagine we are building a Payroll System for a multinational corporation. We need to calculate year-end bonuses. The rules for bonuses are volatile — Sales gets a commission-based bonus, Engineering gets a performance-multiplier, and HR gets a fixed rate.

The “Classic” Object-Oriented approach dictates defining an abstract base class `BonusCalculator` and creating subclasses like `SalesBonus`, `EngineeringBonus`, etc.

The bottleneck arises in the Context class (the payroll engine):

```python
# The "Registry of Death" approach
from bonuses import SalesBonus, EngineeringBonus, HRBonus

class PayrollProcessor:
    def get_bonus_strategy(self, department: str):
        if department == 'sales':
            return SalesBonus()
        elif department == 'engineering':
            return EngineeringBonus()
        elif department == 'hr':
            return HRBonus()
        # Every time we add a department, we must modify this file.
        # This violates the Open/Closed Principle.
```

This code is fragile. Adding a Marketing department requires modifying the core processor logic. In Python, where functions are first-class citizens, we can do better. We can create a system where the `PayrollProcessor` simply looks at a module, finds the relevant function, and executes it.

---

### Mechanics of Introspection
#### The globals() Dictionary vs. inspect

At the CPython level, every stack frame has access to a dictionary representing the global scope. Calling the built-in `globals()` function returns this dictionary.

While iterating over `globals()` allows you to find functions in the current module, it is fraught with peril:

1.  **Pollution:** It contains variables, imported modules, and built-ins.
2.  **Mutability:** It reflects the current state, which can change during runtime.
3.  **Recursion Risks:** If your dispatch function is in the same module, you might accidentally call yourself recursively.

#### The inspect Module

The standard library `inspect` module provides a higher-level, safer API for introspection. It handles the nuances of retrieving members from objects, managing descriptors, and filtering types.

Specifically, `inspect.getmembers(object, predicate)` is our primary tool.

*   `object`: The module or class to inspect.
*   `predicate`: A filter function (like `inspect.isfunction`) that returns `True` if the member should be included.

This allows us to treat a Python module as a Strategy Factory.

---

### The Auto-Discovering Payroll System

Let’s build a solution where adding a new bonus rule is as simple as defining a function with a specific naming convention in a rules module. No other code changes are required.

#### 1. The Domain Models

First, we define our data structures using modern Python 3.10+ features.

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import TypeAlias

# Precise monetary handling
Money: TypeAlias = Decimal

@dataclass(frozen=True)
class Employee:
    name: str
    department: str
    salary: Money
    performance_score: float  # 0.0 to 1.0
```

#### 2. The Strategy Module (bonus_rules.py)

This module contains only the logic for calculations. It effectively replaces the concrete classes in the GoF Strategy pattern.

```python
# bonus_rules.py
from decimal import Decimal

def _helper_function():
    """Private helper, should be ignored by the inspector."""
    pass

def sales_policy(emp) -> Decimal:
    """Sales gets 10% of salary plus performance kicker."""
    base = emp.salary * Decimal('0.10')
    kicker = emp.salary * Decimal(str(emp.performance_score)) * Decimal('0.5')
    return base + kicker

def engineering_policy(emp) -> Decimal:
    """Engineering gets a flat 15% bonus based on score."""
    if emp.performance_score < 0.5:
        return Decimal('0.00')
    return emp.salary * Decimal('0.15')

def marketing_policy(emp) -> Decimal:
    """Marketing gets a fixed $5,000 bonus."""
    return Decimal('5000.00')
```

#### 3. The Dynamic Dispatcher

Now, the core logic. This class loads the rules module, inspects it for valid strategies, and dispatches execution.

```python
# payroll.py
import inspect
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Dict, TypeAlias
import types

# --- IMPORT THE MODULE FOR INSPECTION ---
# We import the entire module object so we can pass it to our
# strategy loader.
import bonus_rules

# --- Domain Models ---
Money: TypeAlias = Decimal

@dataclass(frozen=True)
class Employee:
    name: str
    department: str
    salary: Money
    performance_score: float

# --- The Dynamic Dispatcher ---

StrategyFunc = Callable[[Employee], Money]

class PayrollSystem:
    def __init__(self, rules_module: types.ModuleType):
        self._strategies: Dict[str, StrategyFunc] = {}
        self._load_strategies(rules_module)

    def _load_strategies(self, module: types.ModuleType) -> None:
        """
        Introspects the module to find all valid bonus policies.
        Convention: Function name must end with '_policy'.
        """
        print(f"--- Introspecting module: {module.__name__} ---")

        # inspect.getmembers(module) requires the module object itself.
        functions = inspect.getmembers(module, inspect.isfunction)

        for name, func in functions:
            if name.endswith('_policy'):
                # Extract department name: 'sales_policy' -> 'sales'
                dept_key = name.replace('_policy', '')
                self._strategies[dept_key] = func
                print(f"Registered strategy for: {dept_key.upper()}")

    def calculate_bonus(self, employee: Employee) -> Money:
        strategy = self._strategies.get(employee.department)

        if not strategy:
            raise NotImplementedError(
                f"No bonus policy defined for department: {employee.department}"
            )

        return strategy(employee)

# --- Execution ---

def main():
    # Pass the imported module object 'bonus_rules' to the system
    payroll = PayrollSystem(bonus_rules)

    # Create Employees
    alice = Employee("Alice", "sales", Decimal('50000'), 0.9)
    bob = Employee("Bob", "engineering", Decimal('80000'), 0.8)
    charlie = Employee("Charlie", "marketing", Decimal('60000'), 0.5)

    print("\n--- Processing Payroll ---")
    employees = [alice, bob, charlie]

    for emp in employees:
        try:
            bonus = payroll.calculate_bonus(emp)
            print(f"{emp.name} ({emp.department}): ${bonus:.2f}")
        except NotImplementedError as e:
            print(f"Error for {emp.name}: {e}")

if __name__ == "__main__":
    main()
```

Notice that `_helper_function` was ignored because it did not match the `endswith('_policy')` naming convention. The `PayrollSystem` is now decoupled from the implementation details of the bonuses. To add a generic `hr_policy`, we simply write the function in the `bonus_rules` module; the system picks it up automatically on the next restart.

---

### Best Practice Implementation: Safety and Validation

While the example above works, it lacks rigor. In a production environment, simply checking the function name is insufficient. What if `sales_policy` accepts two arguments instead of one? The code would crash at runtime with a `TypeError`.

To prevent this, we should combine module introspection with signature validation. We can use `inspect.signature` to verify that the discovered strategies match the expected Protocol.

```python
def validate_strategy_signature(func: Callable) -> bool:
    """
    Returns True if func accepts exactly 1 argument.
    """
    sig = inspect.signature(func)
    # Check parameter count
    if len(sig.parameters) != 1:
        return False
        
    # Optional: Check type hints if enforced
    # param = list(sig.parameters.values())[0]
    # return param.annotation is Employee
    
    return True

# Inside _load_strategies:
for name, func in functions:
    if name.endswith('_policy'):
        if validate_strategy_signature(func):
            # register...
            pass
        else:
            print(f"WARNING: Skipped {name} due to invalid signature.")
```

---

### Performance Considerations

Introspection is a relatively expensive operation. Accessing `globals()`, filtering lists, and inspecting signatures involves significant CPU cycles compared to a direct dictionary lookup.

*   **Naive Approach:** Introspecting every time `calculate_bonus` is called. 
    *   *Time Complexity:* $O(N)$ where $N$ is the number of items in the module. This is catastrophic for performance in tight loops.
*   **Cached Approach (Best Practice):** Introspect once during the initialization (`__init__`) of the generic context class. Store the results in a hash map (dictionary). 
    *   *Time Complexity:* $O(N)$ setup, but $O(1)$ lookup for every subsequent call.

This technique is widely used in Python frameworks. For example, `pytest` uses introspection to collect tests, and Django uses it to discover system checks and signals.

---

### Conclusion

By treating modules as objects and functions as first-class citizens, Python allows us to dismantle the rigid boilerplate often associated with the Strategy and Command design patterns. The `inspect` module grants us the power to build architectures that are “closed for modification but open for extension” in the truest sense.

However, with great power comes great responsibility. Dynamic dispatch can make code harder to debug because the “Go to Definition” feature in IDEs may not work for dynamically resolved functions. Always ensure your introspection logic is heavily documented, typed, and validates signatures at startup to catch errors early.
