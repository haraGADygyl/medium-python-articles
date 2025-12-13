# Python’s New Superpower: Unpacking Dictionaries Like a Pro
#### Go beyond `**kwargs` and master the art of declarative dictionary manipulation with the double-splat operator.**

**By Tihomir Manushev**  
*Oct 20, 2025 · 7 min read*

---

If you’ve been writing Python for a little while, you’ve probably met the `**kwargs` syntax in a function definition. It’s that nifty trick that bundles up all the keyword arguments you pass into a function and hands them to you as a dictionary. It’s a classic, reliable tool.

But what about the other side of the coin? What if you already have a dictionary, and you want to do the reverse — unbundle it into keyword arguments or even into another dictionary?

This is where Python’s dictionary unpacking superpower comes in, using the very same `**` operator (often called the “double-splat”). Since its enhancement in Python 3.5 (via PEP 448), this feature has evolved from a niche tool for function calls into a cornerstone of modern, expressive data manipulation. It’s one of those features that, once you truly grasp it, will make you look back at your old code and wonder, “Why was I doing it the hard way?”

Let’s move beyond the basics and explore how you can wield this power to write cleaner, more declarative, and more Pythonic code.

---

### The Classic Use Case: Unpacking into Function Calls

First, let’s start where most developers first encounter unpacking: function arguments. Imagine you have a function that sends a notification. It might take several optional parameters to customize the message.

```python
def send_notification(message, user, *, title="New Message", color="blue", sound="default"):
    """Sends a notification with various options."""
    print(f"--- Notification for {user} ---")
    print(f"Title: {title}")
    print(f"Message: {message}")
    print(f"Color: {color}")
    print(f"Sound: {sound}")
    print("--------------------------")

# Now, let's say you have a dictionary with some custom settings
user_prefs = {
    'color': 'green',
    'sound': 'chime',
    'title': 'Project Update'
}

# The old way might involve manually pulling out values...
# send_notification(
#     "The project has been updated.",
#     "Alice",
#     title=user_prefs.get('title'),
#     color=user_prefs.get('color'),
#     sound=user_prefs.get('sound')
# )

# The SUPERPOWER way:
send_notification("The project has been updated.", "Alice", **user_prefs)
```

Look at that last line. It’s clean, it’s direct, and it perfectly communicates our intent. The `**user_prefs` tells Python to take the key-value pairs from the `user_prefs` dictionary and treat them as if they were keyword arguments passed directly to the function.

This is more than just a cosmetic improvement. If you add a new preference to your dictionary, you don’t have to change the function call. It just works.

There’s a crucial rule here: the keys in the dictionary must be strings, and they must match the names of the function’s parameters. Trying to unpack a key like `123` or a key that doesn’t correspond to a parameter name will result in a `TypeError`.

---

### The Real Game Changer: Unpacking Inside Dictionary Literals

This is where the feature truly becomes a superpower. Before Python 3.5, if you wanted to merge two dictionaries, you had to do something like this:

```python
# The Old Way
d1 = {'a': 1, 'b': 2}
d2 = {'b': 3, 'c': 4}

# Method 1: Create a copy and update
merged = d1.copy()
merged.update(d2)

print(merged)
```

This works, but it takes two separate statements. It’s not an expression.

Now, watch what you can do with dictionary unpacking:

```python
d1 = {'a': 1, 'b': 2}
d2 = {'b': 3, 'c': 4}

# The Modern, Powerful Way
merged = {**d1, **d2, 'd': 5}

print(merged)
```

This is a revelation. It’s a single, elegant expression. The same “last-one-wins” rule applies: the `b` from `d2` overwrote the `b` from `d1`. You can also sprinkle in new key-value pairs (`'d': 5`) wherever you like.

This syntax is perfect for managing configurations, where you often have a hierarchy of settings.

---

### A Practical Example: Web App Configuration

Imagine you’re building a web application. You might have default settings, settings for a specific environment (development vs. production), and maybe some user-specific overrides.

```python
# 1. Base configuration for the entire application
default_config = {
    'host': 'localhost',
    'port': 8000,
    'debug': False,
    'cache_ttl': 3600  # 1 hour
}

# 2. Overrides for the development environment
dev_config = {
    'debug': True,
    'cache_ttl': 10    # 10 seconds for easier testing
}

# 3. Dynamic settings, maybe from an admin panel
dynamic_settings = {
    'host': '0.0.0.0' # Listen on all interfaces
}

# Combine them all in one go!
final_config = {**default_config, **dev_config, **dynamic_settings}

print(final_config)
```

In one line, we’ve created a new configuration dictionary that correctly applies a hierarchy of settings. It’s readable, maintainable, and profoundly declarative. You’re not describing *how* to merge the dictionaries step-by-step; you’re describing what the final dictionary should look like.

---

### Advanced Tricks and Nuances

The power of unpacking doesn’t stop there. Here are a few more patterns you’ll find useful.

#### 1. Conditional Dictionary Entries

Sometimes you only want to add a key-value pair if a certain condition is met. Unpacking makes this surprisingly elegant.

```python
is_admin = True
user_id = 123

user_data = {
    'id': user_id,
    'name': 'Sam',
    # Parentheses force the conditional expression to evaluate first
    **({'permissions': ['read', 'write', 'delete']} if is_admin else {})
}

print(user_data)
# Output if is_admin is True:
# {'id': 123, 'name': 'Sam', 'permissions': ['read', 'write', 'delete']}

# Output if is_admin is False:
# {'id': 123, 'name': 'Sam'}
```

This works because unpacking an empty dictionary (`**{}`) does nothing. It’s a clean, inline way to build up a dictionary with optional sections without resorting to a multi-line `if` statement after the fact.

#### 2. Building API Payloads

When you’re working with external APIs, you often need to construct a JSON payload. Dictionary unpacking is your best friend here.

```python
def get_base_payload(api_key):
    return {'apiKey': api_key, 'version': 'v2'}


def search_products(query, api_key, *, include_variants=False, limit=20):
    """Constructs and returns a search payload for an API."""

    payload = {
        **get_base_payload(api_key),
        'query': query,
        'limit': limit,
        **({'withVariants': 'true'} if include_variants else {})
    }
    # In a real app, you would send this payload to the API
    return payload


# Create a payload for a specific search
search_payload = search_products("python books", "MY_SECRET_KEY", include_variants=True)
print(search_payload)
```

---

### Don’t Forget the New Kid: The Merge Operator `|`

As of Python 3.9, there’s another stylish way to merge dictionaries: the pipe `|` operator, which was inspired by how sets work.

```python
d1 = {'a': 1, 'b': 2}
d2 = {'b': 3, 'c': 4}

# Using the merge operator
merged = d1 | d2
print(merged)
```

So which should you use, `**` or `|`?

*   **`**` (Unpacking):** More versatile. It’s an expression that can be used inside a dictionary literal, allowing you to mix unpacked dicts with new key-value pairs (`{**d1, 'new_key': 1}`). It’s also been around longer (Python 3.5+).
*   **`|` (Merge Operator):** More specific and arguably more readable just for merging two dictionaries. The code `d1 | d2` very clearly says “merge d1 and d2.” It’s the newer option (Python 3.9+).

For simple merges, `|` is a great choice if you’re on a modern version of Python. For building complex dictionaries from multiple sources, `**` remains the undisputed champion.

---

### Conclusion

The double-splat `**` operator is one of the most significant syntactic improvements to Python’s data-handling capabilities in years. It allows you to graduate from imperative, step-by-step dictionary construction to a declarative style where you define the structure of your data in a single, readable expression.

You can combine, override, and conditionally build dictionaries with a syntax that is both powerful and beautiful. It’s a true Python superpower. So the next time you find yourself writing `.copy()` followed by `.update()`, take a moment to pause and consider if you can unleash the power of `**` instead. Your code will thank you for it.