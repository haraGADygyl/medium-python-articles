# Python Class-Based Decorators: When Functions Are Not Enough
#### Moving beyond closures to build extensible, stateful, and object-oriented wrapper components in Python

**By Tihomir Manushev**  
*Dec 22, 2025 · 7 min read*

---

In the Python ecosystem, the function decorator is a staple of intermediate programming. We learn to wrap a function inside another function, perhaps adding a third layer if we need to pass arguments to the decorator itself. For simpler tasks, such as logging a function call or timing its execution, this functional approach is elegant and idiomatic.

However, as a Python engineer designing production-grade systems, you will inevitably hit a wall. Functional decorators rely heavily on closures to retain state. When you need a decorator that requires complex configuration, maintains mutable state across multiple calls, or crucially needs to be extensible via inheritance, the functional “pyramid of doom” becomes a liability.

Managing state with nonlocal variables is clever, but it is often opaque and difficult to debug. When your decorator logic begins to exceed twenty lines, or when you find yourself nesting three functions deep just to accept a configuration parameter, it is time to abandon the closure and embrace the Class.

In this article, we will explore how to refactor complex decorators into clean, maintainable classes. We will leverage Python’s object model to create decorators that are not just wrappers, but fully architected components.

---

### The Anatomy of a Class-Based Decorator

To understand class-based decorators, we must revisit what a decorator actually is. At its core, a decorator is simply a callable that takes a function as an argument and returns a replacement callable.

While we typically think of functions as callables, Python objects are also callables if they implement the `__call__` dunder method. This means a class instance can act exactly like a function.

This architecture offers two distinct advantages:

1.  **Encapsulation:** Configuration and state are stored in `self` attributes, not hidden in closure cells.
2.  **Lifecycle Separation:** We can clearly separate the initialization of the decorator (import time) from the execution of the wrapper (runtime).

---

### The Blueprint

There are two primary ways to implement a class-based decorator, depending on whether the decorator accepts arguments. We will focus on the more robust pattern: the **Parameterized Class Decorator**.

In this pattern:

*   `__init__`: Accepts the decorator’s configuration arguments (e.g., `retries=3`).
*   `__call__`: Accepts the function being decorated (`func`) and returns the actual wrapper.

Let’s look at a concrete implementation.

---

### The ResilientTask Decorator

Imagine we are building a microservice that communicates with a flaky third-party API. We need a retry mechanism. A simple functional decorator could handle this, but we have requirements: we need configurable retry counts, a configurable backoff strategy, and we want to track statistics on how many times the retries triggered.

Doing this with closures would require a tangle of nonlocal counters and nested scopes. Let’s do it with a class.

#### The Implementation

We will use modern Python 3.10+ syntax, including `ParamSpec` for precise type hinting of the decorated function.

```python
import time
import functools
import logging
from typing import Callable, TypeVar, ParamSpec

# ParamSpec captures the parameter types of the decorated function
P = ParamSpec("P")
# TypeVar captures the return type
R = TypeVar("R")

class ResilientTask:
    """
    A class-based decorator that retries a function upon failure.
    Maintains state regarding failure history.
    """

    def __init__(self, max_retries: int = 3, delay: float = 1.0, raise_on_fail: bool = True):
        self.max_retries = max_retries
        self.delay = delay
        self.raise_on_fail = raise_on_fail
        
        # State tracking: accessible for inspection
        self.total_failures = 0
        self.total_recoveries = 0

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        """
        Receives the function to be decorated and returns the wrapper.
        """
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            attempts = 0
            while attempts < self.max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    self.total_failures += 1
                    logging.warning(
                        f"Attempt {attempts}/{self.max_retries} failed for {func.__name__}: {e}"
                    )
                    
                    if attempts >= self.max_retries:
                        logging.error(f"Function {func.__name__} failed after {attempts} retries.")
                        if self.raise_on_fail:
                            raise e
                        return None
                    
                    # Wait before retrying
                    time.sleep(self.delay)
            
            self.total_recoveries += 1
            return None

        return wrapper

# Usage
@ResilientTask(max_retries=3, delay=0.5)
def connect_to_database(connection_string: str) -> bool:
    print(f"Connecting to {connection_string}...")
    # Simulate a random crash for demonstration
    import random
    if random.choice([True, False]):
        raise ConnectionError("Database went away!")
    return True

connect_to_database("localhost:5432")
```

1.  **`__init__` as Configuration:**
    When Python parses `@ResilientTask(max_retries=3, …)`, it instantiates the class. The `__init__` method runs immediately at import time. This is where we validate arguments and set up our strategy. Notice we also initialize `self.total_failures`. In a functional decorator, exposing this metric to the outside world would require awkward function attributes or a global registry. Here, it is just a public attribute on the decorator instance.

2.  **`__call__` as the Factory:**
    The `__call__` method receives the `func`. Crucially, it defines the wrapper closure. While we are still using a closure (the wrapper function), the context of that closure is the class instance (`self`). This means the wrapper has access to `self.delay`, `self.max_retries`, and can mutate `self.total_failures`.

3.  **Type Safety:**
    Using `ParamSpec` (`P`) and `TypeVar` (`R`) ensures that tools like MyPy and VS Code understand that the decorated function preserves its original signature. If `connect_to_database` takes a string and returns a bool, the decorated version is known to do the same.

---

### The Power of Inheritance: Extensible Decorators

The strongest argument for class-based decorators is inheritance. Imagine we now need a specialized version of our retry logic. Instead of a fixed delay, we want an exponential backoff (waiting 1s, then 2s, then 4s).

If we had written `ResilientTask` as a nested function, we would have to copy-paste the entire logic or introduce complex callback arguments to modify the wait behavior. With a class, we simply subclass and override.

```python
class ExponentialBackoffTask(ResilientTask):
    """
    Inherits from ResilientTask but implements exponential backoff logic.
    """
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, factor: int = 2):
        # We can extend the configuration
        super().__init__(max_retries, base_delay)
        self.factor = factor

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        # We need to inject custom logic. 
        # In a purely OOP design, we might have separated the 'wait' logic 
        # into a method in the parent class to make this cleaner.
        # But even overriding __call__ allows us to reuse __init__ and state.
        
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            attempts = 0
            current_delay = self.delay
            
            while attempts < self.max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    time.sleep(current_delay)
                    current_delay *= self.factor # Exponential increase
                    
                    if attempts >= self.max_retries:
                        raise e
            return None
            
        return wrapper
```

This adheres to the Open/Closed Principle: our code is open for extension but closed for modification. We extended the behavior without touching the original, tested `ResilientTask` code.

---

### The “Method Binding”

There is a subtle trap in class-based decorators that senior engineers must be aware of: Descriptor Protocol interactions.

In the examples above, our `__call__` method returns a wrapper function. This is the safe, recommended approach.

However, a common temptation is to make the class instance itself the wrapper, avoiding the inner function entirely. It looks like this (conceptually):

```python
# WARNING: This pattern has a flaw when decorating class methods
class FlawedDecorator:
    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        print("Decorating...")
        return self.func(*args, **kwargs)
```

If you apply `@FlawedDecorator` to a standalone function, it works perfectly. But if you apply it to a method inside a class:

```python
class UserService:
    @FlawedDecorator
    def delete_user(self, user_id):
        pass
```

When you call `UserService().delete_user(1)`, it will likely crash. Why?

When `delete_user` is accessed, Python looks it up. Since `delete_user` is now an instance of `FlawedDecorator`, Python does not treat it as a bound method. It does not automatically pass the `UserService` instance as the first argument (`self`). The `*args` in `__call__` will receive `(1,)` instead of `(instance_of_user_service, 1)`.

---

### The Solution

The solution used in our `ResilientTask` example avoids this problem entirely. By having `__call__` return a standard Python function (the wrapper), Python handles the method binding correctly. The returned wrapper is a simple function, and when it is placed on a class, Python knows how to bind it to `self`.

If you absolutely must implement a decorator where the instance itself handles the execution (perhaps to maintain state specific to that specific execution context), you must implement the `__get__` method to satisfy the Descriptor Protocol, manually creating a bound method. For 99% of use cases, simply returning a wrapper function from `__call__`, as we did in `ResilientTask`, is the correct, “production-safe” architectural choice.

---

### Performance Implications

One might ask: “Is creating a class heavier than a closure?”

Strictly speaking, yes. Instantiating a class object involves more CPython machinery than defining a function. However, this cost is paid primarily at import time (when the `@ResilientTask` line is executed).

At runtime (when the decorated function is called), the performance overhead is nearly identical to a functional decorator. The wrapper returned by our class is just a function closing over `self`. Accessing `self.max_retries` involves an attribute lookup, which is marginally slower than reading a `LOAD_DEREF` from a closure cell, but in the context of I/O bound operations (like database calls or APIs), this nanosecond difference is statistically irrelevant.

---

### Conclusion

Functional decorators are excellent for simple, stateless logic. But when your requirements grow to include complex configuration, mutable status tracking, or inheritance, functional decorators degrade into unreadable, nested complexity.

Class-based decorators provide a structured, object-oriented alternative. They allow you to encapsulate configuration in `__init__`, manage state in `self`, and leverage inheritance to create families of related decorators. By treating decorators as software components rather than just syntactic sugar, you ensure your codebase remains robust, readable, and ready for scale.
