# Import Time vs. Runtime: The Hidden Lifecycle of Decorators
#### Mastering the mechanics of Python’s execution model to build robust, decoupled architectures

**By Tihomir Manushev**  
*December 15, 2025 · 7 min read*

---

One of the most common misconceptions among intermediate Python developers — and even some seniors — is the exact moment a decorator executes. We often conceptualize decorators as “wrappers” that sit around our functions, waiting to spring into action when the function is called.

While this is true for the inner wrapper function, it is false for the decorator itself.

To master Python metaprogramming and build robust frameworks (like Flask, Django, or FastAPI), you must distinguish between two distinct phases in the Python lifecycle: **Import Time** and **Runtime**. Failing to understand this distinction is the root cause of many “circular import” errors, unintended side effects during testing, and application startup bottlenecks.

In this article, we will dissect the mechanics of the `@` syntax, prove exactly when code executes, and demonstrate how to leverage this behavior to build powerful, self-registering plugin architectures.

---

### The Mechanics of import

To understand decorators, we must first respect the `import` statement. In compiled languages like C++ or Java, the compiler reads declarations and optimizes code before the program ever runs. Python is different. Python is an interpreted language, and the `import` statement is actually an executable command.

When you write `import my_module`, the Python interpreter:

1.  Locates the file.
2.  Compiles it to bytecode.
3.  **Executes the module’s code from top to bottom.**

This means that any top-level code in a module — variable assignments, class definitions, and function decorators — runs immediately when the module is imported, not when the functions are called.

---

### The Syntactic Sugar of @

The `@decorator` syntax is merely syntactic sugar. To see why this matters, look at the standard definition:

```python
@my_decorator
def target_function():
    pass
```

The Python interpreter translates the code above into the following instruction sequence:

```python
def target_function():
    pass

target_function = my_decorator(target_function)
```

Notice the assignment. `my_decorator` is called immediately after `target_function` is defined. The result of that call replaces the original name `target_function` in the module’s namespace.

This happens while the module is being read (**Import Time**). If your decorator contains print statements, database connections, or network requests, they will fire the moment the process starts, long before any user interacts with your application.

---

### Proving the Lifecycle: The Telemetry Registry

Let’s visualize this behavior. We will build a simple “Telemetry System” for a hypothetical spacecraft. We want to register various sensor functions so a central computer can check them all at once.

We will use a registration decorator. This is a classic pattern found in web frameworks (routing) and event systems.

```python
from typing import Callable

# 1. Global registry to hold our sensor functions
SENSOR_REGISTRY: list[Callable] = []

def register_sensor(func: Callable) -> Callable:
    """
    A decorator that registers a function into the SENSOR_REGISTRY.
    This runs at IMPORT TIME.
    """
    print(f"[IMPORT TIME] Registering sensor: {func.__name__}")
    SENSOR_REGISTRY.append(func)
    # We return the function unchanged (or we could return a wrapper)
    return func

print("[MODULE START] spacecraft.py is being loaded...")

@register_sensor
def check_oxygen_levels():
    print("[RUNTIME] Checking O2 levels... Nominal.")

@register_sensor
def check_thruster_pressure():
    print("[RUNTIME] Checking Thrusters... 98% PSI.")

def manual_override():
    print("[RUNTIME] Manual override engaged.")

print("[MODULE END] spacecraft.py loading complete.")

def run_diagnostics():
    """Iterates over registered sensors and executes them."""
    print(f"\n[RUNTIME] System Check Initiated. Sensors found: {len(SENSOR_REGISTRY)}")
    for sensor in SENSOR_REGISTRY:
        sensor()

if __name__ == "__main__":
    # This block only runs if we execute the script directly,
    # imitating the 'Runtime' phase of an application.
    run_diagnostics()
```

When you execute this code, the output proves the timeline:

1.  **Module Start:** The interpreter reads the file. It initializes `SENSOR_REGISTRY`.
2.  **Decoration (The “Hidden” Execution):**
    *   The interpreter defines `check_oxygen_levels`.
    *   It immediately invokes `register_sensor(check_oxygen_levels)`.
    *   The print statement `[IMPORT TIME]…` appears now. The function is added to the list.
    *   The interpreter moves to the next line.
3.  **Module End:** The interpreter finishes reading the file.
4.  **Runtime:** Only after the module is fully loaded does the `if __name__ == “__main__”:` block execute, calling `run_diagnostics`.

Notice that `manual_override` was defined but never decorated. Consequently, it never triggered the “Registering sensor” log, and it is not inside the `SENSOR_REGISTRY`.

---

### The “Decorator Pattern” vs. “Decorator Factory”

The confusion deepens when we add arguments to decorators. If we want to define how a sensor is registered (e.g., `@register(criticality=’HIGH’)`), we need a **Decorator Factory**.

This introduces three levels of scope:

1.  **The Factory:** Runs at import time (returns the decorator).
2.  **The Decorator:** Runs at import time (receives the function).
3.  **The Wrapper:** Runs at runtime (when the function is called).

Let’s refactor our system to handle sensor criticality using modern Python 3.10+ features.

```python
import time
from typing import Any, Callable
from functools import wraps

# A dictionary mapping criticality levels to lists of functions
SYSTEM_MONITORS: dict[str, list[Callable]] = {
    "CRITICAL": [],
    "WARNING": [],
    "INFO": []
}

def monitor(level: str = "INFO") -> Callable:
    """
    The Factory. Accepts arguments and returns the actual decorator.
    """
    print(f"1. [IMPORT TIME] Factory called with level='{level}'")
    
    def actual_decorator(func: Callable) -> Callable:
        """
        The Decorator. Receives the function definition.
        """
        print(f"2. [IMPORT TIME] Decorating {func.__name__}")
        
        # Register the function immediately
        SYSTEM_MONITORS[level].append(func)
        
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """
            The Wrapper. Replaces the original logic.
            """
            print(f"3. [RUNTIME] Executing wrapper logic for {func.__name__}")
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            duration = time.perf_counter() - start_time
            print(f"   -> Finished in {duration:.4f}s")
            return result
            
        return wrapper

    return actual_decorator

print("--- STARTING IMPORT ---")

@monitor(level="CRITICAL")
def reactor_core_temp():
    print("   -> Core temperature is 4500K")

print("--- IMPORT COMPLETE ---")

if __name__ == "__main__":
    print("\n--- STARTING RUNTIME ---")
    # We access the registry to find the function, but it is now the WRAPPER
    critical_sensors = SYSTEM_MONITORS["CRITICAL"]
    for sensor in critical_sensors:
        sensor()
```

When you run this code, pay close attention to the numbering in the logs:

1.  **Factory (Step 1):** `monitor(level=”CRITICAL”)` is called. It returns `actual_decorator`.
2.  **Decorator (Step 2):** `actual_decorator` is called with `reactor_core_temp`. It adds the function to the dictionary and returns `wrapper`.
3.  **Runtime (Step 3):** Much later, we loop through the list and call `sensor()`. This executes `wrapper`.

---

### Best Practices: Designing for Import Time

Understanding this lifecycle dictates how we should architect professional Python applications.

**1. Avoid Side Effects at Import Time**

Your decorator code (the part that runs at import time) should be lightweight. It should primarily manipulate metadata or update registries.

*   **Bad:** Connecting to a database inside the decorator body. If you import this module in a unit test, it will try to connect to the DB, potentially failing the test suite.
*   **Good:** Registering the function string name or reference to a list, and connecting to the DB only when the function is actually invoked (Runtime).

**2. The Plugin Architecture**

The “Import Time” execution is a feature, not a bug. It allows for decoupled plugin discovery. Imagine a web application where you have a folder `plugins/`. You can write a script that iterates over that folder and imports every file.

```python
# main.py
import glob
import importlib

# This triggers the decorators in all plugin files!
for module_file in glob.glob("plugins/*.py"):
    importlib.import_module(module_file)

# Now, the registries are populated, even though we never 
# manually imported the specific plugin modules.
```

This is how Flask blueprints and Pytest fixtures work. They rely on the side effect of decorators running at import time to populate a central state.

**3. Handle func vs wrapper**

If your decorator registers the function (like our `SYSTEM_MONITORS` example), decide whether you are registering the original function or the wrapper. In the second example above, `SYSTEM_MONITORS` holds the original function because we appended `func` before defining `wrapper`. If we wanted the timing logic to run when iterating the registry, we should have appended `wrapper` (or `func` after reassignment). This is a common source of bugs where registered functions bypass the decorator’s runtime logic.

---

### Conclusion

The distinction between **Import Time** and **Runtime** is the dividing line between simple scripts and complex architecture. The Python decorator is the bridge between these two worlds.

At **Import Time**, decorators act as architects. They survey the code, update registries, modify metadata, and prepare the structure of the application. They allow modules to self-register and decouple components.

At **Runtime**, the wrappers created by those decorators act as guards. They manage execution, handle logging, enforce authentication, and manage caching.

By respecting the hidden lifecycle of the decorator, you move from simply writing functions to metaprogramming the Python language itself.
