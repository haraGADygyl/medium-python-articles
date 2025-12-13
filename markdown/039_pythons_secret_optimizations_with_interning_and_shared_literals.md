# Python’s Secret Optimizations with Interning and Shared Literals
#### Why 42 is 42, but 9000 is not 9000: A deep dive into Python’s memory management and object recycling

**By Tihomir Manushev**  
*Nov 24, 2025 · 10 min read*

---

If you spend enough time debugging Python code, you eventually hit a moment that makes you question your sanity. You learned early on that every time you create an object, it takes up a new space in memory. You learned that variables are just labels pointing to these objects.

So, you write a simple test. You create two separate strings. You check if they are the same object. They are. You try it again with two integers. They are the same object. You try it with a larger integer. Suddenly, they are different objects.

Welcome to the Twilight Zone of Python optimization.

While Python is often criticized for being “slow” compared to compiled languages like C or Rust, the CPython interpreter (the standard Python we all use) is actually packed with clever tricks to save memory and speed up execution. These tricks, specifically interning and shared literals, involve the interpreter silently reusing objects behind your back.

Understanding these behaviors won’t just help you win trivia bets at your next hackathon; it will save you from writing subtle, dangerous bugs involving object identity.

---

### The Identity Crisis: is vs ==

Before we crack open the interpreter, we must solidify the difference between equality and identity. This is the stage upon which these optimizations perform their magic.

*   **Equality (`==`):** Checks if the values of two objects are the same. (Do these two boxes contain the same cake?)
*   **Identity (`is`):** Checks if the memory address of two objects is the same. (Are we pointing to the exact same physical box?)

Usually, when you assign values to two different variables, you expect two different objects:

```python
list_a = [10, 20, 30]
list_b = [10, 20, 30]

print(list_a == list_b) # True: The values match
print(list_a is list_b) # False: They are two distinct lists in memory  
```

This makes sense. But when we move to immutable types — specifically numbers and strings — Python starts breaking the rules to help us out.

---

### The Secret Life of Small Integers

Let’s look at a phenomenon that often confuses beginners. We will create two variables with the value 42, and two variables with the value 9000.

Depending on how you run this code (in a script, an IDE, or line-by-line in a terminal), you might get conflicting results. Let’s look at why.

```python
# The Small Integer Test

# Part 1: The "Small" Ints
x = 42
y = 42
print(f"42 is 42? {x is y}") # True (Always)

# Part 2: The "Large" Ints
a = 9000
b = 9000
print(f"9000 is 9000? {a is b}") # True (Sometimes!)

# Part 3: The Reality Check
c = 9000
d = int("9000") # Created at runtime
print(f"Runtime 9000 is 9000? {c is d}") # False (The Truth)
```

If you ran this from a file or a modern IDE, `a is b` likely returned `True`. Does this mean 9000 is interned just like 42? No.

You are witnessing a clash between two different optimizations: Global Caching vs. Compiler Optimization.

---

### Optimization 1: The Global Cache (-5 to 256)

In CPython, memory allocation has a cost. Since specific integers are used incredibly frequently (counters, return codes like 0 or -1), allocating a new object every time you type 0 or 1 is wasteful.

To solve this, CPython pre-allocates a specific range of integers when the interpreter starts up. This range is usually -5 to 256.

These numbers are global singletons. They exist in memory from the moment Python boots up. Anytime your code computes a value within this range, Python hands you a reference to the existing object. This is why `x is y` is always `True`.

---

### Optimization 2: Constant Coalescing

So why did `a` and `b` (the 9000s) return `True`?

When you execute a block of code (like a script file or a cell in a notebook), the Python compiler analyzes the whole block at once. It notices that the literal 9000 appears twice. To save memory, it creates one object for 9000 inside that specific code block and points both `a` and `b` to it.

However, this is a local convenience, not a global rule.

To see the illusion break, look at Part 3 of the code above. We assigned `c = 9000`, but we created `d` by converting a string (`int(“9000”)`). Because `d` was created during execution (runtime) rather than compiled as a literal, the compiler couldn’t optimize it. Python had to create a new object.

Since 9000 is outside the global cache range (-5 to 256), the interpreter didn’t fetch a pre-existing singleton. It allocated a fresh memory address. The result? `c is d` returns `False`.

**The Lesson:** The consistency of `is` for integers breaks down the moment you step outside the -5 to 256 range. Your code might work in a script (due to compiler tricks) but fail when accepting input from a user (runtime creation).

---

### String Interning: The Optimization You Didn’t Know You Needed

Strings are immutable sequences, and like integers, they can be heavy on memory. If your application processes text, you might have thousands of instances of the word “error” or “user_id”.

Python uses a technique called interning to optimize this. However, proving this works is tricky because, once again, the compiler tries to outsmart us with Constant Coalescing.

If you write this code in a script or IDE, you will likely see `True` for both cases:

```python
# The String Interning Test (Compiler Optimization)

# Scenario 1: Simple Identifiers
a = "developer"
b = "developer"
print(f"Identifiers: {a is b}")  # True

# Scenario 2: Strings with spaces or symbols
x = "hello world!"
y = "hello world!"
print(f"Non-Identifiers: {x is y}")  # True
```

In the code above, `x is y` is `True` solely because the compiler saw two identical literals in the same block and merged them. This is not string interning in the dynamic sense; it’s just the compiler saving space.

To see how Python really handles strings created during execution, we must construct them dynamically:

```python
# The Real Interning Test (Runtime Construction)

# Case A: Identifiers (Alphanumeric + Underscore)
s1 = "developer"
# Create "developer" dynamically
s2 = "".join(["dev", "eloper"]) 
print(f"Runtime Identifier: {s1 is s2}") # False

# Case B: Non-Identifiers (Spaces/Symbols)
txt1 = "hello world!"
# Create "hello world!" dynamically
txt2 = " ".join(["hello", "world!"]) 
print(f"Runtime Non-Identifier: {txt1 is txt2}") # False
```

You likely got `False` for both. This proves that Python does not automatically check every new string against its internal database to see if it already exists. Doing so for every string concatenation or join operation would be too slow.

So, when is interning actually used?

*   **Code Objects:** Variable names, function names, and string literals explicitly typed in your source code are interned when the code is loaded.
*   **Dictionaries:** Interned strings make dictionary lookups faster.

---

### Forced Interning with sys.intern

If you are processing a massive amount of data (like a generic “status” field in a database log that only ever has 5 unique values), you can force Python to intern these runtime strings. This is the only way to guarantee that a dynamically created string shares memory with an existing one.

```python
import sys

# We construct the strings dynamically
part1 = "cate"
part2 = "gory"

# Without interning, this would be a new object
dynamic_string = part1 + part2 

# With interning, we fetch the existing "category" object
tag_1 = sys.intern(dynamic_string)

# We define a literal "category" (which is automatically interned)
tag_2 = "category"

print(tag_1 is tag_2) # True
```

By explicitly calling `sys.intern()`, you force Python to register this string in its internal “singles club.” It checks: “Do I already have a ‘category’ string?”

1.  **Yes:** Discard the new object and point the variable to the old one.
2.  **No:** Store the new object and remember it for later.

This manual optimization allows you to use `is` for string comparison, turning a slow character-by-character check (O(n)) into an instant pointer check (O(1)).

---

### The Curious Case of the Immutable Tuple

We know that tuples are immutable. Once created, they cannot change. This immutability gives Python the confidence to pull off some very aggressive “lies” regarding copying.

If you have a mutable object, like a list, and you ask for a copy, Python must give you a new object. If it didn’t, modifying the copy would modify the original, leading to chaos.

```python
# Mutable List Copying
original_list = [1, 2, 3]
copy_list = list(original_list) 

print(original_list is copy_list) # False. Safe to modify copy_list.
```

However, if the object is immutable, there is no risk in sharing it. No matter what you do, you cannot change the content of a tuple. So, why waste time and memory creating a copy?

Look at what happens when we try to copy a tuple using the constructor or slicing:

```python
# Immutable Tuple "Copying"
my_tuple = (10, 20, 30)

# Method 1: Slicing
slice_copy = my_tuple[:]

# Method 2: Constructor
cons_copy = tuple(my_tuple)

print(my_tuple is slice_copy) # True
print(my_tuple is cons_copy)  # True
```

You asked for a copy, and Python handed you the original.

It’s a “harmless lie.” Since you cannot mutate `slice_copy`, you will never know that it’s actually the same object as `my_tuple` unless you check the ID. This applies to other immutable types as well, such as `frozenset`.

This optimization makes operations like `tuple(my_tuple)` essentially free. It costs zero memory and almost zero CPU time because it just returns the reference to the argument.

---

### The Empty Singleton

There is one more trick up Python’s sleeve. How many empty tuples do you need in a program? Since an empty tuple can never hold any data, one empty tuple is functionally identical to every other empty tuple.

Python enforces this strict “Singleton” pattern for empty immutable structures.

```python
t1 = ()
t2 = tuple()
t3 = (1, 2, 3)[:0] # Slicing to empty

print(t1 is t2) # True
print(t2 is t3) # True
```

Every time you create an empty tuple in your running Python application, you are pointing to the exact same memory address. The same logic applies to `frozenset()`.

---

### Why You Should Never Rely on This

These optimizations are fascinating, but they come with a massive disclaimer: **Do not program against them.**

These are “implementation details,” not language specifications. This means that while CPython 3.11 might behave this way, CPython 4.0 might not. Furthermore, other implementations like IronPython or Jython (which run on .NET and Java virtual machines, respectively) utilize their host’s garbage collectors and memory managers. They may not intern strings or integers in the same way.

The most dangerous bug you can introduce into your code is using `is` to compare values just because you saw it work once.

---

### The “is” Trap

Imagine you write a function that checks if a user’s score is a specific lucky number.

```python
# BAD CODE - DO NOT DO THIS
def check_lucky_number(score):
    # This works if score is 100
    # This FAILS if score is 1000
    if score is 1000: 
        return True
    return False
```

If you test this with 100, it works (because of small integer interning). If you deploy it and a user scores 1000, it fails, because 1000 is not interned, and the score variable will point to a different object than the literal 1000.

**The Golden Rules:**

1.  Always use `==` to check for equality of values (strings, numbers, lists).
2.  Only use `is` to check for identity with Singletons like `None`, `True`, or `False`.
3.  Use `is` if you genuinely need to know if two variables are aliases for the exact same object (e.g., checking if a default argument has been modified).

---

### Conclusion

Python’s reputation for ease of use often hides the sophisticated engineering humming beneath the surface. The interpreter is constantly making judgment calls — trading a tiny bit of CPU time during startup or object creation to save significant memory and lookup time while the program runs.

Techniques like integer caching, string interning, and the recycling of immutable objects allow Python to stay relatively lightweight, even when handling millions of objects. It treats immutable types as “values” rather than “containers,” blurring the line between the abstract concept of a number and the concrete implementation of an object.

So, the next time you see `a is b` return `True` for two distinct strings, don’t panic. It’s just Python, quietly optimizing your code in the dark.