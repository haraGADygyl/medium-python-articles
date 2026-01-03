# Implicit vs. Explicit: The Hidden Dangers of globals() in Python Design Patterns
#### How to implement the Strategy and Command patterns using robust, type-safe registration decorators in Python 3.10

**By Tihomir Manushev**  
*Jan 3, 2026 · 7 min read*

---

Python is famous for its dynamic nature. Its malleability allows us to inspect memory, modify classes at runtime, and iterate over symbol tables with ease. For a senior engineer, this power is intoxicating. It tempts us to write “clever” code — code that auto-discovers functionality without explicit configuration.

One of the most common manifestations of this urge is found when implementing the Strategy Pattern. When we have a family of interchangeable algorithms (strategies), we often want a way to select one dynamically. The “lazy” Pythonic approach is to define a series of functions following a naming convention (e.g., `strategy_a`, `strategy_b`) and then iterate over the `globals()` dictionary to find them.

While this technique is often demonstrated in tutorials to show off Python’s introspection capabilities, it is a dangerous anti-pattern in production systems. It trades explicitness for brevity and robustness for “magic.”

In this article, we will explore why relying on implicit discovery via `globals()` creates fragile architectures, and how to refactor it into a robust, type-safe Registry Pattern using Python 3.10+ features.

---

### The Scenario: An Image Processing Pipeline

Imagine we are building a serverless image processing pipeline. We receive a raw image buffer and a configuration string indicating which filter to apply (e.g., “blur”, “threshold”, “invert”).

We want to implement these filters as stateless functions. This is a classic functional implementation of the Strategy Pattern.

---

### The Data Model

First, let’s define our domain objects using modern Python dataclasses and strict type aliases.

```python
from dataclasses import dataclass
from typing import TypeAlias, Callable

# Represents a 2D matrix of pixel data
PixelGrid: TypeAlias = list[list[int]]

@dataclass(frozen=True)
class ImageBuffer:
    width: int
    height: int
    data: PixelGrid
    metadata: dict[str, str]

# A Filter is a callable taking an ImageBuffer and returning a new one
FilterStrategy: TypeAlias = Callable[[ImageBuffer], ImageBuffer]
```

---

### The Anti-Pattern: Discovery via globals()

The naive requirement is: “I want to add a new filter just by writing a function named `apply_<filter_name>`, and the system should automatically pick it up.”

Here is how that is typically implemented using the global namespace:

```python
# filters.py
import copy

# --- The Strategies ---

def apply_threshold(image: ImageBuffer) -> ImageBuffer:
    """Converts image to black and white based on luminance."""
    # Simulation of processing...
    print(f"Applying THRESHOLD to {image.width}x{image.height} image")
    return image # In reality, we'd return modified data

def apply_invert(image: ImageBuffer) -> ImageBuffer:
    """Inverts pixel values."""
    print("Applying INVERT filter")
    return image

def apply_blur(image: ImageBuffer) -> ImageBuffer:
    """Gaussian blur approximation."""
    print("Applying BLUR filter")
    return image

# --- The Implicit Discovery Mechanism ---

def get_filter_by_name(name: str) -> FilterStrategy | None:
    """
    Scans the global namespace for a function named 'apply_<name>'.
    """
    target_func_name = f"apply_{name}"
    
    # DANGER: Inspecting the global symbol table
    current_namespace = globals()
    
    if target_func_name in current_namespace:
        return current_namespace[target_func_name]
    
    return None

# --- Usage ---
def main():
    img = ImageBuffer(1920, 1080, [], {})
    
    # Implicitly finding the function
    processor = get_filter_by_name("threshold")
    
    if processor:
        processor(img)
    else:
        print("Filter not found.")

if __name__ == "__main__":
    main()
```

At first glance, this looks elegant. You don’t have to maintain a list of available filters. You just write `def apply_x…` and it works. However, in a large-scale codebase, this approach creates technical debt for several reasons.

#### 1. Namespace Pollution and Shadowing

`globals()` returns the dictionary representing the current module’s symbol table. This includes not just the functions you defined, but also everything you imported.

If you import a function named `apply_compression` from a third-party library to use it as a helper, your discovery logic will accidentally pick it up as a valid strategy. You have lost control over your interface. You are now exposing internal dependencies as public APIs.

#### 2. Refactoring Fragility

Modern IDEs (VS Code, PyCharm) are excellent at refactoring. If you right-click `apply_threshold` and select “Rename” to `apply_binarization`, the IDE will update all static references.

However, the IDE cannot see the string construction `f”apply_{name}”`. Your runtime logic depends on a string literal matching a variable name. Renaming the function will break the `get_filter_by_name` logic, and static analysis tools will not catch it. You will only find out when the application crashes in production.

#### 3. Dead Code Detection

Static analysis tools like `vulture` or generic linters check for unused functions. Since `apply_invert` is never explicitly called (it’s only accessed via a string key in a dictionary), linters may flag it as dead code. To silence them, you have to add “noqa” comments, which adds noise to your clean code.

#### 4. The “Magic” Cost

New developers joining the team will struggle to understand how the system works. They will search for usages of `apply_blur` and find zero results. Implicit discovery breaks the ability to “Go to Definition” or “Find Usages,” which increases cognitive load.---

---

### The Solution: Explicit Registration with Decorators

The Pythonic way to solve this — preserving the convenience of “add function to enable feature” while maintaining safety — is the Registry Pattern implemented via decorators.

This approach adheres to the Zen of Python: *Explicit is better than implicit.*

#### Refactoring to a Registry

We will create a registry mechanism. This is a central dictionary that maps a string key (the filter name) to the callable strategy. We will populate this registry at import time using a decorator.

Here is the production-grade implementation:

```python
# better_filters.py
from typing import Callable
from dataclasses import dataclass

# ... (ImageBuffer and TypeAliases as defined previously) ...

# 1. The Explicit Registry
# This holds our mapping of 'name' -> 'function'
FILTER_REGISTRY: dict[str, FilterStrategy] = {}

class RegistrationError(Exception):
    """Raised when two filters try to register with the same name."""

# 2. The Decorator
def register_filter(name: str | None = None) -> Callable[[FilterStrategy], FilterStrategy]:
    """
    A decorator to register a function as a valid image filter.
    
    Args:
        name: Optional custom name. If None, uses the function's __name__.
    """
    def decorator(func: FilterStrategy) -> FilterStrategy:
        # Determine the key to use in the registry
        key = name if name else func.__name__
        
        if key in FILTER_REGISTRY:
            raise RegistrationError(f"Filter '{key}' is already registered.")
        
        FILTER_REGISTRY[key] = func
        
        # Return the function unchanged so it can still be called normally
        return func
    return decorator

# --- The Strategies ---

@register_filter(name="threshold")
def apply_threshold_v2(image: ImageBuffer) -> ImageBuffer:
    """Converts image to black and white."""
    print(f"[v2] Applying THRESHOLD")
    return image

@register_filter(name="invert")
def apply_invert_v2(image: ImageBuffer) -> ImageBuffer:
    """Inverts colors."""
    print(f"[v2] Applying INVERT")
    return image

@register_filter() # implicitly uses "apply_blur_v2" as key
def apply_blur_v2(image: ImageBuffer) -> ImageBuffer:
    """Gaussian blur."""
    print(f"[v2] Applying BLUR")
    return image

# --- The Retrieval Mechanism ---

def get_strategy(name: str) -> FilterStrategy:
    """
    O(1) lookup in a dedicated registry.
    """
    try:
        return FILTER_REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown filter: {name}. Available: {list(FILTER_REGISTRY.keys())}")

# --- Usage ---

def main():
    img = ImageBuffer(1920, 1080, [], {})
    
    # 1. Look up by the explicit string name provided in the decorator
    try:
        processor = get_strategy("threshold")
        processor(img)
    except ValueError as e:
        print(e)

    # 2. Iterate over all available plugins easily
    print("\n--- System Capabilities ---")
    for name, func in FILTER_REGISTRY.items():
        print(f"Filter: {name} -> Doc: {func.__doc__}")

if __name__ == "__main__":
    main()
```

#### 1. Decoupling Definition from Identification

In the `globals()` approach, the function name was the API key. In the decorator approach, the function name (`apply_threshold_v2`) is for the developer, while the argument `name="threshold"` is for the API configuration. This allows you to rename the Python function (e.g., to `_legacy_threshold_impl`) without breaking the external configuration string “threshold”.

#### 2. Import-Time Validation

The `@register_filter` decorator runs when the Python interpreter loads the module. If you accidentally copy-paste a function and forget to change the registration name, our `RegistrationError` logic triggers immediately at startup (fail-fast). With `globals()`, duplicate definitions might silently overwrite each other depending on the order of execution.

#### 3. Clean Namespaces

The `FILTER_REGISTRY` contains only the functions explicitly marked as filters. It will never accidentally contain an imported utility function, a variable, or a class. It is a clean, trusted source of truth.

#### 4. Type Safety and Introspection

Because `FILTER_REGISTRY` is typed as `dict[str, FilterStrategy]`, tools like Mypy can infer that anything coming out of this dictionary is a `Callable` taking an `ImageBuffer`.

Furthermore, creating a help menu or a CLI listing available commands becomes trivial. You simply iterate over `FILTER_REGISTRY.keys()`. In the `globals()` version, you would have to filter keys by string prefix, which is messy and error-prone.

---

### Architectural Note: The “Import” Side Effect

There is one caveat to the Registry Pattern: The module containing the decorated functions must be imported for the registration to happen.

If your filters are split across multiple files (e.g., `filters/blur.py`, `filters/color.py`), simply importing the registry in `main.py` is not enough. You must ensure the sub-modules are loaded.

A common pattern to handle this in `__init__.py`:

```python
# filters/__init__.py
from .registry import FILTER_REGISTRY
# Import modules solely for their side-effects (registration)
from . import blur, color, edge_detection 

__all__ = ["FILTER_REGISTRY"]
```

This ensures that as soon as you import `filters`, the sub-modules execute, the decorators run, and the registry populates.

---

### Conclusion

Python gives us the tools to shoot ourselves in the foot with amazing efficiency. The `globals()` dictionary is a powerful introspection tool, but it belongs in debugging sessions and REPLs, not in the core logic of a production system.

By relying on implicit discovery via `globals()`, you build a system that is sensitive to renaming, hard to analyze statically, and prone to namespace pollution. By shifting to Explicit Discovery using registration decorators, you effectively invert the control: the individual strategies announce themselves to the system. This leads to code that is robust, self-documenting, and easier to maintain.

When designing patterns in Python, always remember: **Magic is fun to write, but explicit is fun to maintain.**
