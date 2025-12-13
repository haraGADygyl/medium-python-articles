# Stop Thinking of Python Variables as Boxes
#### Why Python variables behave differently than you think — and how to stop writing bugs because of it

**By Tihomir Manushev**  
*Nov 19, 2025 · 8 min read*

---

If you learned to program in C, C++, or Java (specifically regarding primitive types), you likely have a very specific mental model of what a variable is. You probably imagine a variable as a box.

In this “box” model, when you write `x = 10`, you are taking a box, labeling it `x`, and placing the integer `10` inside it. If you later write `y = x`, you take a new box, label it `y`, copy the value `10` from the first box, and place that copy into the `y` box. They are distinct containers. If you smash the contents of box `x`, box `y` remains pristine on the shelf.

This mental model is comfortable. It is intuitive. And in Python, it is completely wrong.

Holding onto the “box” metaphor is the root cause of many subtle bugs, particularly when dealing with lists, dictionaries, and custom objects. To truly understand Python, you must burn the box and buy a pack of sticky notes.

---

### The Reality: Objects and Labels

In Python, variables are not containers that hold data. They are merely labels (or references) attached to objects that live in the computer’s memory.

When you write an assignment statement, you aren’t putting an object into a variable. You are putting a name tag on an object.

Let’s look at a simple assignment:

```python
inventory = ["Potion", "Map", "Sword"]
```

**The Box View (Incorrect):**
You created a box named `inventory` and stuffed a list of three strings inside it.

**The Sticky Note View (Correct):**
Python created a list object in memory at a specific address (let’s say address `0x999`). It then wrote “inventory” on a sticky note and slapped it onto that list object.

This distinction seems pedantic until you introduce a second variable.

```python
backpack = inventory
```

If variables were boxes, `backpack` would be a new box containing a copy of the list. But in Python, `backpack` is just a second sticky note. You now have two notes — `inventory` and `backpack` — stuck to the exact same object at address `0x999`.

---

### Proving It With Code

We don’t have to guess about this. We can use Python’s built-in `id()` function, which acts like a serial number for objects (in CPython, it represents the memory address), and the `is` operator to prove it.

```python
# Create a list
inventory = ["Potion", "Map", "Sword"]

# Assign it to a new variable
backpack = inventory

# Check the "Serial Numbers"
print(f"ID of inventory: {id(inventory)}")
print(f"ID of backpack:  {id(backpack)}")

# Ask Python if they are the same object
print(f"Are they the same? {inventory is backpack}")
```

They are not equal copies; they are the same thing. This is called aliasing.

---

### The Aliasing Trap

Why does this matter? It matters because if you treat variables like boxes, you will assume that modifying `backpack` leaves `inventory` safe and sound. But because they are just labels on the same object, a change through one label is visible through all others.

Let’s see a disaster scenario involving a mutable object (an object that can be changed after creation), like a list.

```python
# The hero takes the map out of the backpack
backpack.remove("Map")

# The hero adds a lantern
backpack.append("Lantern")

print(f"Backpack contents: {backpack}")
print(f"Inventory contents: {inventory}")
```

If you were expecting `inventory` to still contain the Map, your code just introduced a bug. This behavior is often described as “spooky action at a distance.” You modify a variable in function A, and suddenly a variable in function B changes, because unbeknownst to you, they were both stickers on the same underlying data structure.

---

### Assignment is Binding, Not Storing

To fully internalize the sticky note metaphor, we need to look at the syntax of assignment: `variable = object`.

In many languages, assignment is treated as “store the value on the right into the memory space allocated for the variable on the left.”

In Python, assignment is binding. The Right-Hand Side (RHS) happens first. The object is created or retrieved. Only after the object exists does Python look at the Left-Hand Side (LHS) to bind the name to it.

We can prove the object is created before the assignment happens using a custom class that announces its own creation.

```python
class LoudObject:
    def __init__(self, name):
        print(f"--> LOUDOBJECT '{name}' is being created in memory!")

    def __mul__(self, other):
        # This handles the * operator
        print(f"--> Someone is trying to multiply '{self}'!")
        raise TypeError("You cannot multiply a LoudObject!")

print("Step 1: Starting assignment test...")

# We attempt to create a variable 'my_obj'
# But the multiplication will fail.
try:
    my_obj = LoudObject("Titan") * 5
except TypeError:
    print("Step 2: A TypeError occurred.")

print("Step 3: Checking if 'my_obj' exists...")
print(f"Does 'my_obj' exist? {'my_obj' in locals()}")
```

Look closely at what happened. The `LoudObject` “Titan” was created. It exists in memory; we saw the print statement. Then, Python tried to multiply it by 5. This caused a crash (exception). Because the RHS crashed, the assignment to `my_obj` never happened. The sticky note was never written, even though the object was created.

If variables were boxes waiting to be filled, `my_obj` might exist in an empty state. But because it’s a label, and the binding failed, the name `my_obj` remains undefined.

---

### Identity vs. Equality

Once you accept the sticky note metaphor, the difference between the `==` operator and the `is` operator becomes crystal clear.

*   `==` **checks for Equality:** It looks at the values of the objects. It asks, “Do these two objects contain the same data?” (e.g., are the contents of the two sticky-noted items identical?)
*   `is` **checks for Identity:** It looks at the memory address. It asks, “Are these two sticky notes attached to the exact same object?”

Let’s create two distinct lists that happen to look the same.

```python
list_a = [10, 20, 30]
list_b = [10, 20, 30]

print(f"list_a == list_b: {list_a == list_b}")
print(f"list_a is list_b: {list_a is list_b}")
```

Here, `list_a` and `list_b` are equal (same value), but they are not identical. They are two different lists living at two different memory addresses. If you modify `list_a`, `list_b` will not change. This is distinct from our earlier example where we did `backpack = inventory`.

---

### The Immutable Illusion

You might be wondering: “If this is true, why doesn’t this happen with numbers or strings?”

```python
x = 10
y = x
x = x + 5

print(f"x is {x}")
print(f"y is {y}")
```

“Aha!” you say. “It acted like a box! I changed `x`, and `y` stayed the same.”

This happens not because `x` is a box, but because integers are immutable. You cannot change the number `10`. It is a constant distinct entity in the universe of Python.

When you write `x = x + 5`, you aren’t modifying the object `10`. You are calculating `10 + 5`, creating a **new** object `15`, and moving the sticky note labeled `x` onto that new object.

The sticky note `y` is still stuck to the object `10`.

This is confusing because with lists, `list.append()` modifies the object in place. With integers, strings, and tuples, operations usually return new objects rather than changing the existing one. The variable moves to a new object; the object itself remains unchanged.

---

### Function Arguments: The Ultimate Sticky Note Test

The “variables are boxes” mental model causes the most pain when passing arguments to functions.

People often ask: “Does Python pass by value or pass by reference?” The answer is neither. It is **Call by Sharing** (or pass by assignment).

When you call a function, the function’s parameter becomes a new sticky note attached to the original object passed in.

If the object is mutable (like a list), changes made inside the function will persist outside.

```python
def add_signature(doc_list):
    # 'doc_list' is a local sticky note on the passed object
    doc_list.append("Signed: Admin")
    print(f"Inside function: {doc_list}")

my_document = ["Page 1", "Page 2"]
add_signature(my_document)

print(f"Outside function: {my_document}")
```

The `doc_list` inside the function was an alias for `my_document`.

However, if you try to reassign the variable entirely inside the function, nothing happens to the outside variable. Why? Because you are just ripping the local sticky note off the object and putting it on a new one. You aren’t touching the outsider’s sticky note.

```python
def try_to_replace(doc_list):
    # This puts the 'doc_list' label on a BRAND NEW list
    doc_list = ["This is a new list"] 
    print(f"Inside function: {doc_list}")

my_document = ["Page 1", "Page 2"]
try_to_replace(my_document)

print(f"Outside function: {my_document}")
```

Because `doc_list = …` is an assignment, it rebinds the local label. It does not overwrite the memory of the original list.

---

### Conclusion

Python is a language of references. It is a world where data floats in a massive object sea, and our variables are just tags we use to fish them out.

If you continue to visualize variables as storage boxes, you will struggle with:

1.  **Unexpected mutations:** Changing a variable here changes it there.
2.  **Memory usage:** Thinking you are copying data when you are only copying references.
3.  **Default arguments:** The classic bug where a list used as a default argument keeps growing with every function call.

Switching to the “Sticky Note” metaphor takes effort. You have to actively visualize the arrows pointing from names to objects. But once you do, the behavior of Python stops being “magic” or “weird” and starts becoming predictable and logical.

Stop storing. Start labeling.