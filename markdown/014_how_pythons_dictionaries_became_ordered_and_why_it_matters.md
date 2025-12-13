# How Python’s Dictionaries Became Ordered (And Why It Matters)
#### Python’s core data structure got a major upgrade, not as a planned feature, but as a happy accident of optimization

**By Tihomir Manushev**  
*Oct 28, 2025 · 7 min read*

---

For years, we Pythonistas lived by a sacred rule, one of the first things taught after “Hello, World!” and list slicing: “Dictionaries are unordered.”

It was a fundamental truth of the language. When you created a dictionary, you were making a deal. You’d get incredibly fast lookups by key, but you’d sacrifice any sense of order. The sequence in which you inserted items was not the sequence you’d get back when you iterated over them.

If you needed order, you reached for a specialist: `collections.OrderedDict`. It did the job, but it felt like a workaround, an admission that the built-in dict had a limitation.

Then, around 2016, something strange started happening. Developers using the new CPython 3.6 started noticing that their dictionaries… were keeping their order. Was it a fluke? A temporary side effect? A bug?

It turned out to be none of those. It was the beginning of a quiet revolution. That implementation detail in CPython 3.6 became an official, guaranteed language feature in Python 3.7. The sacred rule was broken. Dictionaries are now, officially, ordered.

But how did this happen? And more importantly, why was this change made, and what does it mean for the code you write every day? The story is a fascinating tale of a quest for performance that resulted in a happy accident of usability.

---

### The “Why”: A Quest for a Better, Faster Dictionary

The change wasn’t initially about preserving order. The primary motivation was to make dictionaries smaller and faster. The credit for this innovation goes to Python core developer Raymond Hettinger, who reimagined the internal structure of the dict.

Before Python 3.6, the standard CPython dictionary was implemented using a classic hash table. Here’s a simplified idea of how it worked:

1.  A block of memory was allocated for an array, which was often sparse (meaning many of its slots were empty).
2.  When you inserted a key-value pair, Python would hash the key to calculate an index in that array.
3.  The key’s hash, the key object itself, and the value object were all stored at that index.
4.  If two keys hashed to the same index (a “hash collision”), a process called “probing” would find the next available empty slot.

This design was fast for lookups, but it had a downside: the order was chaotic. Because the final position of an item depended on the hash value and the history of collisions, the insertion order was lost. Furthermore, whenever a dictionary needed to grow, it would create a new, larger table and re-insert all the items, completely scrambling the order all over again.

This sparse table also wasted memory. Raymond Hettinger’s proposal, which was first implemented in PyPy, introduced the “compact dictionary.”

---

### The “How”: A Tale of Two Arrays

The new dictionary design is a brilliant solution that saves memory and, as a side effect, preserves order. It works by splitting the dictionary’s storage into two separate parts.

Let’s pop the hood for a moment.

1.  **The Indices Array:** This is a dense hash table that stores only the indices. When you look up a key, it’s hashed, and Python finds its position in this array. This part can be sparse and is used for the fast lookup magic.
2.  **The Entries Array:** This is a separate, compact array that stores the actual key-value pairs (along with the key’s hash). When you add a new item to the dictionary, it’s simply appended to the end of this entries array.

This is the secret sauce! The indices array just stores a pointer to the item’s position in the entries array. Because items are always appended to the entries array, their insertion order is naturally preserved.

Let’s visualize it. Imagine you build a dictionary like this:

```python
my_dict = {
    'name': 'Alice',
    'age': 30,
    'city': 'New York'
}
```

**Old dict (Pre-3.6):** A single, sparse table. `age` might end up before `name` due to its hash value.

```python
# One big, sparse table. Order is unpredictable.
[
  (hash('age'), 'age', 30),
  --empty--,
  (hash('name'), 'name', 'Alice'),
  --empty--,
  --empty--,
  (hash('city'), 'city', 'New York'),
  ...
]
```

**New dict (3.6+):** Two separate structures.

```python
# Structure 1: Indices (for fast lookups)
# Hashing 'name' leads us to index 0 in the entries array.
# Hashing 'age' leads us to index 1 in the entries array.
# ...and so on.

# Structure 2: Entries (compact and ordered)
[
  (hash('name'), 'name', 'Alice'),    # Appended first
  (hash('age'), 'age', 30),           # Appended second
  (hash('city'), 'city', 'New York')  # Appended third
]
```

When you iterate over the dictionary, Python simply walks through the dense entries array from beginning to end, giving you the items in the exact order you inserted them. This design uses 20–25% less memory than the old dictionary implementation — a massive win that also gave us one of the most requested language features for free.

---

### Why This Matters: The Practical Impact on Your Code
#### 1. Predictable Keyword Arguments (**kwargs)

This isn’t just a piece of academic trivia. Ordered dictionaries have a tangible, positive impact on day-to-day Python programming.

Before, you could never be sure of the order in which `**kwargs` would arrive in a function. Now, you can. This is incredibly useful for functions that perform a sequence of operations based on their arguments.

```python
def process_steps(**steps):
    print("Executing steps in order:")
    for step_name, action in steps.items():
        print(f"-> {step_name}: {action}")
        # Imagine performing the action here
        
process_steps(
    step_1='Validate Data',
    step_2='Connect to Database',
    step_3='Process Records',
    step_4='Generate Report'
)
```

This code is now guaranteed to work as expected. The steps will always be executed in the order they were provided in the function call.

#### 2. Data Interchange and Configuration

When you load data from a format like JSON or YAML, the order of keys in the source file is often meaningful to a human reader. With ordered dicts, that structure is preserved when you load it into Python.

```python
import json

# Imagine this JSON comes from a config file or API response
# The order of fields might be structured for human readability
json_data = """
{
  "id": "user123",
  "name": "Bob",
  "email": "bob@example.com",
  "preferences": {
    "theme": "dark",
    "notifications": true
  }
}
"""

data = json.loads(json_data)

# Printing the dictionary now reflects the original order
for key, value in data.items():
    print(f"{key}: {value}")
```

This makes debugging and logging far more intuitive, as the printed representation of your data structures matches the source.

---

### So, Is collections.OrderedDict Dead?

With the built-in dict now ordered, is there any reason to use `collections.OrderedDict` anymore?

The answer is yes, but for very specific niche cases. `OrderedDict` is not obsolete, but its role has changed from “the only way to get order” to “a specialist tool for order-based logic.”

Here are the key differences that still make `OrderedDict` relevant:

#### 1. Equality Comparison

This is the most important distinction. A regular dict purposefully ignores item order when checking for equality. An `OrderedDict` considers order to be crucial.

```python
from collections import OrderedDict

d1 = {'a': 1, 'b': 2}
d2 = {'b': 2, 'a': 1}

# Regular dicts care only about content, not order
print(f"dict == dict: {d1 == d2}") # True

od1 = OrderedDict([('a', 1), ('b', 2)])
od2 = OrderedDict([('b', 2), ('a', 1)])

# OrderedDicts care about order
print(f"OrderedDict == OrderedDict: {od1 == od2}") # False
```

If your logic depends on two dictionaries being identical including their order, you still need `OrderedDict`.

#### 2. Specialized Methods

`OrderedDict` comes with methods designed specifically for reordering elements, which are not available on the standard dict. The most notable is `move_to_end(key, last=True)`.

This is perfect for algorithms like implementing an LRU (Least Recently Used) cache, where you move an item to the end every time it’s accessed.

```python
from collections import OrderedDict

cache = OrderedDict.fromkeys(['a', 'b', 'c', 'd']) # A simple set-like OrderedDict

# Access 'c'
cache.move_to_end('c')

print(list(cache.keys())) # ['a', 'b', 'd', 'c']
```

#### 3. Backward Compatibility

If you are writing a library that needs to support Python versions older than 3.7, you cannot rely on the built-in dict’s ordering. In that case, using `OrderedDict` is the only way to guarantee consistent behavior for all of your users.

---

### Conclusion

The evolution of Python’s dictionary is a perfect example of how the language grows. It was a change driven by a deep-seated need for efficiency that produced an elegant improvement in usability.

We no longer have to explain the “dictionaries are unordered” caveat to newcomers with the same urgency. The most-used data structure in the language now works in a way that is more intuitive, predictable, and delightful to use. And it all happened because someone wanted to save a little memory.