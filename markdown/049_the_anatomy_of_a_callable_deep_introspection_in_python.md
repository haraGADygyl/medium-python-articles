# The Anatomy of a Callable: Deep Introspection in Python
#### Unlocking the hidden metadata inside Python callables to build smarter, self-aware applications

**By Tihomir Manushev**  
*Dec 4, 2025 · 8 min read*

---

In compiled languages like C++ or Java, a function is often conceptually reduced to a memory address — a pointer to a block of machine code that the CPU jumps to when invoked. The metadata describing that function (its name, arguments, and return types) is largely discarded once the compiler finishes its job.

Python is different. In Python, functions are living, breathing objects. They are first-class citizens that carry their own passports, luggage, and biological history with them at runtime.

This capability is known as **Introspection**: the ability of the code to examine, inspect, and reason about itself.

If you have ever wondered how `pytest` knows which fixtures to inject into your test functions, or how FastAPI automatically converts HTTP JSON bodies into native Python objects based on your type hints, the answer is introspection. These frameworks don’t just call your code; they read your function’s mind before deciding how to execute it.

In this article, we will peel back the skin of a Python function object. We will explore the hidden attributes that power the language’s flexibility, examine the `inspect` module, and learn how to build tools that are aware of the code they are wrapping.

---

### The Function Object: More Than Just Code

Let’s start by creating a modern Python function. We will use type hints, a docstring, and a default value. This isn’t just a subroutine; it is an instance of the `function` class.

```python
def brew_potion(ingredient: str, potency: int = 10) -> str:
    """
    Combines ingredients to create a magical effect.
    
    Returns the name of the resulting potion.
    """
    return f"Elixir of {ingredient} (Level {potency})"
```

Because `brew_potion` is an object, we can interact with it without calling it. We can ask for its documentation or its name:

```python
print(type(brew_potion))      # <class 'function'>
print(brew_potion.__name__)   # 'brew_potion'
print(brew_potion.__doc__)    # The docstring above
```

However, the real magic lies in how Python stores the function’s signature and state.

---

### The __dict__ Attribute

Like most custom objects in Python, functions have a `__dict__` attribute. This means you can attach arbitrary data to a function at runtime. While not commonly used in daily business logic, frameworks often use this to “tag” functions with metadata (like routing information in a web framework) without using a full decorator.

```python
brew_potion.is_dangerous = True
print(brew_potion.__dict__)
```

---

### The Ghost in the Machine: __defaults__ and __kwdefaults__

One of the most misunderstood aspects of Python is how it handles default arguments. You may have heard the advice: “Never use a mutable object as a default argument.” Introspection explains exactly why.

When Python executes a `def` statement, it compiles the function body and evaluates the default argument values once, at that exact moment. It then stores these values in a tuple attribute called `__defaults__` (for positional arguments) or a dictionary called `__kwdefaults__` (for keyword-only arguments).

Let’s look at a broken function to see this mechanism in action.

```python
def add_inventory(item, backpack=[]):
    backpack.append(item)
    return backpack

# Let's inspect the function before calling it
print(f"Defaults before call: {add_inventory.__defaults__}")

# Call 1
add_inventory("Sword")
# Call 2
add_inventory("Shield")

# Inspect again
print(f"Defaults after calls: {add_inventory.__defaults__}")
```

Because the list `[]` was created at definition time and stored in `add_inventory.__defaults__`, every call to the function that doesn’t provide a backpack reuses that exact same list object. We aren’t just looking at a bug; we are looking at the function’s internal state.

#### The Fix

To avoid this, we use `None` as a sentinel.

```python
def add_inventory_safe(item, backpack=None):
    if backpack is None:
        backpack = []
    backpack.append(item)
    return backpack
```

Here, `add_inventory_safe.__defaults__` contains `(None,)`. `None` is immutable, so the state persists safely.

---

### The __code__ Object: The Blueprint

If you want to go deeper, you can look at the `__code__` attribute. This contains the compiled bytecode and low-level details used by the CPython interpreter.

One useful attribute here is `co_varnames`. This tuple contains the names of all local variables (including arguments).

```python
def brew_potion(ingredient: str, potency: int = 10) -> str:
    """
    Combines ingredients to create a magical effect.

    Returns the name of the resulting potion.
    """
    return f"Elixir of {ingredient} (Level {potency})"


print(brew_potion.__code__.co_varnames)
```

If we defined a local variable inside the function, it would appear here too. This is how static analysis tools (linters) often figure out if a variable is unused or shadowed without running the code.

---

### The Modern Way: The inspect Module

Directly accessing dunder attributes like `__defaults__` or `__code__` is brittle. You have to manually align the default values tuple with the argument names tuple, handle keyword-only arguments, and account for `*args` and `**kwargs`. It is a recipe for off-by-one errors.

Since Python 3.3, the standard library has provided the `inspect` module, specifically `inspect.signature`. This offers a high-level, object-oriented interface to introspection.

Let’s examine a complex function signature:

```python
import inspect

def cast_spell(spell_name: str, /, power: int = 5, *, target: str = "Self"):
    pass

sig = inspect.signature(cast_spell)

print(str(sig)) 

for name, param in sig.parameters.items():
    print(f"{name}: {param.kind} | Default: {param.default}")
```

---

### The Power of bind

The most powerful method in `inspect.signature` is `.bind()`. It takes a set of arguments (just like you would pass to the function) and maps them to the function’s parameters, handling all the logic of positional vs. keyword matching and default values.

This is essentially the logic the Python interpreter runs when you call a function, exposed for you to use.

```python
# Imagine we have raw input, perhaps from a CLI or API
args = ("Fireball",)
kwargs = {"target": "Goblin"}

# Bind the arguments to the signature
bound = sig.bind(*args, **kwargs)
bound.apply_defaults()  # Fills in 'power' with 5

print(bound.arguments)
```

If the arguments were invalid (e.g., missing a required positional argument), `sig.bind()` would raise a `TypeError` immediately, allowing you to catch errors before the function is actually entered.

---

### Building a Type Enforcer

Let’s put this alchemy to work. We will build a decorator called `@enforce_types`. It will inspect the function it wraps, read the type hints (`__annotations__`), and validate the incoming arguments at runtime.

This uses `inspect.signature` to map incoming values to argument names, ensuring we check the right variable against the right type hint.

```python
import inspect
import functools

def enforce_types(func):
    # 1. Get the signature of the target function
    sig = inspect.signature(func)
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 2. Bind the incoming arguments to the parameters
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults() # Ensure we check defaults too!
        
        # 3. Iterate over the bound arguments
        for name, value in bound.arguments.items():
            param = sig.parameters[name]
            
            # 4. Check if there is a specific annotation
            if param.annotation is not inspect.Parameter.empty:
                expected_type = param.annotation
                
                # Simple check (doesn't handle Generics like List[int])
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"Argument '{name}' expected {expected_type.__name__}, "
                        f"got {type(value).__name__}."
                    )
        
        # 5. Execute the actual function
        return func(*args, **kwargs)
    
    return wrapper

# --- Usage ---

@enforce_types
def calculate_xp(level: int, modifier: float = 1.0) -> float:
    return (level * 100) * modifier

# Valid call
print(f"XP: {calculate_xp(10, modifier=1.5)}") 

# Invalid call - will raise TypeError before function runs
try:
    calculate_xp(10, modifier="high") 
except TypeError as e:
    print(f"Blocked: {e}")
```

---

**Explanation of the Mechanics**

*   `inspect.signature(func)`: We grab the blueprint of the `calculate_xp` function.
*   `bound = sig.bind(…)`: We map `10` to `level` and `"high"` to `modifier`.
*   `bound.apply_defaults()`: If we didn’t pass a modifier, this ensures `1.0` is present in `bound.arguments` so we can validate the default value as well.
*   `param.annotation`: We retrieve the type hint (`int` or `float`) stored in the function’s metadata.
*   `isinstance`: We perform the check. If it fails, the wrapper crashes deliberately, protecting the inner function from bad data.

---

### Best Practices and Performance

Introspection is a superpower, but like all powerful magic, it comes with a cost.

**1. Performance Overhead**

Accessing `inspect.signature` and creating `BoundArguments` objects is significantly slower than a standard function call. While negligible for configuration logic or unit tests, you should avoid heavy introspection inside tight loops or high-frequency data processing pipelines.

*   **Do:** Use introspection for configuration, dependency injection frameworks, CLI parsing, or debugging tools.
*   **Don’t:** Use `inspect` inside a function called 1,000 times per second to check types.

**2. Preserving Metadata with functools.wraps**

When implementing decorators (like our `@enforce_types`), you are replacing the original function with a new function (the wrapper). By default, `wrapper` has a different name and an empty docstring. This breaks introspection for anyone else using your code!

Always decorate your wrappers with `@functools.wraps(func)`. It copies `__name__`, `__doc__`, `__module__`, and `__annotations__` from the original function to the wrapper, maintaining the illusion that the function is untouched.

**3. Accessing Annotations Correctly**

In Python 3.10+, accessing `func.__annotations__` directly can sometimes return stringified types (e.g., “List[int]” instead of the actual class) if `from __future__ import annotations` is used.

The robust best practice is to use `inspect.signature` (which handles most cases) or `typing.get_type_hints(func)`, which resolves forward references and evaluates stringified types for you.

---

### Conclusion

In many languages, code is static — a script to be followed. In Python, code is data. A function knows its name, it knows its arguments, and through type hints, it knows what it expects to receive.

Understanding introspection allows you to move from writing “scripts” to writing “systems.” It is the key to creating DRY (Don’t Repeat Yourself) code, where a single function definition can drive a CLI interface, an API schema, and runtime validation simultaneously.

Next time you write a function, remember: you aren’t just defining a behavior; you are creating an object rich with metadata, waiting to be read.