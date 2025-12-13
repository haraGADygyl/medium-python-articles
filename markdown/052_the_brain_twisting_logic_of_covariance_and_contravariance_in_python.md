# The Brain-Twisting Logic of Covariance and Contravariance in Python
#### Understanding the subtle geometry of Python’s type system to prevent runtime crashes in higher-order functions.

**By Tihomir Manushev**  
*5 days ago · 7 min read*

---

If you have ever spent time annotating callbacks or higher-order functions in Python, you have likely encountered a specific flavor of frustration. You define a function that seems perfectly logical, you pass it as an argument to another function, and suddenly your type checker (be it Mypy, Pyright, or Pyre) screams at you with a dense error message about incompatible types.

You might stare at the screen and think: “But Integer is a subtype of Float! Why can’t I use a function that returns an integer where a float is expected?” Or worse: “Why can’t I use a function that handles Any object where a function expecting a String is required?”

Welcome to the rabbit hole of Variance.

In the realm of Python type hinting, understanding simple inheritance is easy. Understanding how generic types behave when they interact with inheritance — specifically within the context of function signatures — is where the “alchemy” happens. Today, we are going to deconstruct the brain-twisting logic of Covariance and Contravariance in Callable types.

---

### The Hierarchy: Setting the Stage

To explain this without getting lost in abstract algebra, we need a concrete class hierarchy. Let’s imagine we are building a notification system for a cloud platform.

We have a base class Notification, a specific subclass Email, and an even more specific subclass AlertEmail.

```python
class Notification:
    """Base class for all notifications."""
    pass

class Email(Notification):
    """Standard email notification."""
    pass

class AlertEmail(Email):
    """High-priority email requiring immediate attention."""
    pass
```

The relationship is strict:

1.  Every `AlertEmail` is an `Email`.
2.  Every `Email` is a `Notification`.

This adheres to the Liskov Substitution Principle (LSP): anywhere you expect a `Notification`, you should be able to provide an `Email`, because an `Email` is a `Notification`.

But what happens when we wrap these types inside a Callable?

---

### Covariance (The Intuitive Part)

Let’s look at return values. This is usually the part of variance that clicks easiest for developers because it flows in the same direction as inheritance.

Imagine we have a factory function type alias. We need a callable that produces an Email.

```python
from typing import Callable

# We expect a function that takes no arguments and returns an Email
EmailFactory = Callable[[], Email]
```

Now, consider these two potential implementations:

```python
def create_notification() -> Notification:
    return Notification()

def create_alert() -> AlertEmail:
    return AlertEmail()
```

Which of these is compatible with `EmailFactory`?

#### The Analysis

If I ask you for a function that returns an `Email`, and you give me `create_alert`, I am happy. I asked for an `Email`, and you gave me an `AlertEmail`. Since an `AlertEmail` is an `Email`, my code can treat the result exactly as expected.

However, if you give me `create_notification`, I am in trouble. I asked for an `Email` (perhaps so I can access a `.subject` field), but you gave me a generic `Notification` (which might be an SMS or a Push, lacking the subject line). My code will crash at runtime.

#### The Rule: Covariance

This behavior is called Covariance.

*   **Co-** (meaning “with” or “together”): The relationship moves in the same direction as the inheritance.
*   `AlertEmail` is a subtype of `Email`.
*   Therefore, `Callable[[], AlertEmail]` is a subtype of `Callable[[], Email]`.

In Python terms, return types are covariant. You can always return a more specific type than declared, but never a more generic one.

---

### Contravariance (The Brain-Twister)

Here is where logic seems to invert itself. We must look at function arguments (parameters).

Let’s define a “Sender” callback. This is a function responsible for taking an object and sending it. Our system requires a function that knows how to send an Email.

```python
# We need a function that accepts an Email as an argument
EmailSender = Callable[[Email], None]
```

Now, consider these three candidates:

```python
def send_notification(n: Notification) -> None:
    print(f"Sending generic notification: {n}")

def send_email(e: Email) -> None:
    print(f"Sending email: {e}")

def send_alert(a: AlertEmail) -> None:
    print(f"Sending RED ALERT: {a}")
```

We have a function `process_queue` that takes our `EmailSender` callback:

```python
def process_queue(sender: EmailSender, item: Email) -> None:
    sender(item)
```

Which function can we pass to `process_queue`?

1.  **Passing `send_email`:** This is an exact match. It works.
2.  **Passing `send_alert`:** This accepts an `AlertEmail`. But wait — `process_queue` is holding a generic `Email`. If `process_queue` passes a standard `Email` to `send_alert`, the `send_alert` function might try to access fields that only exist on `AlertEmail` (like `a.siren_level`). This would crash.
3.  **Passing `send_notification`:** This accepts any `Notification`. If `process_queue` passes it an `Email`, that’s fine! An `Email` is a `Notification`. The function knows how to handle the broader category, so it can definitely handle the specific category.

#### The Rule: Contravariance

This is Contravariance.

*   **Contra-** (meaning “against” or “opposite”): The relationship moves in the opposite direction of inheritance.
*   `Notification` is a parent of `Email`.
*   But `Callable[[Notification], None]` is a subtype of `Callable[[Email], None]`.

To be type-safe, a callback must be able to accept at least what you promise to give it. If you promise to give it an `Email`, a function that can handle any `Notification` is safe. A function that demands an `AlertEmail` is picky and unsafe.

---

### The Grand Unification: Callable

When you see a complex `Callable` annotation, you are seeing both variance rules operating simultaneously.

The Callable type is:

*   **Contravariant** on arguments (Inputs).
*   **Covariant** on return types (Outputs).

Let’s visualize this with a unified example. We are building a plugin system for an e-commerce platform. We need a “Processor” that takes a specific Order and returns a Receipt.

```python
class Order: ...
class InternationalOrder(Order): ...

class Receipt: ...
class DetailedReceipt(Receipt): ...

# The strict signature required by our plugin system
PluginProcessor = Callable[[InternationalOrder], Receipt]
```

Our plugin system says: “I will give you an InternationalOrder (or a subtype), and I demand you give me back a Receipt (or a subtype).”

Now, let’s look at a candidate function written by a developer:

```python
def my_processor(o: Order) -> DetailedReceipt:
    ...
```

Is `my_processor` compatible with `PluginProcessor`? Let’s trace the alchemy.

**Input Check (Contravariance):**

*   The requirement is `InternationalOrder`.
*   The candidate accepts `Order`.
*   Since `Order` is a parent of `InternationalOrder`, the candidate is “liberal” in what it accepts. It can handle the `InternationalOrder` we plan to pass it. Safe.

**Output Check (Covariance):**

*   The requirement is `Receipt`.
*   The candidate returns `DetailedReceipt`.
*   Since `DetailedReceipt` is a child of `Receipt`, the candidate returns something more specific than requested. Safe.

Therefore, `Callable[[Order], DetailedReceipt]` is a subtype of `Callable[[InternationalOrder], Receipt]`.

The input type widened (went up the hierarchy), and the output type narrowed (went down the hierarchy).

---

### The “Invariant” Trap of Mutable Collections

It is vital to distinguish Callable variance from Collection variance. This is a common pitfall.

If `AlertEmail` is a subtype of `Email`, is `list[AlertEmail]` a subtype of `list[Email]`?

No. Mutable collections in Python are Invariant.

Why?

```python
alerts: list[AlertEmail] = [AlertEmail(), AlertEmail()]
emails: list[Email] = alerts  # If type checker allowed this...

emails.append(Email())  # ...we could do this.
```

If we treated `list[AlertEmail]` as a `list[Email]`, we could append a plain `Email` into it. But the underlying list is referenced by the `alerts` variable, which believes it only holds `AlertEmail` objects. Later, when we iterate over `alerts` and try to access specific alert features on that plain email, the program crashes.

Because `Callable` represents an operation (code) rather than a holding container (data), it follows the flow of data through the operation, adhering to covariance and contravariance.

---

### Why This Matters for Your Architecture

You might be thinking, “We are obsessing over theory.” But this theory is the difference between a robust architecture and a brittle one.

When you design libraries or internal APIs using callbacks, you are defining contracts.

If you use `Callable` type hints correctly, you give your consumers flexibility. You allow them to pass functions that are more powerful (accept wider inputs) or more informative (return stricter outputs) than you strictly realized you needed.

If you don’t understand variance, you might be tempted to use `Any`.

```python
# The lazy approach
def register_handler(handler: Callable[[Any], Any]): ...
```

By doing this, you turn off the lights. You lose the ability for the IDE to tell you, “Hey, you’re trying to pass a Notification handler to a system that only produces integers.” You invite runtime `AttributeError` exceptions that happen strictly in production when a rare event type triggers a handler that wasn’t designed for it.

---

### Conclusion

Covariance and Contravariance are not just academic terms from category theory; they are the traffic rules of a type system.

*   **Covariance (Outputs):** “I can give you more than you asked for.” (Subclass return is OK).
*   **Contravariance (Inputs):** “I can accept more than you plan to give me.” (Superclass argument is OK).

Mastering this mental flip — specifically regarding function arguments — is what separates a Python scripter from a Python software engineer. It allows you to write type definitions that are precise, safe, and surprisingly flexible.

The next time Mypy yells at you for a `Callable` mismatch, don’t just change the type to `Any`. Stop. Trace the hierarchy. Ask yourself: Am I narrowing the input when I should be widening it? Am I widening the output when I should be narrowing it?

Respect the variance, and the type system will respect you.