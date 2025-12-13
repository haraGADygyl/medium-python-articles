# The Slash and the Star: Mastering Python’s Weirdest Parameter Syntax
#### How to use the / and * operators to build robust, self-documenting, and refactor-safe Python APIs

**By Tihomir Manushev**  
*Nov 28, 2025 · 8 min read*

---

If you have spent any time reading the documentation for Python’s standard library lately, or perhaps digging through the source code of a modern framework like FastAPI or Pandas, you might have stumbled upon a function signature that looks broken.

It might look something like this:

```python
def process_data(data, /, *, strict=False):
    pass
```

At first glance, this looks like a syntax error. Since when are mathematical operators like division (`/`) and multiplication (`*`) allowed to float freely inside a function definition? Did the developer fall asleep on the keyboard?

Rest assured, it is not a typo. These symbols are syntactical boundaries. They represent one of the most powerful tools in a Python developer’s toolkit for designing clean, robust, and maintainable APIs. They allow you to control exactly how a user calls your function — forcing them to be explicit when safety is required, or allowing them to be concise when verbosity gets in the way.

In this article, we are going to demystify the slash and the star. We will move beyond the basic `def func(a, b):` and learn how to architect function signatures that are self-documenting and resistant to misuse.

---

### The Problem: Ambiguity in Arguments

To understand why these features exist, we first have to look at the chaos of standard Python argument passing. By default, Python arguments are “flexible.” You can pass them by position, or you can pass them by keyword.

Consider a simple function that calculates the price of an item after tax:

```python
def calculate_total(price, tax_rate, discount):
    return price * (1 + tax_rate) - discount
```

This seems innocent enough. But how does a user call it?

```python
# Option A: Positional
total = calculate_total(100, 0.05, 10)

# Option B: Keywords
total = calculate_total(price=100, tax_rate=0.05, discount=10)

# Option C: A Mix
total = calculate_total(100, discount=10, tax_rate=0.05)
```

Option A is concise, but risky. If someone reads `calculate_total(100, 0.05, 10)`, can they be sure `10` is the discount and not a shipping fee? What if `tax_rate` and `discount` were swapped in a refactor? The function call would still run, but the math would be wrong.

Option B is clear, but verbose. Typing `price=` every time you want to calculate a total feels redundant.

Python 3 introduced specific syntaxes to solve this dilemma, allowing us to enforce the “best of both worlds.”

---

### The Star (*): Enforcing Clarity with Keyword-Only Arguments

Let’s start with the asterisk. You likely know `*args` and `**kwargs`, but the “bare asterisk” is different. When placed in a function signature, the `*` acts as a wall. It consumes all remaining positional arguments (which is none, because it has no name) and forces everything that follows to be passed as a keyword argument.

This is the antidote to what programmers call “Boolean Blindness.”

#### The “Boolean Blindness” Trap

Imagine a function that deletes users.

```python
def delete_user(user_id, permanent):
    # logic ...
    pass
```

If you see this code in a pull request: `delete_user(42, True)`, your heart should skip a beat. What does `True` mean? Does it mean “delete permanently”? Does it mean “dry run”? Does it mean “send email notification”? You have to read the function definition to know.

We can fix this by forcing the caller to name that argument.

```python
def delete_user(user_id, *, permanent=False):
    if permanent:
        print(f"User {user_id} wiped from database.")
    else:
        print(f"User {user_id} moved to archive.")
```

Now, try calling it the lazy way. Python rejects the positional `True`. The caller is forced to write:

```python
delete_user(99, permanent=True)
```

This single character makes your code readable at the call site. It documents intent. The `*` creates a clear separation: the `user_id` is the primary subject (positional is fine), but the configuration options (flags, modes) require explicit labeling.

---

### The Slash (/): Enforcing Simplicity with Positional-Only Arguments

The forward slash is the newer sibling, officially landing in Python 3.8. While the `*` forces arguments to be named, the `/` forces arguments to **not** be named.

Anything to the left of the `/` in a function signature is positional-only. You cannot use the parameter name as a keyword when calling the function.

But why would you ever want to restrict a user’s ability to use keywords? Isn’t explicit better than implicit?

There are two main reasons: **Decoupling** and **Clarity**.

**1. Decoupling Interface from Implementation**

When you define a function `def square(number):`, you are implicitly promising that the variable name `number` is part of your public API. If a user calls `square(number=5)`, and you later decide to refactor your code to `def square(value):`, you have just broken their code.

However, for a function like `square`, the argument name doesn’t matter. It’s just “the thing we are squaring.” By making it positional-only, you reserve the right to rename the internal parameter without triggering a breaking change for your users.

**2. Matching Mental Models**

Some functions are just naturally positional. Consider a function converting RGB colors to Hex.

```python
def rgb_to_hex(r, g, b, /):
    return "#{:02x}{:02x}{:02x}".format(r, g, b)
```

Calling this function as `rgb_to_hex(r=255, g=0, b=128)` is technically correct in standard Python, but it’s weird. RGB is a standard tuple. The order (red, green, blue) is universally understood. Allowing keywords here creates noise.

By using the slash we have stripped away the unnecessary verbosity. We are telling the developer: “Just give me the three numbers. Don’t overthink the labels.”

---

### Putting It Together: The Three Zones

When you combine the Slash and the Star, you create a function signature divided into three distinct zones. This is the pinnacle of Python API design.

```python
def complex_function(pos_only, /, standard, *, kw_only):
    ...
```

1.  **Left of `/`**: Positional-Only. The strict core inputs where names don’t matter to the caller.
2.  **Between `/` and `*`**: Standard (Flexible). The old-school Python arguments. Can be passed by position or keyword.
3.  **Right of `*`**: Keyword-Only. Configuration flags and options that must be explicit.

---

### A Real-World Example: A Text Formatter

Let’s imagine we are building a utility function for a content management system. We want to truncate text to a certain length, with an option to add an ellipsis.

Here is how we might design this using the three zones.

```python
def truncate_text(text, max_length, /, suffix="...", *, strip_newlines=True):
    """
    Truncates text to a max_length.
    
    Parameters:
    - text: The string to process (Positional-Only)
    - max_length: integer (Positional-Only)
    - suffix: String to append (Flexible)
    - strip_newlines: Boolean cleanup flag (Keyword-Only)
    """
    if strip_newlines:
        text = text.replace('\n', ' ')
        
    if len(text) <= max_length:
        return text
        
    return text[:max_length] + suffix
```

Let’s break down the logic behind this signature design:

*   **`text` and `max_length` (Positional-Only):** These are the core arguments. The function is a truncate operation. You cannot have the operation without the text and the length. `truncate_text(my_string, 10)` reads naturally. Writing `truncate_text(text=my_string, max_length=10)` is cumbersome for the primary arguments.
*   **`suffix` (Flexible):** This is in the middle. It’s an optional modifier. `truncate_text(s, 10, “ — -”)` is readable, but `truncate_text(s, 10, suffix=” — -”)` is also nice if you want to be clear. We give the user the choice.
*   **`strip_newlines` (Keyword-Only):** This is a boolean flag changing behavior. We absolutely do not want someone seeing `truncate_text(s, 10, “…”, True)`. That “True” is baffling. We enforce `strip_newlines=True`.

**Valid Calls**

```python
s = "Hello\nWorld, this is Python."

# 1. Minimal call
truncate_text(s, 5) 
# Result: "Hello..."

# 2. Changing the suffix positionally (Flexible zone)
truncate_text(s, 5, "!") 
# Result: "Hello!"

# 3. Using the flag explicitly (Keyword zone)
truncate_text(s, 20, strip_newlines=False)
# Result: "Hello\nWorld, this..."
```

**Invalid Calls (and why they fail)**

```python
# Fails: text is positional-only
truncate_text(text=s, max_length=5) 

# Fails: strip_newlines is keyword-only
truncate_text(s, 5, "...", False)
```

---

### Why This Matters for Your Career

You might be thinking, “This seems like a lot of work just to define a function.”

If you are writing a quick script to organize your holiday photos, you are right. Standard arguments are fine. But if you are writing library code, shared utilities for your team, or an API that will be used by hundreds of other developers, this discipline is crucial.

1.  **Refactoring Safety:** By using `/`, you protect yourself from users depending on your internal variable names. You can change `max_length` to `limit` in your code, and because users were forced to pass it positionally, their code won’t break.
2.  **Readability Enforcement:** By using `*`, you ensure that boolean flags in your codebase are readable. You eliminate the mystery of “Magic Booleans.”
3.  **Professional Polish:** Using these features shows a deep understanding of Python’s data model. It aligns your code with the standard library (functions like `len()`, `pow()`, and `divmod()` use positional-only arguments).

---

### Conclusion

Python is often praised for its readability and “executable pseudocode” style. However, as projects grow, the looseness of Python’s default argument handling can lead to brittle interfaces and ambiguous function calls.

The slash (`/`) and the star (`*`) are the guardrails that keep your code on track. The slash says, “The order matters, not the name.” The star says, “The name matters, because the intent must be clear.”

Next time you are defining a function with more than two arguments, pause. Ask yourself: “Should this boolean be a keyword-only argument?” or “Does naming this first argument actually add value?” Use the weird syntax. Your future self — and the developers maintaining your code — will thank you for it.