# Python is Not Java: The Cost of Semantic Imitation
#### Unlearning the “Kingdom of Nouns”: Why First-Class Functions Render Traditional Design Patterns Obsolete

**By Tihomir Manushev**  
*Jan 2, 2026 · 7 min read*

---

When developers migrate to Python from statically typed, strictly object-oriented languages like Java or C#, they often bring more than just their algorithmic knowledge — they bring their architectural muscle memory. They bring the Gang of Four (GoF) design patterns, the rigid class hierarchies, and the instinct that “everything must be an object.”

While Python is indeed object-oriented, it is also multi-paradigm. It supports procedural, functional, and object-oriented styles with equal fluency. The friction arises when we attempt to force-fit Java semantics into Python syntax. This practice, often called “Java-thon,” results in code that is syntactically correct but semantically inefficient — bloated with boilerplate, heavy on memory usage, and cognitively dissonant to the underlying mechanisms of the CPython interpreter.

In this article, we will dissect the hidden costs of semantic imitation. We will look at why blindly implementing patterns like Strategy or Command using class hierarchies is an anti-pattern in Python, and how understanding Python’s first-class functions can lead to cleaner, faster, and more robust systems.

---

### The Kingdom of Nouns vs. The Power of Verbs

In languages like Java (pre-lambda) or C++, behavior must be attached to data. If you want to pass a function around, you wrap it in a class. This leads to the “Kingdom of Nouns,” where execution is buried under layers of `AbstractFactory`, `impl` packages, and `execute()` methods.

Python is different. In Python, functions are first-class objects. This is not just a syntactic convenience; it is a fundamental property of the Python data model. A function in Python is an instance of the function class. It can be assigned to a variable, passed as an argument, returned from other functions, and even stored in data structures like lists or dictionaries.

When we ignore this and wrap behavior in single-method classes, we incur two distinct costs:

1.  **The Runtime Cost:** Creating a class instance involves allocating memory for the object and its `__dict__` (unless `__slots__` is used), and invoking a method involves a descriptor protocol lookup to bind the function to the instance.
2.  **The Cognitive Cost:** We force readers to parse a class structure when a simple importable function would have sufficed.

Let’s examine this through the lens of the Strategy Pattern.

---

### The Text Sanitizer

Imagine we are building a system to sanitize user comments on a social platform. We need different filtering strategies: removing URLs, masking profanity, or normalizing whitespace.

---

#### The “Java-thon” Approach

A developer trained in the classic object-oriented tradition would likely define an interface (Abstract Base Class) and implement concrete strategies as subclasses.

```python
from abc import ABC, abstractmethod

# The Interface
class TextFilterStrategy(ABC):
    @abstractmethod
    def apply(self, text: str) -> str:
        """Apply the filter to the text."""
        pass

# Concrete Strategy 1
class UrlRemover(TextFilterStrategy):
    def apply(self, text: str) -> str:
        # A simple mock implementation for demonstration
        words = []
        for word in text.split():
            if not word.startswith("http"):
                words.append(word)
        return " ".join(words)

# Concrete Strategy 2
class ProfanityMasker(TextFilterStrategy):
    def apply(self, text: str) -> str:
        bad_words = {"archaic", "cobol"}
        words = [
            "****" if word.lower() in bad_words else word 
            for word in text.split()
        ]
        return " ".join(words)

# The Context
class CommentSanitizer:
    def __init__(self, strategies: list[TextFilterStrategy]):
        self._strategies = strategies

    def clean(self, text: str) -> str:
        for strategy in self._strategies:
            text = strategy.apply(text)
        return text

# Usage
sanitizer = CommentSanitizer([UrlRemover(), ProfanityMasker()])
result = sanitizer.clean("Do not use archaic COBOL code here http://example.com")
print(result) 
```

Does this code work? Yes. Is it “good” Python? No.

Analyze the `UrlRemover` and `ProfanityMasker` classes. They have no state. They have no `__init__`. They exist solely to host the `apply` method. In Python terms, these are namespaced functions pretending to be objects.

When `sanitizer.clean` runs, Python must:

1.  Access the strategy object.
2.  Look up the `apply` attribute.
3.  The attribute lookup triggers the descriptor protocol (because `apply` is a method), binding the function to the instance.
4.  Finally, execute the code.

We have built a Rube Goldberg machine to call a function.

### The Pythonic Approach: First-Class Functions

In Python, the Strategy pattern often evaporates into simple function passing. We don’t need a `TextFilterStrategy` class because the callable interface is inherent to functions. Any function that matches the signature `(str) -> str` is a strategy.

Here is the refactored, idiomatic version:

```python
from typing import Callable, Iterable

# Type Alias for clarity (Python 3.10+)
FilterFunc = Callable[[str], str]

# Concrete Strategies are just functions
def remove_urls(text: str) -> str:
    """Removes any token starting with http."""
    return " ".join(w for w in text.split() if not w.startswith("http"))

def mask_profanity(text: str) -> str:
    """Masks specific forbidden words."""
    bad_words = {"archaic", "cobol"}
    return " ".join(
        "****" if w.lower() in bad_words else w 
        for w in text.split()
    
    )

# The Context
class CommentSanitizer:
    def __init__(self, filters: Iterable[FilterFunc]):
        self._filters = filters

    def clean(self, text: str) -> str:
        for filter_func in self._filters:
            # Direct execution, no attribute lookup or method binding overhead
            text = filter_func(text)
        return text

# Usage
# Note: We pass the functions directly, we do not instantiate them.
sanitizer = CommentSanitizer([remove_urls, mask_profanity])
result = sanitizer.clean("Do not use archaic COBOL code here http://example.com")
print(result)
```

#### Technical Analysis of the Refactoring

1.  **Memory Efficiency (The Flyweight Effect):** In the Class-based approach, if we had 1,000 different `CommentSanitizer` instances, and we instantiated new `UrlRemover()` objects for each, we would be creating thousands of redundant objects. In the functional approach, `remove_urls` is defined once at module load time. It is a singleton. It acts as a natural Flyweight. We pass a reference to the existing code object, consuming virtually no extra memory.
2.  **Reduction of Indirection:** The loop `text = filter_func(text)` involves loading a local variable and calling it. There is no `LOAD_ATTR` (to find `apply`) and no method binding overhead. While method lookup is fast in Python, it is not free. In tight loops, these micro-optimizations compound.
3.  **Simplicity:** We deleted the ABC and the classes. We reduced the lines of code (LOC) significantly while increasing readability.

---

### Handling State: The Closure vs. The Class

A common counter-argument is: “What if my strategy needs state? What if the `ProfanityMasker` needs to load a dictionary from a database?”

The Java reflex is: “Pass the database connection to the Constructor.”
The Python reflex offers two choices: Closures or Callables.

If the state is simple, a closure (often via a decorator or a factory function) is elegant.

```python
def make_profanity_filter(blocked_words: set[str]) -> FilterFunc:
    def _filter(text: str) -> str:
        return " ".join(
            "****" if w.lower() in blocked_words else w 
            for w in text.split()
        )
    return _filter

# Usage
# db_words = query_database(...)
custom_filter = make_profanity_filter({"java", "xml"})
```

Here, `custom_filter` holds `blocked_words` in its `__closure__` attribute. It is self-contained.

However, if the state is complex, mutable, or requires lifecycle management (like opening/closing files), this is where classes return to the stage. But we implement them as Callables.

```python
class FileBasedProfanityFilter:
    def __init__(self, filepath: str):
        with open(filepath, 'r') as f:
            self.bad_words = set(f.read().splitlines())

    def __call__(self, text: str) -> str:
        return " ".join(
            "****" if w.lower() in self.bad_words else w 
            for w in text.split()
        )
```

By implementing `__call__`, this class instance looks and acts exactly like our functions `remove_urls` and `mask_profanity`. The `CommentSanitizer` doesn’t need to change a single line of code. It expects a `Callable[[str], str]`, and `FileBasedProfanityFilter` satisfies that contract structurally.

---

### Introspection and Discovery

One of the most powerful features of Python is that modules are objects, and we can inspect them at runtime. This allows us to avoid the “Registry” boilerplate often seen in other languages.

In Java, adding a new strategy might require updating a Factory class or an Enum. In Python, we can dynamically discover strategies.

Suppose all our filter functions are defined in a module named `filters.py`. We can automatically load them using `inspect`.

```python
import inspect
import filters  # Our module containing filter functions

FilterFunc = Callable[[str], str]

def get_all_strategies() -> list[FilterFunc]:
    strategies = []
    for name, obj in inspect.getmembers(filters):
        # We can enforce a naming convention or check type signatures
        if inspect.isfunction(obj) and name.startswith("strategy_"):
            strategies.append(obj)
    return strategies
```

This dynamic nature allows for “Convention over Configuration.” By simply adhering to a naming convention (e.g., `strategy_remove_urls`), a developer can add a new feature to the system without ever touching the core `CommentSanitizer` code.

---

### Conclusion

When we mimic Java or C++ in Python, we are effectively fighting the language. We are building explicit structures to emulate behavior that is already implicit in Python’s data model. The result is code that is harder to read, heavier on memory, and slower to execute.

To master Python is to unlearn the rigidity of the “Kingdom of Nouns.” It is to embrace functions as first-class citizens, to understand that closures can replace private variables, and to realize that sometimes, the best implementation of a Strategy pattern is just a list of functions.

Write Python that looks like Python, not like translated Java. Your RAM, your CPU, and your fellow developers will thank you.
