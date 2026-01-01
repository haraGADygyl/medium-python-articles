# The Time Machine in Your Code: Refactoring Undo with Python Closures
#### Why Python’s __closure__ and first-class functions make the classic Command Pattern obsolete for in-memory history management

**By Tihomir Manushev**  
*Jan 1, 2026 · 8 min read*

---

If there is one feature that separates a toy script from a production-grade application, it is the ability to say “oops.”

The “Undo” operation (Ctrl+Z) is a fundamental user expectation. However, implementing it requires a significant architectural decision: how do we capture the state of the past? In the strict object-oriented world, particularly in languages like Java or C++, this is the textbook use case for the Command Design Pattern. The standard recipe involves creating a class hierarchy where every action is an object encapsulating both the logic to execute a change and the logic to undo it.

But Python is not Java. While the Command pattern is perfectly valid in Python, strictly adhering to its class-heavy structure often leads to what I call “architectural noise” — boilerplate code that obscures the actual logic.

In this article, we will explore how Python’s first-class functions allow us to refactor the Command pattern. We will move from heavy, stateful objects to lightweight functional streams, utilizing closures and `functools.partial` to capture state. We will also dissect the CPython internals to understand the memory implications of this shift.

---

### The Classical Approach: The Command Pattern

Let’s establish the baseline. We are building a backend for a Smart Home Lighting System. Users can change the brightness or color temperature of various smart bulbs. We need to support an undo stack.

In the classic “Gang of Four” (GoF) approach, we need four participants:

1.  **Receiver:** The actual light bulb (holds the state).
2.  **Command Interface:** An abstract base class defining execute and undo.
3.  **Concrete Commands:** Classes like `BrightnessCommand` that store the previous state.
4.  **Invoker:** The controller that holds the history stack.

Here is a robust, type-hinted implementation using Python 3.10+:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

# --- The Receiver ---
@dataclass
class SmartBulb:
    location: str
    brightness: int = 0  # 0 to 100
    color_temp: int = 3000  # Kelvin

    def __repr__(self) -> str:
        return f"<{self.location} | {self.brightness}% | {self.color_temp}K>"

# --- The Command Interface ---
class Command(ABC):
    @abstractmethod
    def execute(self) -> None:
        """Apply logic."""

    @abstractmethod
    def undo(self) -> None:
        """Revert logic."""

# --- Concrete Command ---
@dataclass
class ChangeBrightness(Command):
    bulb: SmartBulb
    target_level: int
    _previous_level: int = field(init=False)

    def execute(self) -> None:
        # Capture state before mutation
        self._previous_level = self.bulb.brightness
        self.bulb.brightness = self.target_level
        print(f"[CMD] Set {self.bulb.location} to {self.target_level}%")

    def undo(self) -> None:
        print(f"[UNDO] Reverting {self.bulb.location} to {self._previous_level}%")
        self.bulb.brightness = self._previous_level

# --- The Invoker ---
class RemoteController:
    def __init__(self) -> None:
        self._history: list[Command] = []

    def press(self, command: Command) -> None:
        command.execute()
        self._history.append(command)

    def undo_last(self) -> None:
        if not self._history:
            print("Nothing to undo.")
            return
        cmd = self._history.pop()
        cmd.undo()

# --- Usage ---
if __name__ == "__main__":
    living_room = SmartBulb("Living Room")
    remote = RemoteController()

    # Create command instances
    cmd1 = ChangeBrightness(living_room, 50)
    cmd2 = ChangeBrightness(living_room, 100)

    remote.press(cmd1) # <Living Room | 50% | 3000K>
    remote.press(cmd2) # <Living Room | 100% | 3000K>
    
    remote.undo_last() # Reverts to 50%
    print(living_room)
```

This code is clean and solid. However, look at the `ChangeBrightness` class. It exists solely to store `_previous_level` and map the undo method to the assignment operation. We are creating a new class definition, instantiating objects, and managing attribute access just to delay a function call. In Python, where functions are first-class citizens, we can do better.

---

### The Functional Refactor: Closures as State Containers

To simplify this, we must realize that an object with a single method (or two, in this case) is essentially a closure in disguise.

We can replace the Concrete Command class with a Higher-Order Function. This function performs the action and returns a callable responsible for the undo operation.

Why return the undoer dynamically? Because the state required to undo an action (the previous brightness) is most easily captured at the exact moment the action is performed.

Here is the functional equivalent:

```python
from typing import Callable, TypeAlias
from dataclasses import dataclass

# Type alias for our undo function
Undoer: TypeAlias = Callable[[], None]

@dataclass
class SmartBulb:
    location: str
    brightness: int = 0

    def __repr__(self) -> str:
        return f"<{self.location}: {self.brightness}%>"

# --- Functional Commands ---

def set_brightness(bulb: SmartBulb, level: int) -> Undoer:
    """
    Applies the change immediately and returns a closure 
    that captures the previous state to allow undoing.
    """
    prev_level = bulb.brightness
    bulb.brightness = level
    print(f"[FUNC] Set {bulb.location} to {level}%")

    # The Closure
    def undo_action() -> None:
        print(f"[FUNC UNDO] Reverting {bulb.location} to {prev_level}%")
        bulb.brightness = prev_level

    return undo_action

# --- The Invoker (Functional) ---
class FunctionalController:
    def __init__(self) -> None:
        # The history is now simply a stack of functions
        self._undo_stack: list[Undoer] = []

    def execute(self, undoer: Undoer) -> None:
        # In this pattern, the action executes before being passed here,
        # receiving the undo closure is the signal that it happened.
        self._undo_stack.append(undoer)

    def undo_last(self) -> None:
        if not self._undo_stack:
            print("Nothing to undo.")
            return
        # Pop the function and call it
        undo_func = self._undo_stack.pop()
        undo_func()

# --- Usage ---
if __name__ == "__main__":
    kitchen = SmartBulb("Kitchen")
    controller = FunctionalController()

    # 1. Execute and register the undoer
    undo_token = set_brightness(kitchen, 75)
    controller.execute(undo_token)

    # 2. Execute again
    undo_token_2 = set_brightness(kitchen, 20)
    controller.execute(undo_token_2)

    # 3. Undo
    controller.undo_last() # Reverts to 75%
    print(kitchen)
```

The magic happens inside `set_brightness`. When we define `undo_action` inside the parent function, `undo_action` retains access to the variable scope of `set_brightness`.

Specifically, it captures `prev_level`. Even after `set_brightness` returns, the `prev_level` variable stays alive because it is bound to the `undo_action` function object.

In CPython, this is not magic; it is a specific data structure. If we inspect our undo_token, we can see the captured variables:

```python
print(undo_token.__closure__)
```

The `__closure__` attribute contains a tuple of cells. These cells are special wrappers that reference the objects (kitchen instance and the integer 75) required by the function to run later. This creates a lightweight, self-contained snapshot of the past state without defining a class to hold it explicitly.

---

### Deep Dive: Memory and Performance
#### 1. Memory Allocation

Is the functional approach merely syntactic sugar, or does it offer performance benefits?

In the OOP example, every action instantiates a `ChangeBrightness` object. In Python, an object instance carries a `__dict__` (unless `__slots__` is used) to store attributes. This is a hash map, which has a memory overhead.

In the functional example, we create a function object (the closure). While function objects also have overhead, they do not typically have a `__dict__` for attributes. Instead, they use the `__closure__` tuple. Generally, the memory footprint of a closure created at runtime is comparable to or slightly smaller than a slotted class instance, but significantly smaller than a standard dictionary-backed instance.

#### 2. Implementation Simplicity

The functional approach removes the need for:

*   Inheritance checks (`isinstance` logic).
*   Attribute lookups (`self.bulb`, `self.target_level`).
*   Abstract Base Class dispatch mechanisms.

However, there is a trade-off in introspection. With the OOP Command object, you can easily inspect `cmd.bulb` or `cmd.target_level` later (perhaps to display a history log to the user: “Changed brightness to 50%”). With the closure `undo_action`, the data is hidden inside `__closure__` cells. Introspecting this is difficult and brittle. If your UI needs to display a list of undoable actions by name, the functional approach needs to be augmented (e.g., by attaching a `__doc__` string or a custom attribute to the closure).

---

### Alternate Functional Strategy: functools.partial

Sometimes you don’t need a custom inner function. If the undo logic is symmetrical to the do logic, you can use `functools.partial`.

Let’s say we have a generic function:

```python
from functools import partial

def set_color(bulb: SmartBulb, hex_code: str) -> None:
    print(f"Setting {bulb.location} color to {hex_code}")
    bulb.color_hex = hex_code

# The Logic
current_color = my_bulb.color_hex
set_color(my_bulb, "#FF0000")

# The Undo is just the same function, pre-filled with old arguments
undo_step = partial(set_color, my_bulb, current_color)
history.append(undo_step)
```

`partial` creates a callable object that freezes the arguments (`my_bulb`, `current_color`) inside the object’s `func`, `args`, and `keywords` attributes. It is efficient, implemented in C, and cleaner than writing a lambda.

---

### The Serialization

There is one specific scenario where the Command Pattern (OOP) strictly beats the Functional/Closure approach: **Persistence**.

If you need to save your undo stack to disk (to survive an application crash or restart), you typically use Python’s `pickle` module.

*   **Pickle loves Classes:** Pickle handles class instances easily (by saving the module path, class name, and `__dict__`).
*   **Pickle does not love Closures:** Pickle cannot serialize inner functions (closures) or lambdas because they have no stable name in the module’s global namespace.

If your “Undo” feature is session-based (in-memory only), callables are superior. If your “Undo” must persist across sessions, stick to the Command class.

---

### Best Practice Implementation: The Reversible Action Protocol

For most modern Python applications (web backends, data processing pipelines, or CLI tools) where persistence of the undo stack is not required, I recommend a hybrid approach: **The Reversible Action Protocol**.

Instead of inheritance, use `typing.Protocol` (structural subtyping) and Callables.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Reversible(Protocol):
    def __call__(self) -> None: ...
    # We could attach metadata here if needed

class ActionManager:
    def __init__(self):
        self.undo_stack: list[Reversible] = []
        self.redo_stack: list[Reversible] = []

    def do(self, action: Callable[[], Reversible]):
        """
        Takes a function that performs an action AND returns its undoer.
        """
        undoer = action()
        self.undo_stack.append(undoer)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        undoer = self.undo_stack.pop()
        # Execute undo
        undoer()
```

This allows you to mix and match: partial objects, closures, or even full-blown Class instances (as long as they implement `__call__`), giving you the flexibility of functions with the power of objects when you need it.

---

### Conclusion

The Command pattern was designed in an era where functions were not objects. In Python, strictly adhering to the “Class per Command” structure is an anti-pattern when the commands are stateless or simple.

By leveraging closures, we transform the “Undo” problem from one of Class Design to one of Scope Management. We capture the state of the world in the `__closure__` cells of a function, creating a lightweight, straightforward history stream. However, as with all architectural choices, consider the lifespan of your data: if the history needs to outlive the process, objects remain king. For everything else, embrace the function.
