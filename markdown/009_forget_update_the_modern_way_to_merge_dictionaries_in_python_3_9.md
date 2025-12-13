# Forget .update(): The Modern Way to Merge Dictionaries in Python 3.9+
#### How Python 3.9’s union operators (| and |=) create a more readable, intuitive, and safer way to combine dictionaries.**

**By Tihomir Manushev**  
*Oct 21, 2025 · 7 min read*

---

Merging dictionaries is one of those tasks that feels like a rite of passage for a Python developer. You do it when you’re combining configuration settings, aggregating data, or just wrestling with JSON APIs. For years, we had our trusty tools: the classic `.update()` method and the slick, modern `**` unpacking syntax. They worked. They got the job done.

But “good enough” isn’t the Python way. The language constantly evolves toward more expressive, readable, and elegant solutions. In 2020, with the release of Python 3.9, a new and beautiful syntax for merging dictionaries arrived, and it’s time you made it your default.

PEP 584 introduced the union operators (`|` and `|=`) for dictionaries. Borrowing a familiar concept from sets, these operators provide an incredibly intuitive and clean way to handle one of our most common data manipulation tasks. This isn’t just a minor tweak; it’s a fundamental improvement to the language’s user interface.

Let’s take a journey from the old ways to the new, see why this change is so significant, and understand how you can write cleaner, more intentional code today.

---

### The Old Guard: A Trip Down Memory Lane

To appreciate where we are, we need to remember where we came from. There have been several ways to merge dictionaries over the years, each with its own quirks and style.

#### Method 1: The Trusty .update()

This is the classic. If you’ve been writing Python for more than a few years, `.update()` is probably baked into your muscle memory. It’s an in-place method, meaning it modifies the dictionary it’s called on.

Let’s say we’re managing default settings for an application and want to override them with some user-provided values.

```python
# Default application settings
default_settings = {
    'theme': 'dark',
    'font_size': 12,
    'show_toolbar': True
}

# User's custom settings from a config file
user_settings = {
    'font_size': 14,
    'language': 'en'
}

# Let's merge them
merged_settings = default_settings.copy() # We have to copy first!
merged_settings.update(user_settings)

print(merged_settings)
```

Notice the key behaviors of `.update()`:

*   **It’s an in-place operation.** It modifies the original dictionary. This is why we had to create a `copy()` of `default_settings` first. If we hadn’t, we would have permanently altered our defaults, which could be a nasty bug waiting to happen.
*   **It returns None.** You cannot chain it or use it in an assignment to get the result. `new_dict = d1.update(d2)` will leave you with `new_dict` being `None`.
*   **Last-in wins.** When keys conflict (like `font_size`), the value from the dictionary passed into `.update()` overwrites the original.

`.update()` is explicit and it works, but that extra `copy()` step is easy to forget and can lead to unintended side effects.

#### Method 2: The Elegant Unpacking (**)

Introduced in Python 3.5 via PEP 448, dictionary unpacking felt like a revelation. It gave us a concise, functional way to create a new merged dictionary in a single, readable line.

Using our same settings example:

```python
# Default application settings
default_settings = {
    'theme': 'dark',
    'font_size': 12,
    'show_toolbar': True
}

# User's custom settings
user_settings = {
    'font_size': 14,
    'language': 'en'
}

# Merge using dictionary unpacking
merged_settings = {**default_settings, **user_settings}

print(merged_settings)
```

This was a huge step forward.

*   **It creates a new dictionary.** The original `default_settings` and `user_settings` are left untouched. This is generally much safer and leads to fewer surprises.
*   **The syntax is declarative.** You’re describing the contents of the new dictionary literal by “spreading” or “unpacking” the contents of the others into it.
*   **Last-in still wins.** The order matters. The rightmost dictionary’s values for any duplicate keys will be the ones that end up in the final result.

For a few years, this was the gold standard for creating a new merged dictionary. But the syntax, while clever, is more about the mechanics of building a dict than the intent of merging two.

---

### The New Era: The Beautiful Union Operators

This brings us to Python 3.9. The core developers recognized that merging is a fundamental operation, much like the union of two sets. So why not use the same operator?

#### The Merge Operator: |

The pipe operator (`|`) is the modern equivalent of the `**` unpacking method. It performs a union and creates a new dictionary.

Let’s see it in action:

```python
# Default application settings
default_settings = {
    'theme': 'dark',
    'font_size': 12,
    'show_toolbar': True
}

# User's custom settings
user_settings = {
    'font_size': 14,
    'language': 'en'
}

# The modern, Python 3.9+ way
merged_settings = default_settings | user_settings

print(merged_settings)
```

Look how clean that is! `d1 | d2` is a crystal-clear expression of intent: “Give me the union of d1 and d2.”

Its behavior mirrors the `**` unpacking method, which is great for consistency:

*   **It creates a new dictionary.** Originals are preserved.
*   **Last-in wins.** The right-hand operand’s values take precedence in case of key collisions. `user_settings` overwrites the `font_size` from `default_settings`.

This syntax is not just shorter; it’s more semantically correct. It elevates the operation from a trick of syntax to a first-class feature of the dictionary type.

#### The In-Place Merge Operator: |=

What about our old friend `.update()`? Does it have a modern equivalent? Absolutely. The `|=` operator is the new in-place merge.

This is the perfect tool when you explicitly want to modify a dictionary. For example, if you’re building up a dictionary of results within a loop.

```python
from collections import ChainMap

# Let's imagine we have a baseline config and a command-line override config
baseline = {'user': 'admin', 'retries': 3}
overrides = {'retries': 5, 'timeout': 30}

# Update the baseline config in-place with the overrides
baseline |= overrides

print(baseline)
# Output: {'user': 'admin', 'retries': 5, 'timeout': 30}
```

Here, `baseline |= overrides` does the exact same thing as `baseline.update(overrides)`. It modifies `baseline` directly.

The choice between the two is now largely a matter of style, but `|=` aligns with Python’s other in-place operators (`+=`, `-=`, etc.), making the language feel more consistent and coherent.

---

### Why This Is More Than Just Syntactic Sugar

It’s easy to dismiss these new operators as mere “syntactic sugar” — a fancy new way to write something we could already do. But that view misses the point. The syntax of a language is its user interface. A better UI makes for a better developer experience and, ultimately, better code.

*   **Readability and Intent:** `d1 | d2` reads like a statement of fact: “the result is the union of d1 and d2.” In contrast, `{**d1, **d2}` reads like a set of instructions: “create a new dictionary, then unpack d1 into it, then unpack d2 into it.” The former describes what you want, while the latter describes how to get it. Good code emphasizes the *what* over the *how*.
*   **Consistency:** By using operators already familiar from sets, the language becomes more consistent. An operation that feels like a “union” now looks like a union, whether you’re working with sets or dictionaries. This reduces the cognitive load on developers — you have fewer distinct patterns to remember.
*   **Avoiding Side Effects:** By making the non-in-place merge operator (`|`) so clean and prominent, the language subtly encourages safer programming practices. Creating new objects instead of mutating existing ones is a core tenet of functional programming and can eliminate a whole class of bugs related to shared, mutable state.

---

### A Quick Note on Compatibility and Types

The only real “catch” is that these operators are exclusive to Python 3.9 and newer versions. If you’re writing code that needs to run on older versions like Python 3.8 (which is still very common in production environments), you’ll have to stick with `.update()` and `**` unpacking.

It’s also worth noting that these operators work with any mapping types that support them, not just the basic `dict`. This includes `collections.OrderedDict` and `collections.defaultdict`. The type of the resulting dictionary is determined by the type of the left-hand operand.

```python
from collections import defaultdict

d1 = defaultdict(int, {'a': 1, 'b': 2})
d2 = {'b': 3, 'c': 4}

merged = d1 | d2
print(merged)
# Output: defaultdict(<class 'int'>, {'a': 1, 'b': 3, 'c': 4})
print(type(merged))
# Output: <class 'collections.defaultdict'>
```

---

### Conclusion

The evolution of dictionary merging in Python is a perfect example of the language’s philosophy of continuous improvement. We moved from the imperative `.update()` to the clever `**` unpacking, and now we’ve arrived at the clear and intentional `|` and `|=` operators.

For developers working in a modern Python 3.9+ environment, the choice is clear. Reach for the union operators first. They make your code more readable, more expressive, and more aligned with the modern idioms of the language. They turn a chore into an elegant expression of logic.

Simple and correct. That’s the Python way.