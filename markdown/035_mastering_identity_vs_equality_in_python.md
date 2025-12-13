# Mastering Identity vs. Equality in Python
#### Unlocking the secrets of Python’s memory model to avoid invisible bugs

**By Tihomir Manushev**  
*Nov 20, 2025 · 8 min read*

---

Imagine you are standing in front of two identical houses. They are painted the exact same shade of beige, they have the same number of windows, and the manicured lawns are trimmed to the exact same height. To a casual observer, these houses are “equal.” They possess the same attributes.

However, if you have the key to House A, it will not unlock House B. They occupy different physical spaces on the street. They have different addresses. They are distinct entities.

This architectural analogy lies at the heart of one of the most common sources of confusion for Python developers: the difference between the `==` operator (Equality) and the `is` operator (Identity).

While they often seem interchangeable to beginners, confusing them can lead to subtle bugs that haunt your codebase, especially when dealing with mutable data structures or memory optimization. Let’s tear down the walls of Python’s memory model to understand when two things are actually the same thing, and when they just look alike.

---

### The Two Types of “Sameness”

In Python, every object created has three defining characteristics:

1.  **A Type:** (e.g., `int`, `list`, `dict`)
2.  **A Value:** (The data it holds, like `42` or `['apple', 'banana']`)
3.  **An Identity:** (A unique integer representing its specific location in memory).

The two operators in question strictly test different characteristics.

#### 1. The Equality Operator (==)

The double equals sign checks for equivalence of value. It asks the question: Does the data inside Object A look exactly like the data inside Object B?

When you run `a == b`, Python effectively calls the magic method `a.__eq__(b)`. It allows the objects to decide for themselves if they are equal. For a list, this means checking every element. For a dictionary, it means checking keys and values.

#### 2. The Identity Operator (is)

The `is` keyword checks for equivalence of identity. It asks the question: Are Object A and Object B actually the exact same object residing at the same memory address?

Under the hood, this compares the integer returned by the `id()` function. If `id(a)` is the same number as `id(b)`, then `a is b` returns `True`. This is a much faster operation than `==` because it doesn’t need to scan the contents of the object; it simply compares two memory pointers.

---

### Visualizing the “Sticky Note” Model

To understand this, we have to unlearn the idea that variables are “boxes” that contain data. As noted by computer science educators, a better metaphor for Python is that variables are sticky notes (labels) attached to objects.

Let’s look at a code example involving a fictional inventory system.

```python
# We create a list object in memory and stick the label 'inventory_1' to it.
inventory_1 = ["Sword", "Shield", "Potion"]

# We create a NEW, SEPARATE list object with the same data.
inventory_2 = ["Sword", "Shield", "Potion"]

# We stick a new label, 'backup_inventory', to the EXISTING object found at inventory_1.
backup_inventory = inventory_1
```

At this point, we have three variables (labels) but only two distinct list objects in memory.

*   `inventory_1` and `backup_inventory` are two labels stickied to the same object.
*   `inventory_2` is a label stickied to a different object that happens to have the same contents.

Let’s test our operators:

```python
print(f"inventory_1 == inventory_2: {inventory_1 == inventory_2}")
# Output: True
# Explanation: They contain the same strings in the same order.

print(f"inventory_1 is inventory_2: {inventory_1 is inventory_2}")
# Output: False
# Explanation: They are two different piles of RAM. 
# Changing one will NOT affect the other.

print(f"inventory_1 is backup_inventory: {inventory_1 is backup_inventory}")
# Output: True
# Explanation: They are aliases. Both labels point to the specific address.
```

If we modify the object via the `inventory_1` label, the `backup_inventory` sees the change immediately because it’s looking at the same thing. `inventory_2`, however, remains pristine.

```python
inventory_1.append("Map")

print(backup_inventory) 
# Output: ['Sword', 'Shield', 'Potion', 'Map']

print(inventory_2)
# Output: ['Sword', 'Shield', 'Potion']
```

---

### The Singleton Trap: Checking for None

If `==` checks values and is generally what we want for data, when should we strictly use `is`?

The most critical use case is checking for `None`.

In Python, `None` is a singleton. This means that in the entire lifespan of your program, exactly one `None` object exists. Any variable assigned to `None` is just pointing to that solitary object in memory.

The Pythonic way to check for null values is always:

```python
if my_variable is None:
    pass
```

And the negation:

```python
if my_variable is not None:
    pass
```

Why not use `== None`?

While `x == None` usually works, it is risky. Because `==` invokes the `__eq__` magic method, a custom class could be written in a way that lies. A developer could implement a class that returns `True` when compared to `None`, even if the object is not actually the `None` singleton.

```python
class DeceptiveBot:
    def __eq__(self, other):
        return True  # I am equal to everything!

bot = DeceptiveBot()

print(bot == None)  # True (Scary!)
print(bot is None)  # False (Safe.)
```

Using `is` bypasses the object’s custom comparison logic and checks the memory address directly. Since the `None` object has a unique address that cannot be faked, `is` is the source of truth.

---

### Sentinels: The Advanced Use Case

Another powerful use case for `is` is the creation of Sentinel Objects.

Sometimes, `None` is a valid value for a function to receive, so you can’t use it to check if a parameter was missing.

Imagine a search function where finding `None` is a valid result, but we also need to know if the user didn’t provide a default value.

```python
# We create a unique object to act as a flag. 
# object() creates a featureless, unique object in memory.
MISSING = object()

def reliable_search(target, data, default=MISSING):
    if target in data:
        return data[target]
    
    # We use 'is' because we want to know if the user specifically 
    # passed the distinct MISSING object we defined above.
    if default is MISSING:
        raise ValueError("Target not found and no default provided!")
        
    return default
```

If we used `==` here, and the user passed a custom object that evaluated to equal `MISSING` (unlikely, but possible), our logic would break. `is` guarantees we are checking for that specific marker.

---

### The Optimization Hall of Mirrors: Interning

If you play around with `is` and `==` in the interactive console, you might encounter some “spooky” behavior with numbers and strings. This often leads beginners to draw incorrect conclusions about how Python works.

```python
a = 100
b = 100
print(a is b) 
# Output: True (Wait, shouldn't these be different objects?)

x = 9999
y = 9999
print(x is y)
# Output: False (In standard CPython consoles)
```

Why did 100 return `True`, but 9999 return `False`?

This is due to an optimization technique called Interning.

Python (specifically the CPython implementation) pre-allocates a specific range of small integers (usually -5 to 256) when it starts up. These numbers are used so frequently that Python decides: “I’m not going to create a new object every time someone types the number 5. I’ll just hand them a reference to the ‘5’ I already have in the cache.”

So, `a` and `b` both point to the pre-existing, shared object for 100.

However, for larger integers (like 9999), Python usually creates new objects for each assignment (though this can vary depending on if you are running a script vs. the interactive shell, as the compiler can optimize distinct lines in a script).

**The Golden Rule:** Never, ever rely on `is` to compare integers or strings. Even if it works for small numbers, it is an implementation detail of CPython, not a language guarantee. It could change in future versions or behave differently in other implementations like PyPy or IronPython. Always use `==` for numbers and strings.

---

### Relative Immutability: When Identity Persists but Value Changes

Here is a final brain-teaser that highlights the distinction between the container’s identity and the data’s value.

Tuples are famous for being immutable. You cannot change them. But, a tuple is just a container of references (IDs). If a tuple holds a reference to a mutable object, like a list, the list can change, even if the tuple’s identity does not.

```python
# A tuple containing a number and a list
my_tuple = (42, [10, 20])
print(f"Original ID: {id(my_tuple)}")

# We cannot do this: my_tuple[0] = 99 (TypeError)

# But we CAN do this:
my_tuple[1].append(30)

print(my_tuple)
# Output: (42, [10, 20, 30])
print(f"New ID: {id(my_tuple)}")
# The ID is exactly the same.
```

The `my_tuple` object hasn’t moved in memory. Its identity is constant. It still holds the reference to the same list object. However, the value of that list has changed.

This leads to a strange paradox: `my_tuple` is still the same object (`is` returns `True`), but if we had made a copy of the original data before the append, `my_tuple == original_copy` would now be `False`.

---

### Conclusion

Python’s handling of variables is elegant, but it requires a mental shift from “boxes” to “labels.”

*   Use `==` when you care about the content. Do the objects hold the same information? (Strings, numbers, lists, data classes).
*   Use `is` when you care about the entity. Are these variables pointing to the exact same location in memory?
*   Always use `is` for `None` checks (`x is None`).
*   Beware of Interning. Don’t assume two distinct number or string assignments will have different IDs, but don’t rely on them having the same ID either.

By understanding that `==` calls a method to compare data, while `is` compares memory pointers, you can write safer, more predictable, and more “Pythonic” code.