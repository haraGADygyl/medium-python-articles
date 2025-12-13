# Python’s Sneakiest Bug: Why s1 == s2 Can Be False Even When Strings Look Identical
#### A deep dive into Unicode normalization and how to prevent subtle bugs in your Python code when comparing what appears to be identical text

**By Tihomir Manushev**  
*Nov 3, 2025 · 8 min read*

---

You’ve been coding in Python for a while. You feel confident. You write a simple piece of logic to check if a username from a database matches a user’s input. They look identical on the screen. You print them both out, side-by-side, and your eyes confirm it. Yet, Python insists they are not the same.

```python
# Let's say s1 comes from user input, and s2 from a database
s1 = 'élan'
s2 = 'élan' # This looks the same, but is it?

print(f"String 1: {s1}")
print(f"String 2: {s2}")
print(f"Are they equal? {s1 == s2}")
```

Running this code produces a result that can make a developer question their sanity.

Welcome to one of the deepest and most important topics when working with text in any programming language: Unicode normalization. This isn’t a bug in Python. It’s a fundamental characteristic of how modern text is represented, and understanding it will make you a much more robust and globally-minded developer.

---

### The Ghost in the Machine: Code Points vs. Visual Characters

The root of this “problem” lies in a simple fact: what you see as a single character is not always a single “thing” to the computer. The Unicode standard, which allows us to represent characters from nearly every language in the world, is a complex system.

To a human, the character **é** is just… well, **é**. It’s a single letter. But in the Unicode standard, there are two perfectly valid ways to represent it:

1.  **The Pre-Composed Character:** A single, unique code point for “LATIN SMALL LETTER E WITH ACUTE”. Its hexadecimal ID is `U+00E9`.
2.  **The Decomposed Sequence:** A sequence of two code points: the standard “LATIN SMALL LETTER E” (`U+0065`) followed immediately by the “COMBINING ACUTE ACCENT” mark (`U+0301`).

When a program renders text, it sees the combining mark and knows to place it on top of the preceding character. The final result on your screen is visually identical.

Let’s prove this by inspecting our “identical” strings from before.

```python
s1 = 'élan' # This uses the pre-composed character U+00E9
s2 = 'e\u0301lan' # This uses e (U+0065) + combining ´ (U+0301)

print(f"Length of s1: {len(s1)}")
print(f"Length of s2: {len(s2)}")
```

The output is revealing.

Aha! Now we see the truth. Python’s default equality check (`==`) for strings is simple and fast: it compares the sequence of code points one by one. In its eyes, `s1` is a sequence of four numbers, while `s2` is a sequence of five. They are fundamentally different, even if they look the same to us.

These two different-but-visually-identical representations are called **canonical equivalents**. The Unicode standard says that any application should treat them as identical. But Python’s `==` operator doesn’t go that deep on its own. For that, we need a special tool.

---

### The Fix: Bringing Order with unicodedata.normalize

Python’s standard library comes with a powerful module for handling the complexities of Unicode: `unicodedata`. The specific function we need is `unicodedata.normalize()`.

This function takes two arguments: a normalization form (as a string) and the string you want to normalize. It converts a string into a standard, predictable representation. There are four forms, but we’ll start with the two most important ones for solving our problem: **NFC** and **NFD**.

**NFC: Normalization Form C (Composition)**  
Think of ‘C’ as Composition. This form takes a string and composes sequences of characters and combining marks into the shortest possible pre-composed character. It’s the “let’s put it all together” form.

**NFD: Normalization Form D (Decomposition)**  
Think of ‘D’ as Decomposition. This form does the opposite. It takes pre-composed characters and breaks them down into their base characters and separate combining marks. It’s the “let’s take it all apart” form.

Let’s see them in action on our troublesome strings:

```python
from unicodedata import normalize

s1 = 'élan' # Pre-composed
s2 = 'e\u0301lan' # Decomposed

# Applying NFC to both
s1_nfc = normalize('NFC', s1)
s2_nfc = normalize('NFC', s2)

print(f"s1 NFC: {s1_nfc}, length: {len(s1_nfc)}")
print(f"s2 NFC: {s2_nfc}, length: {len(s2_nfc)}")
print(f"Are NFC forms equal? {s1_nfc == s2_nfc}")

print("-" * 20)

# Applying NFD to both
s1_nfd = normalize('NFD', s1)
s2_nfd = normalize('NFD', s2)

print(f"s1 NFD: {s1_nfd}, length: {len(s1_nfd)}")
print(f"s2 NFD: {s2_nfd}, length: {len(s2_nfd)}")
print(f"Are NFD forms equal? {s1_nfd == s2_nfd}")
```

This gives us the solution we’ve been looking for.

By converting both strings to the same normalized form — either NFC or NFD — we get a consistent sequence of code points. Now, Python’s `==` operator works exactly as we expect.

So which one should you use? For general-purpose string comparison and storage, **NFC** is the recommended standard. It’s typically what users generate from their keyboards and it’s the form recommended by the World Wide Web Consortium (W3C).

---

### Beyond Comparison: Practical Uses for NFD

If NFC is the best for comparisons, why does NFD even exist? It has its own set of powerful use cases, most notably for cleaning and transforming text.

Imagine you want to create a “slug” for a URL from a blog post title, or you want a search function that ignores accents. You need to strip those diacritics away. NFD is the perfect first step.

```python
from unicodedata import combining, normalize

def remove_accents(text: str) -> str:
    """
    Decomposes the string and filters out combining marks.
    """
    # 1. Decompose the string into base characters and combining marks
    decomposed_text = normalize('NFD', text)
    
    # 2. Filter out any characters that are combining marks  
    filtered_chars = [char for char in decomposed_text if not combining(char)]
    
    # 3. Join them back into a string
    return "".join(filtered_chars)

title = "Aprender Phyton é incrível!"
slug = remove_accents(title)
print(f"Original title: {title}")
print(f"Accent-free title: {slug}")
```

Here, we decompose **é** into **e** and **´**, and then `unicodedata.combining()` helps us identify and discard the **´**, leaving just the base character.

---

### The Deep End: Compatibility Forms NFKC and NFKD

There’s another layer to this. Some characters are not just canonical equivalents; they are **compatibility equivalents**. These are characters that exist in Unicode primarily for compatibility with older character sets. They often have a “preferred” representation.

For example, the ligature **ﬁ** (a single character, `U+FB01`) is visually similar to the two characters **f** and **i**. The fraction **½** (`U+00BD`) is a compatibility character for the sequence **1/2**.

The NFKC and NFKD forms handle these. The ‘K’ stands for Compatibility. These are “stronger” normalization forms that can significantly change your text.

```python
from unicodedata import normalize

s_compat = "The recipe requires ½ cup of flour and one 'ﬁne' egg."

# NFKC will compose and replace compatibility characters
s_nfkc = normalize('NFKC', s_compat)

# NFKD will decompose and replace compatibility characters
s_nfkd = normalize('NFKD', s_compat)

print(f"Original: {s_compat}")
print(f"NFKC: {s_nfkc}")
print(f"NFKD: {s_nfkd}")
```

Notice how **½** became **1/2** and **ﬁ** became **fi**.

> **Warning:** Use NFKC and NFKD with extreme caution. Because they can change the semantic meaning of text (e.g., a superscript ² in m² could become a regular 2), they are generally not suitable for storing data permanently. Their primary use is for features like search and indexing, where you want to treat many visually similar characters as the same thing to provide better search results.

---

### Your Go-To Strategy for Robust String Handling

Now that we’ve journeyed through the Unicode rabbit hole, let’s establish a clear, practical strategy.

1.  **Assume All Input is Messy:** Never assume that text data, whether from users, APIs, or files, is in a consistent normalized form.
2.  **Normalize Before Comparing:** When checking for equality, always normalize both strings to NFC first. A helper function is perfect for this.
3.  **Be Explicit in Your Logic:** For features like accent-insensitive search, use an NFD-based `remove_accents` function. For fuzzy searching, consider using NFKC, but be aware of its effects.

Here’s a robust comparison function you can add to your toolbox:

```python
from unicodedata import normalize

def are_strings_equal(s1: str, s2: str, case_insensitive: bool = False) -> bool:
    """
    Compares two strings for equality after applying NFC normalization.
    Optionally performs a case-insensitive comparison using casefold.
    """
    s1 = normalize('NFC', s1)
    s2 = normalize('NFC', s2)
    
    if case_insensitive:
        # Use casefold() as it's more thorough than lower() for international text
        return s1.casefold() == s2.casefold()
    else:
        return s1 == s2

# Our original problem
str_a = 'élan'
str_b = 'e\u0301lan'

print(f"Default comparison: {str_a == str_b}")
print(f"Normalized comparison: {are_strings_equal(str_a, str_b)}")
```

This function ensures that you are always comparing apples to apples, finally resolving the sneaky bug that wasn’t a bug at all.

---

### Conclusion

The “identical but not equal” string problem is a classic rite of passage for developers moving from simple ASCII-based programming to the complex, global world of Unicode. By understanding that visual representation is separate from the underlying code point sequence, you can anticipate and solve these issues gracefully. Remember to use `unicodedata.normalize('NFC', …)` as your go-to for safe, reliable string comparisons, and keep the other normalization forms in your toolkit for more specialized text processing tasks. Mastering this concept will save you countless hours of debugging and make your applications more reliable for users all over the world.