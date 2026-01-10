# Python’s Privacy Illusion: Name Mangling and Conventions
#### Why __double_underscore isn’t what you think it is, and how to properly encapsulate state in Python applications

**By Tihomir Manushev**  
*Jan 10, 2026 · 7 min read*

---

If you have migrated to Python from a language like Java, C++, or C#, your first encounter with Python’s encapsulation philosophy can feel like a cold shower. You reach for the `private` keyword to lock down your internal state, only to find it missing. You look for `protected`, but it’s nowhere to be found.

Instead, you are introduced to underscores, vague community conventions, and a mechanism with the ominous name of “Name Mangling.”

Many developers misunderstand these tools. They assume the double underscore (`__var`) is the Python equivalent of private, a security feature designed to keep prying eyes away from sensitive data. This assumption is dangerous. Python’s approach to encapsulation is not based on enforced restrictions, but on namespace safety and the “Consenting Adults” philosophy.

In this deep dive, we will peel back the layers of the Python interpreter to understand how privacy actually works, why “private” variables are merely an illusion, and how to structure your classes for robustness rather than secrecy.

---

### The Gentleman’s Agreement: The Single Underscore

Before we tackle the mechanics of name mangling, we must address the most common tool in the Pythonista’s belt: the single leading underscore (e.g., `_internal_cache`).

To the Python interpreter, a variable named `_variable` is indistinguishable from `variable`. It triggers no special behavior, no memory optimization, and no access control. You can access it from outside the class, modify it, and delete it without the interpreter raising so much as a warning.

However, to a Python developer, that underscore screams: “This is an implementation detail. Touch this at your own risk.”

This is the essence of the “Consenting Adults” philosophy. Python assumes that if you are accessing an attribute marked as internal, you have a good reason — perhaps you are debugging, patching a library, or writing a serialization tool. The language refuses to stand in your way, but the underscore releases the library author from the responsibility of maintaining backward compatibility for that specific attribute.

```python
from typing import Any

class DatabaseConnector:
    def __init__(self, dsn: str):
        self.dsn = dsn
        # By convention, this is internal.
        # It holds raw socket state we don't want users messing with.
        self._socket: Any = None 
        self._connected: bool = False

    def connect(self) -> None:
        print(f"Connecting to {self.dsn}...")
        self._socket = "SimulatedRawSocket"
        self._connected = True

    def _internal_handshake(self) -> None:
        # A method intended only for internal use
        print("Performing handshake protocols...")

# Usage
db = DatabaseConnector("postgres://localhost:5432")
db.connect()

# The interpreter allows this without complaint:
print(f"Direct access: {db._socket}") 
db._internal_handshake()
```

While this code runs perfectly, IDEs and linters will often flag access to `_socket` as a warning. The protection is social and tooling-based, not structural.

---

### The Mechanics of Name Mangling

If the single underscore is a “Do Not Enter” sign, the double leading underscore (e.g., `__context`) is often mistaken for a lockbox.

When you name an attribute with at least two leading underscores and at most one trailing underscore, the Python interpreter performs Name Mangling. It drastically transforms the name of the attribute in the class’s `__dict__` storage to make it harder to access accidentally.

Crucially, this is not done for security. It is done to prevent namespace collisions in inheritance hierarchies. Let’s look at what happens under the hood when we use double underscores.

---

### The Accidental Overwrite

Imagine you are writing a library that provides a `BasePage` class for a web framework. You store some context in `self.context`. A user comes along, subclasses `BasePage` to create `ProfilePage`, and unknowingly creates their own `self.context`. Without name mangling, the subclass would overwrite the parent’s data, causing the parent methods to crash.

Name mangling solves this by prefixing the class name to the variable.

```python
class BasePlugin:
    def __init__(self) -> None:
        # Standard public attribute
        self.name: str = "Base"
        
        # Protected attribute (convention)
        self._status: str = "Initialized"
        
        # Private attribute (Name Mangled)
        self.__config: dict[str, str] = {"mode": "DEFAULT"}

    def get_config(self) -> dict[str, str]:
        # Internally, the class knows how to find this
        return self.__config

class AnalyticsPlugin(BasePlugin):
    def __init__(self) -> None:
        super().__init__()
        self.name = "Analytics"
        
        # We unknowingly define the same attribute names!
        
        # This overwrites the parent's _status
        self._status = "Recording"
        
        # Does this overwrite the parent's __config?
        # The user assumes this is their own private dictionary.
        self.__config = {"tracking_id": "UA-12345"}

# Inspections
plugin = AnalyticsPlugin()

print(f"1. Public Name: {plugin.name}")
print(f"2. Protected Status: {plugin._status}")

# Let's see what get_config returns. 
# If __config was overwritten, it would return the tracking ID.
print(f"3. Parent Config via method: {plugin.get_config()}")

# Let's inspect the actual dictionary storage
print("\n--- Internal Dictionary (__dict__) ---")

import pprint
pprint.pprint(plugin.__dict__)
```

When you run this code, you will see a fascinating result in the `__dict__`:

1.  **`_status` was clobbered:** Because it uses a single underscore, the subclass `AnalyticsPlugin` overwrote the variable used by `BasePlugin`. If `BasePlugin` relied on that string being “Initialized”, it is now broken.
2.  **`__config` co-exists:** This is the magic.
    *   In `BasePlugin`, the interpreter renamed `__config` to `_BasePlugin__config`.
    *   In `AnalyticsPlugin`, the interpreter renamed `__config` to `_AnalyticsPlugin__config`.

Both attributes exist simultaneously in the same instance memory. The methods defined in `BasePlugin` automatically look for `_BasePlugin__config`, while methods in `AnalyticsPlugin` look for `_AnalyticsPlugin__config`.

The “private” variable effectively becomes class-local. It ensures that a subclass cannot accidentally break the internal workings of a superclass by reusing a variable name.

---

### Piercing the Veil

This mechanism proves that Python offers safety, not security. A determined developer can easily access these variables. There is no memory protection or access violation error.

If you are debugging a library and you absolutely need to see the state of a “private” variable, you simply access the mangled name directly:

```python
# Accessing the 'private' attribute of the parent class from the outside
hidden_data = plugin._BasePlugin__config
print(f"Breaching privacy: {hidden_data}")
```

This is intentionally possible. Python favors introspectability. If you are serializing an object to JSON, you need access to everything. If you are writing a debugger, you need access to everything. If Python enforced strict privacy like C++, writing flexible metaprogramming tools or ORMs (Object-Relational Mappers) would be significantly harder.

---

### Best Practices: When to Mangle?

Given that name mangling exists, you might be tempted to use `__variable` everywhere to make your code “safer.” This is generally considered an anti-pattern in Python.

*   **Debugging Difficulty:** You can’t just type `obj.__var` in the debugger; you have to remember the class name and the mangling rules.
*   **Inflexibility:** If you design a class meant to be extended, using double underscores prevents subclasses from accessing parts of the parent state that they might legitimately need to modify. You are locking them out of the “implementation details” that Python usually allows them to touch.

#### The Rules of Engagement

1.  **Use `public_variable` (No underscore):** For data that is part of the class’s contract. This is the API.
2.  **Use `_protected_variable` (Single underscore):** For 95% of your internal state. It signals intent without adding complexity. It allows subclasses to access the data if they really need to.
3.  **Use `__private_variable` (Double underscore):** ONLY when:
    *   You are writing a library or framework that will be widely distributed.
    *   You anticipate your class will be subclassed deeply and by people you don’t know.
    *   The attribute name is generic (like `context`, `id`, `state`, or `config`) and highly likely to collide with a subclass’s attribute name.

---

### Conclusion

Python’s lack of strict access modifiers is not a missing feature; it is a deliberate design choice favoring simplicity and transparency. The language provides tools for every scenario: properties for logic encapsulation, single underscores for social contracts, and name mangling for namespace safety in inheritance.

The double underscore is a powerful tool, but it is not a lock. It is a namespace partition. By understanding that `__private` is actually just `_ClassName__private`, you can stop treating it as a security feature and start using it for its true purpose: ensuring your framework classes play nicely in a complex inheritance chain.

Treat your fellow developers as consenting adults. Mark your internal API with a single underscore, document your code, and trust that if someone bypasses your conventions, they have a specific reason — and the responsibility — for doing so.
