# Beyond Inheritance: Modernizing the Command Pattern with Python Protocols
#### Why structural subtyping is the key to loosely coupled, type-safe Python architectures

**By Tihomir Manushev**  
*Dec 30, 2025 · 7 min read*

---

For nearly two decades, Python developers attempting to implement the classic Gang of Four (GoF) design patterns faced a philosophical friction. The strict, object-oriented definitions provided in Design Patterns: Elements of Reusable Object-Oriented Software relied heavily on strict inheritance hierarchies — a concept that felt alien in Python’s dynamic, duck-typed ecosystem.

To bridge this gap, Python 2.6 introduced Abstract Base Classes (ABCs). They allowed us to formalize interfaces, providing a “nominal” type system where a class had to explicitly declare its ancestry to be treated as a valid subtype. While effective, this approach reintroduced the rigidity of Java or C++ into Python codebases, coupling implementation details with interface definitions.

With the advent of Python 3.8 and the maturation of static analysis tools like Mypy, we witnessed a paradigm shift: the introduction of `typing.Protocol`. Protocols bring standardized structural subtyping to Python. They allow us to enforce strict interfaces without requiring inheritance, effectively “formalizing duck typing.”

In this article, we will modernize the classic Command pattern. We will move away from the rigid hierarchy of ABCs and toward the flexible, decoupled nature of Protocols, examining the mechanical differences and performance implications along the way.

---

### The Legacy Approach: The Abstract Base Class

The Command pattern decouples an object that invokes an operation (the Invoker) from the object that knows how to perform it (the Receiver). In a strictly nominal type system, this requires an interface — usually an abstract class — that dictates the structure of the Command.

Let’s imagine a Smart Home system. We have a central hub (the Invoker) that queues actions for various IoT devices (Receivers), such as lights, thermostats, and locks.

Here is how we would traditionally structure this using `abc.ABC`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
import time

# 1. The Explicit Interface (Nominal Subtyping)
class IOTCommand(ABC):
    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""
    
    @abstractmethod
    def undo(self) -> None:
        """Revert the command."""

# 2. The Receiver
class SmartLight:
    def turn_on(self) -> None:
        print("💡 Light is now ON")
    
    def turn_off(self) -> None:
        print("🌑 Light is now OFF")

# 3. The Concrete Command
@dataclass
class ToggleLightCommand(IOTCommand):
    light: SmartLight
    
    def execute(self) -> None:
        self.light.turn_on()
        
    def undo(self) -> None:
        self.light.turn_off()

# 4. The Invoker
class HomeHub:
    def __init__(self) -> None:
        self._history: list[IOTCommand] = []

    def run(self, command: IOTCommand) -> None:
        print(f"[{time.strftime('%X')}] Running command...")
        command.execute()
        self._history.append(command)

    def undo_last(self) -> None:
        if self._history:
            cmd = self._history.pop()
            print(f"[{time.strftime('%X')}] Undoing...")
            cmd.undo()

# Usage
hub = HomeHub()
light = SmartLight()
cmd = ToggleLightCommand(light)

# This works because ToggleLightCommand explicitly inherits from IOTCommand
hub.run(cmd)
hub.undo_last()
```

While the code above is robust, it suffers from nominal coupling. The `HomeHub` relies on the `IOTCommand` class. If you import a library of third-party smart device commands that strictly follow the structure of a command (they have execute and undo) but do not inherit from your specific `IOTCommand` ABC, they are incompatible with your `HomeHub`.

To fix this with ABCs, you would have to write adapter wrappers for every third-party class, manually registering them as subclasses using `IOTCommand.register()`, or rewriting the third-party code. This negates the dynamic flexibility that makes Python productive.

---

### The Functional Interlude: Callable

Experienced Python developers often look at single-method interfaces (like a Command that only has execute) and correctly identify that they are just functions in disguise.

We could replace `IOTCommand` with `typing.Callable[[], None]`. This works beautifully for simple callbacks. However, the Command pattern often requires state (like the light instance) and metadata (like an undo operation).

While you can attach attributes to functions, standard function types (`Callable`) cannot express “I need a callable that also has an undo method” to a static type checker. This is where Protocols shine.

---

### The Modern Approach: typing.Protocol

`typing.Protocol` allows us to define an interface based on what an object does, not what it inherits from. This is structural subtyping. If class A has the methods defined in Protocol P, then A is a subtype of P, even if A has never heard of P.

Let’s refactor our Smart Home system using Protocols.

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

# 1. The Structural Interface
@runtime_checkable
class Reversible(Protocol):
    def execute(self) -> None: ...
    def undo(self) -> None: ...

# 2. Receivers (unchanged)
class SmartLock:
    def lock(self) -> None:
        print("🔒 Door LOCKED")
    
    def unlock(self) -> None:
        print("🔓 Door UNLOCKED")

class Thermostat:
    def set_temp(self, temp: int) -> None:
        print(f"🌡️ Temp set to {temp}°C")

# 3. Concrete Commands (No inheritance needed!)
@dataclass
class LockDoorCommand:
    security_device: SmartLock

    def execute(self) -> None:
        self.security_device.lock()

    def undo(self) -> None:
        self.security_device.unlock()

@dataclass
class SetTempCommand:
    thermostat: Thermostat
    target_temp: int
    previous_temp: int = 20  # State for undo

    def execute(self) -> None:
        self.thermostat.set_temp(self.target_temp)

    def undo(self) -> None:
        self.thermostat.set_temp(self.previous_temp)

# 4. The Invoker
class SmartHub:
    def __init__(self) -> None:
        self._history: list[Reversible] = []

    def run(self, command: Reversible) -> None:
        # Static check: Mypy ensures 'command' has execute/undo
        # Runtime check: isinstance works because of @runtime_checkable
        if not isinstance(command, Reversible):
            raise TypeError(f"{type(command)} is not a Reversible command")
            
        command.execute()
        self._history.append(command)

# Usage
hub = SmartHub()
door_cmd = LockDoorCommand(SmartLock())
temp_cmd = SetTempCommand(Thermostat(), 24)

# These work perfectly, despite no inheritance relation to 'Reversible'
hub.run(door_cmd)
hub.run(temp_cmd)
```

---

### How Protocols Work

The magic happens in two places: static analysis (Mypy/Pyright) and runtime inspection (CPython).

#### 1. Static Analysis (The Compiler View)

When you run Mypy against the code above, it inspects the `LockDoorCommand` class. It sees that the class defines execute and undo with signatures matching `Reversible`. Therefore, it considers `LockDoorCommand` to be a subtype of `Reversible`.

If you were to rename `undo` to `revert` in `LockDoorCommand`, Mypy would flag an error at the `hub.run(door_cmd)` line, stating that `LockDoorCommand` is missing the undo attribute required by `Reversible`. This gives you the safety of strict interfaces with the flexibility of duck typing.

#### 2. Runtime Behavior (The CPython View)

By default, Protocols are erased at runtime; `isinstance(obj, MyProtocol)` will raise a TypeError. However, by decorating the Protocol with `@runtime_checkable`, we unlock specific behavior in CPython.

When `isinstance(door_cmd, Reversible)` is called, CPython triggers the `__instancecheck__` on the Protocol’s metaclass (`abc.ABCMeta`, which `typing.Protocol` uses internally).

For a standard ABC, this check looks at the `__mro__` (Method Resolution Order) to find an ancestral link. For a runtime-checkable Protocol, it inspects the attributes of the instance. It iterates over the attributes defined in the Protocol and verifies their presence on the target object.

**Performance Warning:** Because `@runtime_checkable` performs introspection (iterating over `dir(instance)` or `__dict__`), it is significantly slower than a standard inheritance-based `isinstance` check. In high-performance loops (e.g., dispatching millions of commands per second), rely on static type checking and avoid runtime `isinstance` checks against Protocols if possible.

---

### Callables vs. Protocols: The Hybrid approach

Sometimes, the Command pattern is implemented using classes that implement `__call__`, making instances behave like functions. Protocols handle this elegantly.

If you want a Command that is callable and has a description attribute (useful for logging), `typing.Callable` is insufficient. You cannot define `Callable[[args], ret] + {description: str}`.

You can, however, define a Protocol with `__call__`:

```python
class DescriptiveCommand(Protocol):
    description: str
    
    def __call__(self) -> None: ...

class BackupDatabase:
    def __init__(self, db_name: str):
        self.description = f"Backing up {db_name}"
    
    def __call__(self) -> None:
        print(f"Performing backup...")

def scheduler(cmd: DescriptiveCommand) -> None:
    print(f"Scheduling: {cmd.description}")
    cmd()

# Works!
scheduler(BackupDatabase("UsersDB"))
```

This effectively bridges the gap between the functional approach (functions as objects) and the object-oriented approach (rich state and metadata).

---

### When to Use Which?

While Protocols represent the modern evolution of Python interfaces, ABCs are not dead.

**Use `abc.ABC` when:**

*   **Code Reuse is Primary:** You want to provide a base implementation (template method pattern) that children inherit. Protocols cannot provide method implementations.
*   **Strict Control:** You want to prevent instantiation of the base class (ABCs raise errors if instantiated; Protocols do not).
*   **Performance:** You rely heavily on runtime `isinstance` checks in tight loops.

**Use `typing.Protocol` when:**

*   **Decoupling is Primary:** You are writing a library or a framework (like our SmartHub) and want to accept objects from users without forcing them to inherit from your base classes.
*   **Multiple Interfaces:** A class needs to satisfy multiple disparate interfaces (e.g., Serializable, Renderable, Executable). With ABCs, this leads to complex multiple inheritance (the “diamond problem”). With Protocols, the class simply implements the methods — no inheritance hierarchy mess.
*   **Retrofitting:** You are adding type hints to an existing codebase where you cannot easily change the class hierarchy.

---

### Conclusion

The evolution from “Classic” GoF patterns to Pythonic implementations mirrors the evolution of Python itself. We started by mimicking C++ (Nominal inheritance/ABCs), moved to a purely dynamic era (ignoring types entirely), and have arrived at a sophisticated middle ground.

By replacing Abstract Base Classes with Protocols in the Command pattern, we embrace structural subtyping. We tell our Invokers: “I don’t care who your parents are; I only care what you can do.” This decoupling makes systems easier to test, easier to extend with third-party code, and more aligned with the dynamic spirit of Python, all while maintaining the compile-time safety that modern engineering teams demand.
