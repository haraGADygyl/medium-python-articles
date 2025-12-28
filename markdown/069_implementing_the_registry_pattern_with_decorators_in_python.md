# Implementing the Registry Pattern with Decorators in Python
#### How to use Python’s first-class functions and import lifecycle to replace messy if/else chains with self-assembling plugin systems.

**By Tihomir Manushev**  
*Dec 28, 2025 · 7 min read*

---

One of the most persistent sources of technical debt in growing Python applications is the “Centralized Dispatch” anti-pattern. You know this code. It usually lives in a file named `main.py` or `router.py`, and it looks like a towering skyscraper of `if/elif/else` statements or a manually maintained dictionary mapping strings to classes.

Every time a developer adds a new feature — a new payment gateway, a new file export format, or a new event handler — they must not only write the logic but also remember to open this central file and manually wire it up. If they forget, the code sits dead in the codebase, unreachable and useless.

This violates the Open/Closed Principle: our core dispatch logic should be open for extension but closed for modification. We shouldn’t have to surgically alter our main execution loop just to add a plugin.

The solution lies in leveraging Python’s dynamic nature and its treatment of functions as first-class objects. By combining the Registry Pattern with Decorators, we can create “self-assembling” architectures where modules plug themselves into the system simply by existing.

---

### The Mechanics of Discovery

To understand why this pattern works, we must look at how CPython handles module loading.

In compiled languages like C++ or Java, annotations often require compile-time processing or complex runtime reflection scanning to locate classes. Python is different. In Python, a module is an object, and “loading” a module is actually executing it.

When you write `import my_module`, the Python interpreter reads that file from top to bottom and executes every statement. Function definitions (`def my_func…`) are executable statements that create function objects and bind them to names. Decorators (`@register`) are simply syntactic sugar for function calls that happen at that exact moment of definition.

This means we can use the “Import Time” phase of the Python lifecycle to perform architectural wiring. We can trick the modules into announcing their presence to a central registry before the “Runtime” phase (when business logic actually executes) ever begins.

---

### The Architecture: A Data Ingestion Pipeline

Let’s visualize this with a concrete, production-grade scenario. Imagine we are building a Data Ingestion System. We receive blobs of data from various third-party sources (webhooks, FTP drops, APIs), and we need to process them. The source type is identified by a string key (e.g., ‘stripe_webhook’, ‘aws_sns’, ‘legacy_xml’).

#### 1. The Contract (Protocols)

First, we define a rigorous interface. We don’t want just any function ending up in our registry. We use `typing.Protocol` to enforce structural subtyping, ensuring any registered handler adheres to the expected signature.

```python
# registry.py
from typing import Protocol, Any, TypeAlias
from dataclasses import dataclass

# Modern Type Aliases (Python 3.10+)
Payload: TypeAlias = dict[str, Any]
IngestionResult: TypeAlias = bool

@dataclass(frozen=True)
class EventContext:
    source_ip: str
    timestamp: float
    request_id: str

class IngestionHandler(Protocol):
    """
    Protocol defining the shape of any function capable
    of handling an ingestion event.
    """
    def __call__(self, payload: Payload, context: EventContext) -> IngestionResult:
        ...
```

#### 2. The Registry and The Decorator

Next, we create the mechanism. This code usually lives in a dedicated module (e.g., `registry.py`) to avoid circular imports.

This decorator performs two roles:

1.  **Registration:** It saves the function into a global dictionary.
2.  **Passthrough:** It returns the original function unmodified, so it remains unit-testable and callable directly.

```python
# registry.py
from typing import Protocol, Any, TypeAlias, Callable
from dataclasses import dataclass
from collections.abc import MutableMapping

# --- 1. The Contract (Types) ---

# Modern Type Aliases (Python 3.10+)
Payload: TypeAlias = dict[str, Any]
IngestionResult: TypeAlias = bool


@dataclass(frozen=True)
class EventContext:
    source_ip: str
    timestamp: float
    request_id: str


class IngestionHandler(Protocol):
    """
    Protocol defining the shape of any function capable
    of handling an ingestion event.
    """

    def __call__(self, payload: Payload, context: EventContext) -> IngestionResult:
        ...


# --- 2. The Registry Logic ---

# The Central Registry
# Maps a string key (e.g., 'stripe') to a callable handler
_HANDLERS: MutableMapping[str, IngestionHandler] = {}


class DuplicateHandlerError(Exception):
    """Raised when a handler name collides with an existing one."""
    pass


def register_handler(source_key: str) -> Callable:
    """
    A parameterized decorator factory.

    Usage:
        @register_handler("stripe")
        def handle_stripe(...): ...
    """

    def _decorator(func: IngestionHandler) -> IngestionHandler:
        if source_key in _HANDLERS:
            raise DuplicateHandlerError(
                f"Handler for '{source_key}' already registered by {_HANDLERS[source_key].__name__}"
            )

        # The Side Effect: Wiring the architecture
        _HANDLERS[source_key] = func

        # Return the function unchanged so it remains importable and testable
        return func

    return _decorator


def get_handler(source_key: str) -> IngestionHandler:
    """Retrieve a handler, raising an error if unknown."""
    try:
        return _HANDLERS[source_key]
    except KeyError:
        raise NotImplementedError(f"No handler registered for source: {source_key}")
```

#### 3. The Implementations (Plugins)

Now, developers can write their logic in separate modules. Notice that these modules do not need to import the “Main App.” They only need the registry. This reverses the dependency direction.

```python
# plugins/payment_handlers.py
from registry import register_handler, EventContext, Payload

@register_handler("stripe_webhook")
def process_stripe(payload: Payload, ctx: EventContext) -> bool:
    print(f"[{ctx.request_id}] Processing Stripe payment: {payload.get('amount')}")
    # Complex business logic here...
    return True

@register_handler("paypal_ipn")
def process_paypal(payload: Payload, ctx: EventContext) -> bool:
    print(f"[{ctx.request_id}] Processing PayPal IPN for user {payload.get('user_id')}")
    return True

# plugins/system_handlers.py
from registry import register_handler, EventContext, Payload

@register_handler("aws_sns")
def process_sns_notification(payload: Payload, ctx: EventContext) -> bool:
    print(f"[{ctx.request_id}] Received infrastructure alert: {payload.get('message')}")
    return True
```

#### 4. The Main Execution Loop

Finally, our application logic becomes incredibly simple. It doesn’t know about Stripe or AWS. It only knows about the Registry.

```python
# main.py
import time
from registry import get_handler, EventContext

# CRITICAL: We must ensure the modules are imported so the decorators run!
# In a real app, you might use importlib to scan a directory.
import plugins.payment_handlers
import plugins.system_handlers

def ingest_event(source: str, data: dict):
    ctx = EventContext(
        source_ip="127.0.0.1", 
        timestamp=time.time(), 
        request_id="req_12345"
    )
    
    try:
        # Dispatch dynamically
        handler = get_handler(source)
        success = handler(data, ctx)
        print(f"Result: {'Success' if success else 'Failure'}")
        
    except NotImplementedError as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Simulate incoming traffic
    ingest_event("stripe_webhook", {"amount": 5000, "currency": "usd"})
    ingest_event("aws_sns", {"message": "CPU High"})
    ingest_event("unknown_source", {})
```

---

### The Hidden Details

While the implementation looks straightforward, there are several engineering nuances that separate a toy example from a production implementation.

#### State Persistence and Global Scope

The `_HANDLERS` dictionary is a global variable. In Python, “global” actually means “module-level.” Because Python modules are singletons (cached in `sys.modules`), this dictionary persists for the life of the process. This makes it an effective, lightweight storage mechanism for the registry.

However, because it is mutable global state, we must be careful. The `register_handler` decorator includes a check for `DuplicateHandlerError`. This is vital. Without it, if two developers accidentally use the key “stripe”, the second module imported would silently overwrite the first, leading to baffling runtime bugs.

#### The Import-Time Dependency

The most fragile part of this pattern is ensuring the modules containing the decorated functions are actually imported. If `main.py` never imports `plugins.payment_handlers`, the Python interpreter never parses that file, the `@register_handler` line never executes, and the registry remains empty.

In frameworks like Django or Flask, this is often solved by an “App Factory” pattern where plugins are explicitly listed in a configuration file, and the app iterates through that list using `importlib.import_module`. This provides a nice middle ground: you don’t hardcode logic, but you do explicitly define the scope of the application.

#### Why Not Just Use Classes?

A Java developer might look at this and ask, “Why not create an abstract BaseHandler class and find all subclasses?”

You could, using `BaseHandler.__subclasses__()`. However, that approach couples your implementations to an inheritance hierarchy. If you later decide a handler needs to inherit from a `DatabaseModel` or a `ThreadMixin`, you might encounter the Diamond Problem or metaclass conflicts.

By using decorators on functions (or classes), you decouple the mechanism of registration from the implementation of the logic. The handler doesn’t need to be a child of a specific class; it just needs to behave (Protocol) correctly and identify itself (Decorator).

---

### Advanced Refinements

#### Parametric Decorators with Metadata

In the example above, `register_handler` takes an argument (`source_key`). This creates a closure. The outer function (`register_handler`) receives the arguments and returns the inner function (`_decorator`), which receives the function being decorated.

We can expand this to store more than just the function. We could store metadata:

```python
@register_handler("stripe", version=2, retry_policy="exponential")
def handle_stripe(...): ...
```

The registry could then become a dictionary of `HandlerMetadata` objects, allowing the main loop to make intelligent decisions (e.g., “This handler is deprecated, log a warning”).

#### Testing the Registry

Testing code that relies on global side effects can be tricky. When writing unit tests for the registry logic, you should ensure isolation. The `unittest.mock.patch.dict` context manager is perfect for this:

```python
from unittest.mock import patch
from registry import _HANDLERS, register_handler

def test_registration():
    # Patch the global registry dict so we don't pollute other tests
    with patch.dict(_HANDLERS, {}, clear=True):
        @register_handler("test_key")
        def dummy_func(p, c): return True
        
        assert "test_key" in _HANDLERS
        assert _HANDLERS["test_key"] == dummy_func
```

---

### Conclusion

The Registry Pattern using decorators is a quintessential Pythonic idiom. It replaces rigid, hard-coded control flow with a flexible, declarative structure. It allows your codebase to grow horizontally — adding new capabilities by adding new files — without constantly destabilizing the vertical pillars of your core application logic.

By understanding the mechanics of Python’s import system and the first-class nature of functions, we move away from writing scripts that simply run top-to-bottom and start building architectures that assemble themselves.
