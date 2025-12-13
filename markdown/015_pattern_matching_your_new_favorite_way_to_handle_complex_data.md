# Pattern Matching: Your New Favorite Way to Handle Complex Data
#### Ditch the nested if/elif statements and learn how Python 3.10’s most exciting feature can help you write cleaner, more declarative code

**By Tihomir Manushev**  
*Oct 29, 2025 · 6 min read*

---

Let’s be honest. We’ve all been there. You’re working with data from a JSON API, a database, or some other external source. You get back a dictionary, and your job is to pull out the information you need. But the data is… complicated.

Sometimes a key is present, sometimes it’s not. Sometimes a value is a single item, other times it’s a list. The data might have different “shapes” depending on the type of record you’re looking at. Before you know it, you’ve written something like this:

```python
def process_data_old_way(record):
    if 'type' in record:
        if record['type'] == 'tv-series':
            if 'creators' in record:
                # Handle a TV series with multiple creators
                print(f"TV series with creators: {', '.join(record['creators'])}")
            elif 'creator' in record:
                # Handle a TV series with a single creator
                print(f"TV series with creator: {record['creator']}")
            else:
                print("Invalid TV series record: missing creator info.")
        elif record['type'] == 'movie':
            if 'director' in record:
                # Handle a movie
                print(f"Movie directed by: {record['director']}")
            else:
                print("Invalid movie record: missing director.")
    else:
        print("Invalid record: no type specified.")
```

This nested nightmare of if/elif/else blocks is what we call the “Pyramid of Doom”. It’s hard to read, a pain to modify, and incredibly fragile. Add one more variation to the data schema, and you’re back in the pyramid, adding another level of indentation.

For years, this was just the way things were done in Python. But with the release of Python 3.10, we were given a powerful new tool to flatten this pyramid into a clean, declarative, and beautiful structure: Structural Pattern Matching.

It’s not just a fancy switch statement. It’s a completely new way to think about handling complex data.

---

### The Zen of match/case

Structural Pattern Matching introduces the `match` and `case` keywords. At first glance, it looks like a switch statement from languages like C++ or Java, but its power lies in its ability to match the structure of your data.

Instead of just checking a variable for a specific value, you can check if your data — like a dictionary — conforms to a certain shape. Let’s refactor our pyramid of doom using match/case.

Imagine we’re processing records from a media API. Here’s our new function:

```python
def get_creator(record: dict) -> str:
    match record:
        case {'type': 'tv-series', 'creators': [*names]}:
            return f"TV series with creators: {', '.join(names)}"
        
        case {'type': 'tv-series', 'creator': name}:
            return f"TV series with creator: {name}"

        case {'type': 'movie', 'director': name}:
            return f"Movie directed by: {name}"

        case {'type': 'tv-series'}:
            raise ValueError(f"Invalid 'tv-series' record: {record}")

        case _: # The "catch-all" or wildcard case
            raise ValueError(f"Invalid record: {record}")
```

Take a moment to appreciate how much cleaner that is. The indentation is flat. The logic is clear. Each case statement describes a valid “shape” of data we expect to see. This is the core idea: you’re not writing a procedure to pick the data apart; you’re providing a blueprint of what the data should look like.

Let’s break down how this magic works.

---

### Anatomy of a Mapping Pattern

The real power-up here is the ability to match against dictionary structures, or what the syntax calls “mapping patterns.”

**1. Matching on Keys and Values**

The simplest pattern matches specific key-value pairs.

```python
case {'type': 'movie', 'director': name}:
```

This pattern does three things at once:
*   It checks if the record is a dictionary-like object (a mapping).
*   It checks if it contains a key ‘type’ whose value is exactly ‘movie’.
*   It checks if it contains a key ‘director’. If it does, it captures the value associated with that key and assigns it to the variable `name`.

This combination of validation and value extraction (destructuring) is what makes pattern matching so expressive.

**2. Partial Matches are Your Friend**

Notice something important: our data records might also contain other keys, like ‘title’ or ‘year’.

```python
t1 = {'type': 'tv-series', 'season': 1, 'creator': 'John Smith', 'title': 'Awake and alive'}

get_creator(t1) 
# Output: 'TV series with creator: John Smith'
```

The pattern `case {'type': 'tv-series', 'creator': name}` succeeds even though `t1` has extra keys (‘season’ and ‘title’). Unlike a direct dictionary comparison, mapping patterns succeed on partial matches. As long as the subject contains the keys specified in the pattern, the match works. This makes your code resilient to changes in an API that adds new, optional fields.

**3. Destructuring Sequences Inside a Mapping**

This is where things get really cool. What if a TV series has multiple creators? Our API might send that as a list.

```python
case {'type': 'tv-series', 'creators': [*names]}:
```

This pattern matches a dictionary with a key ‘creators’ that points to a sequence. The `[*names]` syntax is a sequence pattern. It captures all the items in the list and assigns them to a new list called `names`.

So if our record is:
`{'type': 'tv-series', 'creators': ['Smith', 'Doe', 'Adams']}`

The variable `names` will become `['Smith', 'Doe', 'Adams']` inside the case block. No more `isinstance(record['creators'], list)` checks needed!

**4. Capturing the “Rest” of the Dictionary**

What if you want to match a few specific keys and then grab everything else in a separate dictionary? You can do that with the `**` operator, much like you would with `**kwargs` in a function.

```python
def process_food(item):
    match item:
        case {'category': 'Veggies', **details}:
            print(f"Veggies Details: {details}")
        case _:
            print("It's something else.")

food = {'category': 'Veggies', 'type': 'tomato', 'cost': 150}
process_food(food)
# Output: Veggies Details: {'type': 'tomato', 'cost': 150}
```

The `**details` must be the last item in the pattern, and it captures all remaining key-value pairs from the subject into a new dictionary called `details`. This is perfect for when you want to process a few known fields and pass the rest along to another function.

**5. The Indispensable Catch-All Case**

What happens if none of your patterns match? The match statement will raise a `MatchError` (Note: In strict terms, Python falls through without error if no case matches, but good practice often dictates handling it). To handle unexpected data gracefully, you should almost always include a catch-all case at the end:

```python
case _:
    raise ValueError(f"Invalid record: {record}")
```

The underscore `_` is a wildcard that matches anything without capturing it. This final case acts like the final `else` in an if/elif/else chain, ensuring that you have a plan for data that doesn’t fit any of your expected shapes.

---

### Why This is Profoundly Better than if/elif

It might be tempting to dismiss match/case as mere “syntactic sugar,” but it represents a fundamental shift from imperative to declarative programming.

*   **Declarative Style:** With if/elif, you write an imperative script of instructions: “Check for this key. If it’s there, check its value. If that matches, check for another key…” With match/case, you provide a declarative blueprint: “My data should look like this.” The code describes what the data is, not how to parse it.
*   **Readability and Intent:** The structure of your data is laid out right in the code. A new developer can look at the match block and immediately understand the different data shapes your program is designed to handle. It’s self-documenting.
*   **Safety and Robustness:** Pattern matching forces you to think about the different states your data can be in. The catch-all case `case _:` ensures you handle unexpected inputs instead of letting your program crash. It makes your code more robust by design.
*   **Validation and Destructuring in One Step:** This is the core superpower. You are no longer separating the “checking” from the “getting.” The pattern itself is the test. If the test passes, you already have the data you need, neatly extracted into variables.

---

### Conclusion

Structural Pattern Matching is one of the most significant features added to Python in years. It’s your new best friend for wrangling the messy, semi-structured data that defines so much of modern software development.

The next time you find yourself typing `if 'key' in my_dict:`, stop. Take a step back and ask yourself if you’re about to build another Pyramid of Doom. If you are, give match/case a try. It will lead to code that is not only more efficient to write but also a genuine pleasure to read.