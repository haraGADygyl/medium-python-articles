# Python’s namedtuple vs NamedTuple
#### A practical guide to choosing between collections.namedtuple and typing.NamedTuple for cleaner, more efficient code.

**By Tihomir Manushev**  
*Nov 18, 2025 · 6 min read*

---

In the ever-evolving landscape of Python, shiny new features often steal the spotlight. When Python 3.7 introduced the `@dataclass` decorator, it was met with widespread applause. It was modern, powerful, and solved a common problem: reducing the boilerplate of writing classes that primarily store data. But in our rush to embrace the new, we sometimes forget the battle-tested veterans that paved the way.

Long before dataclasses, Python already had elegant solutions for creating simple, data-centric objects. These tools, `collections.namedtuple` and its successor `typing.NamedTuple`, are more than just historical footnotes. They are powerful, efficient, and in many cases, still the perfect tool for the job. They are the unsung heroes of Python’s data structures, and it’s time they got their due.

This article is a tribute to these workhorses. We’ll explore their strengths, understand their differences, and see why they deserve a permanent place in your developer toolkit.

---

### The Original Hero: collections.namedtuple

Let’s start with a problem every Python developer has faced. You’re working with a set of related data — say, a point on a map — and you store it in a tuple.

```python
sofia = (42.6977, 23.3219)

# ... later in the code
# Wait, which one is latitude?
latitude = sofia[0]
longitude = sofia[1]
```

This works, but it’s fragile and hard to read. You have to rely on “magic numbers” (the indices 0 and 1) to access the data. A month from now, will you remember which is which? Will your teammates? This is where `collections.namedtuple`, available since Python 2.6, rides to the rescue.

It’s a factory function that creates a new class — a subclass of tuple — with named fields. It’s like getting a custom-built tuple with labels.

```python
from collections import namedtuple

# Define the structure of our new class
# The first argument is the class name, the second is a string of field names
GeoPoint = namedtuple('GeoPoint', 'latitude longitude')

# Now, we can create instances of our new GeoPoint class
sofia = GeoPoint(42.6977, 23.3219)

# The magic is in the access
print(f"Sofia's Latitude: {sofia.latitude}")
print(f"Sofia's Longitude: {sofia.longitude}")
```

Suddenly, our code is self-documenting. `sofia.latitude` is infinitely clearer than `sofia[0]`.

---

### The Superpowers of namedtuple

What makes `namedtuple` so great is that it retains all the best qualities of a tuple while adding this layer of readability.

1.  **Immutability:** Just like tuples, named tuples are immutable. Once you create an instance, its values cannot be changed. This makes them perfect for storing data that shouldn’t be accidentally modified, like configuration settings or records from a database.
2.  **Lightweight:** A `namedtuple` instance is incredibly memory-efficient. It uses the exact same amount of memory as a regular tuple because the field names are stored in the generated class, not in every single instance. For programs that create millions of small objects, this can be a significant performance win.
3.  **Tuple Compatibility:** Since it is a tuple, you can use it anywhere a tuple is expected. It supports indexing, slicing, and unpacking.

```python
# Unpacking works just like a regular tuple
lat, lon = sofia
print(f"Unpacked: Latitude={lat}, Longitude={lon}")
```

It also comes with a few handy helper methods (all prefixed with an underscore to avoid clashing with your field names).

```python
# _fields: A tuple of the field names
print(f"Fields: {sofia._fields}")

# _asdict(): Returns the object as an OrderedDict (or a regular dict since Python 3.8)
print(f"As Dictionary: {sofia._asdict()}")

# _replace(): Creates a NEW instance with specified fields replaced
# This respects immutability!
sao_paulo = sofia._replace(latitude=-23.5505, longitude=-46.6333)
print(f"São Paulo: {sao_paulo}")
```

The `_asdict()` method is particularly useful for tasks like serializing your data to JSON.

---

### The Modern Successor: typing.NamedTuple

As Python evolved, so did its philosophy. The introduction of optional type hints in Python 3.5 was a monumental shift, allowing for static analysis that could catch bugs before code even ran. The classic `collections.namedtuple` had one weakness in this new world: its syntax didn’t support type hints.

Enter `typing.NamedTuple`. Introduced with the `typing` module, it does everything `collections.namedtuple` does but with a more modern, class-based syntax that fully embraces type annotations.

```python
from typing import NamedTuple
import datetime

# The syntax is now a proper class definition
class WebUser(NamedTuple):
    """Represents a user on our platform."""
    username: str
    email: str
    is_premium: bool
    last_login: datetime.date

# Instantiation is the same
jane = WebUser(
    username='jane_doe', 
    email='jane@example.com', 
    is_premium=True, 
    last_login=datetime.date(2025, 11, 18)
)

print(f"User: {jane.username}, Premium: {jane.is_premium}")
```

This might look like just a syntactic change, but it’s a massive improvement for several reasons:

1.  **First-Class Type Hint Support:** This is the headline feature. Now, static analysis tools like Mypy can understand the structure of your data. If you try to pass a string to `is_premium`, your editor or a pre-commit hook can warn you immediately.
2.  **Superior Readability:** The class-based syntax is more familiar to Python developers. It provides a natural place to put a docstring, making your code even more self-documenting.
3.  **Easily Add Methods:** Because it uses the `class` statement, adding behavior is straightforward. You can add methods just like you would with any other class.

```python
class WebUser(NamedTuple):
    """Represents a user on our platform."""
    username: str
    email: str
    is_premium: bool
    last_login: datetime.date

    def is_active(self, days_threshold: int = 30) -> bool:
        """Checks if the user has logged in recently."""
        delta = datetime.date.today() - self.last_login
        return delta.days < days_threshold

# Now we can call our method!
print(f"Is Jane active? {jane.is_active()}")
```

This is a huge advantage over `collections.namedtuple`, where adding methods involves awkward “monkey-patching” after the class is created.

4.  **Default Values:** `typing.NamedTuple` also allows for default values, though it’s important to remember that fields without defaults cannot follow fields with defaults.

```python
class WebUser(NamedTuple):
    username: str
    email: str
    last_login: datetime.date
    is_premium: bool = False # Default value
```

---

### The Showdown: When to Use Which?

Both are tuple subclasses, both are immutable, and both are memory-efficient. So how do you choose?

Here’s a simple guide:

**Use collections.namedtuple when:**

*   You’re working on a codebase that needs to support older versions of Python.
*   You need to create a simple data structure dynamically at runtime (e.g., from field names stored in a list).
*   You want the absolute most basic, no-frills container with zero ceremony.

**Use typing.NamedTuple when:**

*   You are writing modern, type-hinted Python.
*   You want an immutable data structure. This is the key reason to choose it over a default `@dataclass`, which is mutable.
*   You need the memory efficiency of a tuple but want a cleaner syntax and the ability to add simple helper methods.

---

### Conclusion

While `@dataclass` is a fantastic tool, it creates mutable objects by default. Immutability is a powerful concept that leads to safer, more predictable code. When you need a lightweight object that bundles a few attributes together and guarantees they won’t change, `typing.NamedTuple` is often the superior choice.

Don’t let these powerful tools gather dust. The original `namedtuple` is a testament to Python’s long-standing focus on practical, readable code. Its successor, `NamedTuple`, carries that legacy into the modern era of static typing. They are simple, efficient, and robust.