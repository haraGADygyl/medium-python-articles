# Advanced Features of Python’s @dataclass
#### Go beyond the basics and master immutability, custom initializers, and field-level controls to write more robust and expressive Python code

**By Tihomir Manushev**  
*Nov 14, 2025 · 7 min read*

---

If you’ve been writing Python for a while, you’ve probably felt the tedium of creating classes that do little more than hold data. You write `__init__`, assigning `self.x = x`, `self.y = y`, and then you write `__repr__` for sane debugging, and maybe `__eq__` to make them comparable. It’s a lot of boilerplate for a simple container.

Python 3.7 introduced the `@dataclass` decorator, a brilliant tool that autogenerates those boilerplate methods for you. With a simple decorator, your plain-looking class suddenly gets a fully-featured constructor, a clean representation, and value-based equality.

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

p1 = Point(1.5, 2.5)
p2 = Point(1.5, 2.5)

print(p1)
print(p1 == p2)
```

This is fantastic, but it’s just scratching the surface. The true power of `@dataclass` lies in its advanced customization options, which can transform your simple data containers into robust, self-validating, and highly expressive objects. Let’s go beyond the basics and explore how you can supercharge your classes.

---

### Achieving True Immutability with frozen=True

One of the most powerful concepts in programming is immutability. An immutable object is one whose state cannot be modified after it is created. This is a huge advantage: it makes your code more predictable, prevents accidental modifications, and allows objects to be used safely as keys in dictionaries or elements in sets.

By default, dataclasses are mutable. But you can change that with a single keyword argument.

```python
from dataclasses import dataclass, FrozenInstanceError

@dataclass(frozen=True)
class UserProfile:
    user_id: int
    username: str

user = UserProfile(user_id=101, username='alex')

# This is fine
print(user.username)

# But this will raise an error!
try:
    user.username = 'alex_the_great'
except FrozenInstanceError:
    print("Nope! You can't change a frozen instance.")
```

When you set `frozen=True`, `@dataclass` generates a `__setattr__` and `__delattr__` method that raises a `FrozenInstanceError` on any attempt to modify a field.

A fantastic side effect is that frozen dataclass instances are automatically hashable (provided all their fields are hashable). This means you can add them to sets and use them as dictionary keys without any extra work.

```python
user_one = UserProfile(user_id=101, username='alex')
user_two = UserProfile(user_id=102, username='casey')

# Now we can do this!
user_data = {user_one: 'Logged in', user_two: 'Inactive'}
print(user_data[user_one])
```

---

### Making Your Objects Sortable with order=True

What if you want to sort a list of your objects? Normally, you’d have to implement the rich comparison methods: `__lt__` (less than), `__le__` (less than or equal to), etc. This is another tedious task that `@dataclass` can handle for you.

By setting `order=True`, the decorator will generate all four of these methods automatically.

```python
from dataclasses import dataclass

@dataclass(order=True)
class PlayerScore:
    score: int
    name: str

scores = [
    PlayerScore(1200, 'Zelda'),
    PlayerScore(950, 'Mario'),
    PlayerScore(1500, 'Link'),
    PlayerScore(950, 'Luigi'),
]

# The sort is done field by field, in the order of declaration.
# First by score, then by name for ties.
scores.sort(reverse=True)

for player in scores:
    print(player)
```

The comparison is performed field by field, starting from the top. In our example, it first compares by score. If the scores are equal (like for Mario and Luigi), it moves on to the next field, name, to break the tie.

---

### Fine-Grained Control with field() and default_factory

This is where `@dataclass` truly shines. The `dataclasses.field()` function allows you to customize the behavior of each field individually.

One of the most common pitfalls in Python is using mutable default arguments, like a list or a dictionary. If you do this in a regular class, every instance shares the exact same list. `@dataclass` is smart enough to forbid this pattern outright, raising a `ValueError` if you try.

The correct solution is `default_factory`. It’s a parameter that takes a zero-argument callable (like `list`, `dict`, or a lambda function) and calls it to create a new default value for each instance.

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Team:
    name: str
    members: List[str] = field(default_factory=list)

# Each team gets its own, unique list of members
team_a = Team('Warriors')
team_a.members.append('Steph')

team_b = Team('Lakers')
team_b.members.append('LeBron')

print(team_a)
print(team_b)
```

The `field()` function is a gateway to much more customization:

*   `repr=False`: Exclude a field from the generated `__repr__` method. This is perfect for fields that contain sensitive information or are too verbose to be useful in a log.
*   `compare=False`: Exclude a field from being used in the generated comparison methods (`__eq__`, `__lt__`, etc.).
*   `init=False`: Exclude a field from the `__init__` method. This is for fields that are computed after the object is created.

This leads us directly to the next feature…

---

### Custom Initialization Logic with __post_init__

Sometimes, you need to do more than just assign values during initialization. You might need to validate data, or compute one field based on the values of others. For this, `@dataclass` provides a special hook: the `__post_init__` method.

If you define a method named `__post_init__`, the generated `__init__` will call it right after it has initialized all the fields.

Let’s combine `init=False` and `__post_init__` to build a more intelligent class.

```python
from dataclasses import dataclass, field
from urllib.parse import urljoin

@dataclass
class Article:
    title: str
    author: str
    content: str
    slug: str = field(init=False, repr=False)
    url: str = field(init=False)

    def __post_init__(self):
        # Validate that the title is not empty
        if not self.title:
            raise ValueError("Title cannot be empty.")
            
        # Generate the slug from the title
        self.slug = self.title.lower().replace(' ', '-')
        
        # Compute the full URL
        base_url = 'https://myblog.com/'
        self.url = urljoin(base_url, self.slug)

article = Article(
    title='Advanced Dataclasses',
    author='Pythonista',
    content='Once upon a time...'
)

print(article)
```

Look at how clean that is! The slug and url are not passed to the constructor. Instead, they are computed in `__post_init__`, which also serves as a place to add validation logic. We also decided the slug wasn’t important for the repr, so we excluded it.

---

### Distinguishing Class and Instance Variables

In a regular Python class, any variable defined directly in the class body is a class variable, shared by all instances. But with dataclasses, any variable with a type annotation is treated as an instance field.

So how do you declare a class variable that also has a type hint? You use `typing.ClassVar`. The `@dataclass` decorator knows to ignore any field marked as `ClassVar`, treating it as a standard class variable.

```python
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass
class Item:
    # This is a class variable, shared by all items
    tax_rate: ClassVar[float] = 0.05
    
    name: str
    price: float
    net_price: float = field(init=False)

    def __post_init__(self):
        self.net_price = self.price * (1 + self.tax_rate)

item1 = Item('Book', 20.00)
item2 = Item('Pen', 1.00)

print(f"{item1.name}: ${item1.net_price:.2f}")
print(f"{item2.name}: ${item2.net_price:.2f}")

# If we change the tax rate on the class...
Item.tax_rate = 0.10

# ...any new instances will use the new rate.
item3 = Item('Notebook', 5.00)
print(f"{item3.name}: ${item3.net_price:.2f}")
```

---

### Conclusion

Python’s `@dataclass` is far more than just a shortcut for reducing boilerplate. It’s a sophisticated tool for designing data-centric classes that are clear, robust, and highly functional. By leveraging features like `frozen=True` for immutability, `order=True` for sortability, `field()` for granular control, `__post_init__` for custom logic, and `ClassVar` for class-level data, you can write code that is not only more concise but also more correct and expressive.

The next time you find yourself writing a class to hold some state, don’t just stop at the basic decorator. Dig into these advanced features — they will help you write better Python.