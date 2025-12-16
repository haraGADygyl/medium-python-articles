# Architecting Parameterized Decorators in Python
#### Moving from nested closures to clean Class-Based Architectures in Python 3.10+

**By Tihomir Manushev**  
*December 16, 2025 · 7 min read*

---

To the uninitiated, Python decorators often feel like magic. They allow us to wave a wand over a function and transform its behavior — adding logging, caching, or authentication — without modifying a single line of the function’s internal logic.

Most intermediate Python developers are comfortable writing a standard decorator: a function that accepts a callable and returns a wrapper. However, the moment you need to pass arguments to that decorator — for example, `@retry(attempts=5)` rather than just `@retry` — the architecture shifts dramatically.

Suddenly, you are no longer writing a decorator; you are writing a decorator factory. You find yourself trapped in a “pyramid of doom,” defining functions within functions within functions, struggling to track which variable belongs to which scope.

In this article, we will move beyond the syntax sugar to understand the architectural mechanics of parameterized decorators. We will explore how to manage closures effectively using functional patterns and then refactor that logic into a clean, robust Object-Oriented approach suitable for production systems.

---

### The Mental Model: Decorators vs. Decorator Factories

To architect a parameterized decorator, you must first understand the fundamental difference in how Python evaluates the `@` syntax.

When you write a standard decorator:

```python
@simple_decorator
def my_func():
    pass
```

Python translates this effectively into:

```python
my_func = simple_decorator(my_func)
```

However, when you add parentheses to pass arguments:

```python
@param_decorator(x=1, y=2)
def my_func():
    pass
```

The order of operations changes. Python evaluates this as:

1.  Call `param_decorator(x=1, y=2)`.
2.  Take the return value of that call (which must be a callable).
3.  Call that returned callable with `my_func` as the argument.

Thus, it looks like:

```python
my_func = param_decorator(x=1, y=2)(my_func)
```

This means `param_decorator` is not the decorator. It is a factory function whose sole job is to capture the arguments (`x` and `y`) and manufacture the actual decorator that will eventually process `my_func`.

---

### Approach 1: The Functional Pyramid (Closures)

The traditional way to implement this is using three levels of nested functions. While this leverages Python’s powerful closure mechanisms, it can become difficult to read.

Let’s implement a production-grade `RetryPolicy` decorator. This decorator will accept a maximum number of retries and a delay factor. If the decorated function raises an exception, it will wait and try again.

We will use modern Python 3.10+ typing, specifically `ParamSpec` and `TypeVar`, to ensure our decorator preserves the type signature of the function it wraps (a common pain point in decorated code).

```python
import time
import functools
from typing import Callable, TypeVar, ParamSpec, Any

# P captures the parameters of the decorated function
P = ParamSpec("P")
# R captures the return type of the decorated function
R = TypeVar("R")

def retry_policy(max_retries: int = 3, delay_seconds: float = 1.0):
    """
    A decorator factory that creates a retry mechanism with a fixed delay.
    """
    
    # LEVEL 1: The Factory
    # This scope captures 'max_retries' and 'delay_seconds' as closures.
    
    def actual_decorator(func: Callable[P, R]) -> Callable[P, R]:
        
        # LEVEL 2: The Decorator
        # This scope captures 'func'.
        
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            
            # LEVEL 3: The Wrapper
            # This code runs at runtime when the function is called.
            
            last_exception: Exception | None = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    print(f"[Retry] Attempt {attempt}/{max_retries} failed for "
                          f"{func.__name__}. Retrying in {delay_seconds}s...")
                    time.sleep(delay_seconds)
            
            # If we exit the loop, we failed all attempts
            print(f"[Retry] All {max_retries} attempts failed.")
            if last_exception:
                raise last_exception
            raise RuntimeError("Unknown error during retry logic")

        return wrapper

    return actual_decorator
```

1.  **The Factory (`retry_policy`):** This runs immediately when the module is imported (provided the decoration happens at the top level). It validates the configuration (e.g., `max_retries`) and returns `actual_decorator`.
2.  **The Closure:** Crucially, `actual_decorator` has access to `max_retries` and `delay_seconds`. These are free variables. Python’s bytecode compiler creates “cells” to store these values so they persist even after `retry_policy` returns.
3.  **The Decorator (`actual_decorator`):** This receives the function to be wrapped. It defines the wrapper and applies `functools.wraps` (essential for preserving the original function’s `__name__` and `__doc__`).
4.  **The Wrapper (`wrapper`):** This is what actually executes at runtime. It has access to `func` (from Level 2), and `max_retries`/`delay_seconds` (from Level 1).

**Usage:**

```python
@retry_policy(max_retries=2, delay_seconds=0.5)
def unstable_network_call(endpoint: str) -> dict:
    import random
    if random.random() < 0.7:
        raise ConnectionError(f"Failed to connect to {endpoint}")
    return {"status": 200, "data": "Success"}

# When we call this, we are calling 'wrapper'
result = unstable_network_call("api.example.com")
print(result)
```

While effective, the nested nature of this code (variable lookup traversing two scopes up) can be cognitively demanding. As the logic grows complex, maintaining this pyramid becomes error-prone.

---

### Approach 2: The Class-Based Implementation

A cleaner, more extensible approach for parameterized decorators is to use a Class. This aligns better with the Single Responsibility Principle: the class handles the configuration state, and the `__call__` method handles the decoration logic.

In this pattern, the `__init__` method acts as the factory, and the `__call__` method acts as the decorator.

Let’s refactor our retry logic into a class.

```python
import functools
import time
from typing import Callable, ParamSpec, TypeVar

# P captures the parameters of the decorated function
P = ParamSpec("P")
# R captures the return type of the decorated function
R = TypeVar("R")


class RetryManager:
    """
    A class-based decorator for handling retry logic.
    Arguments passed to __init__ become the configuration.
    """

    def __init__(self, max_retries: int = 3, delay_seconds: float = 1.0):
        # Configuration is stored as instance attributes, 
        # avoiding the need for complex closure lookups.
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        # The __call__ method turns the instance into a callable,
        # allowing it to act as the actual decorator.

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception: Exception | None = None

            for attempt in range(1, self.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    print(f"[Class-Based Retry] Attempt {attempt}/{self.max_retries} "
                          f"failed. Waiting {self.delay_seconds}s...")
                    time.sleep(self.delay_seconds)

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry failed")

        return wrapper
```

*   **Explicit State:** Instead of relying on invisible “free variables” floating in closure cells, we access configuration via `self.max_retries`. This is standard Object-Oriented behavior and is often easier for IDEs and humans to parse.
*   **Extensibility:** Because it is a class, we can easily add helper methods. For example, we could add a method to dynamically calculate the backoff time (linear vs. exponential) without cluttering the wrapper function.
*   **Initialization Validation:** The `__init__` is the perfect place to raise `ValueError` if the user passes a negative retry count. In the functional version, this logic clutters the outer scope.

The syntax for usage remains identical to the functional version. This is the beauty of Python’s protocol-based design (duck typing) — as long as the object is callable, the `@` syntax accepts it.

```python
@RetryManager(max_retries=4, delay_seconds=0.2)
def fetch_database_record(record_id: int):
    print(f"Fetching record {record_id}...")
    raise ValueError("Database connection lost") 

# Execution
try:
    fetch_database_record(42)
except ValueError:
    print("Operation failed after retries.")
```

---

### Advanced Considerations: functools.wraps in Classes

There is a subtle trap when using class-based decorators. If you implement the `__call__` method as shown above, `functools.wraps` works perfectly because `wrapper` is a function defined inside a method.

However, some developers try to implement the wrapper logic directly in `__call__` to avoid defining an inner function. **Do not do this.**

If `__call__` executes the logic directly, the decorated function (`fetch_database_record`) becomes an instance of `RetryManager`, not a function. This breaks introspection, confuses testing frameworks (like pytest), and makes the object unbindable if used on class methods. Always have `__call__` return a distinct wrapper function.

---

### Best Practice: Making Arguments Optional

A mark of a polished API is a decorator that can be used with or without arguments.

*   `@retry` (uses defaults)
*   `@retry(attempts=5)` (uses custom values)

Achieving this requires introspection because usage changes the arguments passed to your factory.

*   `@retry`: The factory receives the function as the first argument.
*   `@retry()`: The factory receives nothing (or keywords).

Here is a robust pattern to handle both, utilizing `functools.partial`:

```python
def flexible_retry(func: Callable = None, *, retries: int = 3):
    if func is None:
        # We were called as @flexible_retry(retries=5)
        # We return a partial application of this very function,
        # effectively waiting for the 'func' argument.
        return functools.partial(flexible_retry, retries=retries)

    # We were called as @flexible_retry
    # or the partial has now received the function.
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Implementation details...
        print(f"Retrying {retries} times...")
        return func(*args, **kwargs)
        
    return wrapper
```

This pattern flattens the pyramid. By checking if `func` is `None`, we detect if we are in the “configuration” phase or the “decoration” phase.

---

### Conclusion

Parameterized decorators represent a significant jump in complexity from standard decorators, but they unlock the ability to write declarative, clean, and highly reusable code.

While functional closures are the “Pythonic” default, do not shy away from Class-Based decorators. When your decorator requires complex configuration, state validation, or sub-routines, the Class pattern offers superior readability and maintainability. It transforms the “magic” of closures into the explicit structure of attributes and methods.

Whichever approach you choose, remember that decorators are interface code. They should be well-typed, explicitly documented, and strictly preserve the metadata of the functions they wrap.
