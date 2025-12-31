# Inside the Infinite `__call__` Chain of Python
#### Explaining the recursive nature of Python’s callable objects, method wrappers, and the CPython tp_call slot

**By Tihomir Manushev**  
*Dec 31, 2025 · 8 min read*

---

If you have spent enough time exploring the darker corners of the Python interpreter, you may have stumbled upon a syntactical oddity that looks like a glitch in the matrix. We know that to execute a function, we use the call operator `()`. We also know that under the hood, this invokes the `__call__` magic method.

So, logical deduction suggests that `my_func()` is roughly equivalent to `my_func.__call__()`. But if `__call__` is a method, and methods are objects in Python, does `__call__` have its own `__call__`?

Execute this in your terminal, and you will see the answer is a resounding “yes”:

```python
def void():
    return "Gazing into the abyss"

# This works
print(void.__call__()) 

# This also works
print(void.__call__.__call__())

# And this...
print(void.__call__.__call__.__call__())
```

You can chain this theoretically forever, limited only by your patience and stack depth. It looks like an infinite loop, or perhaps a recursion error waiting to happen. However, this behavior is not a quirk; it is a fundamental consequence of Python’s consistent object model. It is the “Ouroboros” — the snake eating its own tail — of language design.

In this deep dive, we are going to bypass the surface-level syntax and look directly at the CPython implementation to understand how method resolution, the `tp_call` slot, and method wrappers conspire to allow this infinite chaining.

---

### The Everything-is-an-Object Axiom

To understand the infinite `__call__`, we must first internalize the most distinct feature of Python: First-Class Objects.

In languages like C++ or Java (historically), a method is a distinct entity from data. In Python, functions and methods are full-blown objects. They have IDs, types, and attributes.

When you define a function in Python:

```python
def compute_entropy(data: list[int]) -> float:
    return 0.0
```

`compute_entropy` is an instance of the function class. Because it is an object, it can have methods. And the method that makes it “runnable” is `__call__`.

But here is the trick: when you access `compute_entropy.__call__`, you aren’t getting a raw function pointer. You are getting another object. Specifically, you are getting a method-wrapper.

---

### The CPython Internals: tp_call

Let’s drop down to C. In CPython (the standard Python implementation), every object is represented by a C struct called `PyObject`. Every `PyObject` has a reference to its type, stored in a `PyTypeObject`.

The `PyTypeObject` struct contains a collection of function pointers known as “slots.” These slots define how the object behaves. There is `tp_str` for string representation, `tp_iter` for iteration, and the star of our show: `tp_call`.

When you write `my_obj()`, the Python interpreter doesn’t immediately look for a `__call__` method in the dictionary. Instead, the opcode `CALL_FUNCTION` (or `CALL_METHOD` in newer versions) triggers a C-level check:

1.  It inspects the type of `my_obj`.
2.  It looks for the `tp_call` slot in that type structure.
3.  If `tp_call` is not NULL, it executes the C function pointed to by that slot.

---

### The Mechanism of the Chain

So, why does `func.__call__.__call__` work? Let’s trace the object lifecycle step-by-step.

#### 1. The Function

You start with `void`. It is an object of type function. The function type has a `tp_call` slot that points to CPython’s function execution logic.

*   **Result:** calling `void()` triggers `function_call` in C.

#### 2. The First Access

You access `void.__call__`. Python’s descriptor protocol kicks in. Since `__call__` is a method on the function object, Python returns a bound method. However, for built-in magic methods on built-in types, CPython uses a specialized object called a method-wrapper.

*   **Current Object:** `<method-wrapper ‘__call__’ of function object>`

#### 3. The Second Access

You now have a method-wrapper object. This object also has a type: `PyMethodWrapper_Type`. Crucially, this type also defines a `tp_call` slot.
When you call this wrapper (`void.__call__()`), the `tp_call` implementation of the wrapper looks at the object it wraps (our original function) and invokes its `tp_call`.

#### 4. The Infinite Recursion (That Isn’t)

Now you access `void.__call__.__call__`. You are asking for the `__call__` attribute of a method-wrapper. Because the method-wrapper is an object, it returns another method-wrapper bound to the previous wrapper.

It is mirrors reflecting mirrors. We aren’t entering a recursive stack depth in execution logic (until we actually execute); we are simply creating a chain of wrapper objects, each capable of invoking the previous one.

---

### Visualizing the Layers

Let’s write some code to inspect these layers. We will use `id()` and `type()` to prove that we are dealing with distinct objects at every step of the chain.

```python
class QuantumProcessor:
    """A callable class representing a processing unit."""
    
    def __init__(self, name: str):
        self.name = name

    def __call__(self, value: int) -> int:
        return value * 42

def investigate_call_chain():
    # 1. Instantiate our callable
    qp = QuantumProcessor("Q1")
    
    # 2. Define the chain
    # Layer 0: The instance itself
    layer_0 = qp
    
    # Layer 1: The Bound Method (Accessing qp.__call__)
    # This creates a new 'method' object bound to qp
    layer_1 = layer_0.__call__
    
    # Layer 2: The Method Wrapper
    # This accesses layer_1.__call__. Since layer_1 is a built-in type (method),
    # CPython returns a 'method-wrapper' bound to layer_1.
    layer_2 = layer_1.__call__
    
    # Layer 3: The Wrapper of the Wrapper
    # This accesses layer_2.__call__. layer_2 is a method-wrapper,
    # so we get ANOTHER method-wrapper bound to layer_2.
    layer_3 = layer_2.__call__

    # 3. Output Types
    print(f"{'Layer':<10} | {'Type':<25} | {'Description'}")
    print("-" * 65)
    
    print(f"{'0':<10} | {type(layer_0).__name__:<25} | Instance of QuantumProcessor")
    print(f"{'1':<10} | {type(layer_1).__name__:<25} | Bound Method (wraps Layer 0)")
    print(f"{'2':<10} | {type(layer_2).__name__:<25} | Method Wrapper (wraps Layer 1)")
    print(f"{'3':<10} | {type(layer_3).__name__:<25} | Method Wrapper (wraps Layer 2)")

    # 4. Prove the Chain Structure
    print("\n--- The Ouroboros Verification ---")
    
    # Check 1: Are they the same object? (Should be False)
    # A method and its wrapper are distinct structures in memory.
    is_same = layer_1 is layer_2
    print(f"Is Layer 1 same object as Layer 2? {is_same}")
    
    # Check 2: Does Layer 1 wrap Layer 0? (Standard bound method behavior)
    # Note: User-defined bound methods use __self__ to point to the instance.
    wraps_0 = layer_1.__self__ is layer_0
    print(f"Does Layer 1 wrap Layer 0?       {wraps_0}")

    # Check 3: Does Layer 2 wrap Layer 1? (The Infinite Chain start)
    # The wrapper's job is to hold layer_1 and invoke its tp_call.
    wraps_1 = layer_2.__self__ is layer_1
    print(f"Does Layer 2 wrap Layer 1?       {wraps_1}")
    
    # Check 4: Does Layer 3 wrap Layer 2?
    wraps_2 = layer_3.__self__ is layer_2
    print(f"Does Layer 3 wrap Layer 2?       {wraps_2}")

    # 5. Execution
    print("\n--- Execution ---")
    # Calling the top of the chain should ripple down to the bottom
    result = layer_3(2) 
    print(f"layer_3(2) result: {result}")

if __name__ == "__main__":
    investigate_call_chain()
```

When you run this script, you will see `True` for all the “wraps” checks. This confirms the architectural implication:

1.  **Layer 1** is a method object. It holds `qp` in `__self__`.
2.  **Layer 2** is a method-wrapper. It holds **Layer 1** in `__self__`.
3.  **Layer 3** is another method-wrapper. It holds **Layer 2** in `__self__`.

The “Infinite Loop” is actually an Infinite Linked List of wrappers, constructed dynamically as you access the attributes. No stack overflow occurs during access — only during execution if you somehow managed to create a cycle (which CPython prevents here by simply wrapping the previous object linearly).

---

### The Cost of Abstraction

While it is elegant architecturally, using explicit `__call__` chains incurs performance penalties.

*   Each dot (`.`) in Python triggers an attribute lookup (`getattribute`).
*   Each parenthesis `()` triggers a call.

**Direct Call `obj()`:**

*   **Opcode:** `CALL_FUNCTION`
*   **Cost:** Checks `tp_call`. Jumps to C function. Fast.

**Explicit Call `obj.__call__()`:**

*   **Opcode:** `LOAD_ATTR (__call__)` -> `CALL_FUNCTION`
*   **Cost:** `LOAD_ATTR` must search the object’s dictionary or MRO (Method Resolution Order). Then it creates a method object (allocation). Then it calls that object.
*   **Result:** Significantly slower (often 2x overhead for simple functions).

**Chained Call `obj.__call__.__call__()`:**

*   **Cost:** Two `LOAD_ATTR` lookups, two allocations of wrapper objects, then the execution chain.

In high-throughput systems (like inner loops of a web server or a data processing pipeline), explicitly calling magic methods is a performance anti-pattern. Always rely on the operator `()` which allows CPython to take the “fast path” via the `tp_call` slot.

---

### When is `__call__` Useful?

If calling `__call__` explicitly is slow and verbose, why do we care about this mechanics?

The power lies in **Callable Objects** as a replacement for single-method interfaces (like the Strategy or Command patterns mentioned in design pattern literature).

Because Python treats functions and objects uniformly via `__call__`, we can swap out a simple function for a complex class instance without changing the client code. This is known as the **Uniform Access Principle**.

---

### From Function to Stateful Callable

Imagine a system that processes payments. Initially, you use a simple function.

```python
from decimal import Decimal

# Phase 1: Simple Function
def process_payment(amount: Decimal) -> bool:
    print(f"Processing ${amount}...")
    return True

# Client Code
def checkout(payment_strategy):
    payment_strategy(Decimal("100.00"))

checkout(process_payment)
```

Later, you realize you need to track how many payments have been processed and enforce a limit. In Java, you might need to refactor `process_payment` into a `PaymentProcessor` interface and change the `checkout` signature. In Python, you simply create a class with `__call__`.

```python
from dataclasses import dataclass
from decimal import Decimal


# Phase 1: Simple Function
def process_payment(amount: Decimal) -> bool:
    print(f"Processing ${amount}...")
    return True


# Client Code
def checkout(payment_strategy):
    payment_strategy(Decimal("100.00"))


checkout(process_payment)


# Phase 2: Stateful Class
@dataclass
class RateLimitedProcessor:
    limit: int
    _count: int = 0

    def __call__(self, amount: Decimal) -> bool:
        if self._count >= self.limit:
            print("Limit reached!")
            return False

        self._count += 1
        print(f"Processing ${amount} (Transaction {self._count})")
        return True


# Client code remains EXACTLY the same
safe_processor = RateLimitedProcessor(limit=3)
checkout(safe_processor)
```

This works specifically because `safe_processor` satisfies the Callable protocol. The `checkout` function blindly calls `()`, and CPython’s `tp_call` slot handles the dispatch, whether it points to a raw function or a class instance.

---

### Conclusion

The fact that `func.__call__.__call__` is valid syntax is more than a party trick. It is a testament to Python’s rigorous adherence to its “everything is an object” philosophy.

By exposing the execution logic (`tp_call`) as a standard attribute (`__call__`), Python bridges the gap between the interpreter’s internal mechanics and the developer’s high-level code. While we shouldn’t use these chains in production code due to the overhead of attribute lookups and wrapper allocation, understanding them demystifies how Python executes code.

It reminds us that in Python, syntax is often just sugar over a consistent, dynamic object model. Whether you are running a function, a method, or a complex callable class, you are ultimately just asking a C-struct to invoke its `tp_call` pointer.
