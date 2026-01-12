# Deconstructing __repr__ vs. __str__: The Python Display Protocol
#### Why print() is for users, the REPL is for devs, and how to stop logging <object at 0x…> forever

**By Tihomir Manushev**  
*Jan 12, 2026 · 7 min read*

---

Every Python developer, regardless of seniority, has encountered the “Useless Object” log entry. You are debugging a critical failure in a microservice, you scan the error logs, and there, sitting mockingly in the variable dump, is this:

`<models.Transaction object at 0x7f8b1c2d3e40>`

This string tells you nothing. It tells you the type of the object and where it lives in memory — information that is technically accurate but practically useless for debugging business logic. You don’t care about the memory address; you care about the transaction ID, the amount, and the currency.

This failure of communication happens because the class author neglected Python’s Display Protocol. Unlike many languages that provide a single `toString()` method, Python acknowledges that an object has two distinct audiences: the developer and the user.

To serve these two masters, Python provides two distinct dunder (double underscore) methods: `__repr__` and `__str__`. Understanding the mechanics, philosophy, and interplay between these two methods is the difference between writing scripts and engineering robust, debuggable Python systems.

---

### The Philosophical Divide

The Python Data Model splits object representation into two clear lanes.

#### 1. __repr__: The Developer’s Contract

The `__repr__` (representation) method is the voice of the object speaking to you, the engineer. Its primary goal is unambiguity.

According to Python’s design philosophy, the string returned by `__repr__` should, if at all possible, be a valid Python expression that could recreate the object. This is often referred to as the “round-trip” property:

```python
obj == eval(repr(obj))
```

When you inspect an object in a debugger, log it to a file for traceability, or view it in the interactive REPL (Read-Eval-Print Loop), Python invokes `__repr__`. If this string is ambiguous, you are flying blind.

#### 2. __str__: The End-User’s View

The `__str__` string method is the voice of the object speaking to the end-user. Its primary goal is readability.

This method is invoked by the `print()` function and the `str()` constructor. It does not need to reveal implementation details, types, or internal states. It simply needs to look nice. For a datetime object, `__repr__` might look like `datetime.datetime(2023, 10, 25, 14, 30)`, while `__str__` simply outputs `2023–10–25 14:30:00`.

---

### The Mechanics of Display

To truly master these methods, we must look at how CPython handles them internally.

When you ask Python to display an object, it follows a specific resolution order. If you call `print(my_obj)` (which triggers `str()`), Python checks if the class implements `__str__`. If it does, that result is returned.

However, here is the critical fallback mechanism: If a class implements `__repr__` but not `__str__`, Python will use `__repr__` as a fallback for `print()` calls.

The inverse is not true. If you implement `__str__` but not `__repr__`, the REPL and debugger will revert to the default (and useless) `<object at 0x…>` display.

The Golden Rule of Python Classes: If you can only implement one, implement `__repr__`. It covers your bases for both debugging and display.

Let’s explore this with a concrete example. We will build a `StockPosition` class representing a holding in a financial portfolio. We will use modern Python 3.10+ syntax.

#### Phase 1: The “Useless” Default

```python
class StockPosition:
    def __init__(self, ticker: str, shares: int, avg_price: float):
        self.ticker = ticker
        self.shares = shares
        self.avg_price = avg_price

# Instantiating the object
pos = StockPosition("AAPL", 50, 145.20)

print(pos)
```

In REPL, this output is unacceptable for production code. We cannot verify the state of the object without manually inspecting attributes.

#### Phase 2: Implementing __repr__

We will now implement `__repr__` to provide a faithful, unambiguous string representation. Note the use of `!r` in the f-string, which is a standard format specifier that calls `repr()` on the interpolated value (adding quotes around strings automatically).

```python
class StockPosition:
    def __init__(self, ticker: str, shares: int, avg_price: float):
        self.ticker = ticker
        self.shares = shares
        self.avg_price = avg_price

    def __repr__(self) -> str:
        # Dynamic class name for inheritance safety
        class_name = type(self).__name__
        # !r forces the repr of the attribute (adds quotes to strings)
        return f"{class_name}(ticker={self.ticker!r}, shares={self.shares}, avg_price={self.avg_price})"

pos = StockPosition("AAPL", 50, 145.20)

print(pos)
```

We now have a perfect round-trip representation. We can copy the output `StockPosition(ticker=’AAPL’, …)` and paste it into code to recreate the object.

#### Phase 3: Implementing __str__

While `__repr__` is great for us, a business user looking at a report doesn’t want to see class constructors. They want to see the ticker and the total value.

```python
class StockPosition:
    def __init__(self, ticker: str, shares: int, avg_price: float):
        self.ticker = ticker
        self.shares = shares
        self.avg_price = avg_price

    def __repr__(self) -> str:
        class_name = type(self).__name__
        return f"{class_name}(ticker={self.ticker!r}, shares={self.shares}, avg_price={self.avg_price})"

    def __str__(self) -> str:
        # User-friendly display
        market_value = self.shares * self.avg_price
        return f"[{self.ticker}] {self.shares} shares @ ${self.avg_price:.2f} (Total: ${market_value:,.2f})"

pos = StockPosition("AAPL", 50, 145.20)

# The User sees the formatted report
print(pos)
```

---

### The Container Trap

There is a subtle nuance regarding containers (lists, tuples, dicts) that often confuses developers. When you `print()` a list of objects, you might expect Python to call `__str__` on the list, which would in turn call `__str__` on the items inside.

This is not what happens.

Python’s container types implement their own `__str__` method, but when iterating over their contents to build their string representation, they exclusively call `__repr__` on the items they contain. This design decision ensures that a list of strings, for example, clearly shows which items are strings (surrounded by quotes) and which might be other types.

```python
portfolio = [
    StockPosition("GOOGL", 10, 2800.00),
    StockPosition("MSFT", 20, 300.00)
]

print(f"Portfolio: {portfolio}")
```

Even though we are `print`-ing the list, the items inside use their `__repr__`. If we had only implemented `__str__` and skipped `__repr__`, this list would look like `[<__main__.StockPosition…>, <__main__.StockPosition…>]`, rendering logs of collections useless.

---

### Best Practices for Production

When implementing these methods in a professional codebase, adhere to the following guidelines to ensure maintainability and security.

#### 1. Use type(self).__name__

Avoid hardcoding the class name in your `__repr__` string. If you subclass `StockPosition` later (e.g., `class ShortPosition(StockPosition)`), a hardcoded name will result in a lying `__repr__`.

```python
# Bad
return f"StockPosition(ticker={self.ticker!r}...)"

# Good
return f"{type(self).__name__}(ticker={self.ticker!r}...)"
```

#### 2. Leverage f-string Flags

Python f-strings support conversion flags that mirror the dunder methods.

*   `{obj!r}` forces a call to `repr(obj)`.
*   `{obj!s}` forces a call to `str(obj)`.
*   `{obj!a}` calls `ascii(obj)`, escaping non-ASCII characters.

Using `!r` is essential for string attributes in `__repr__` to ensure the quotes are present, distinguishing “5” (string) from 5 (integer).

#### 3. Mask Sensitive Data

While `__repr__` is for developers, logs are often stored in semi-public locations (like Splunk or Datadog). If your object contains PII (Personally Identifiable Information), secrets, or API keys, your `__repr__` must mask them.

```python
def __repr__(self) -> str:
    return f"{type(self).__name__}(user_id={self.user_id}, api_key='***')"
```

This breaks the “round-trip” capability (`eval` won’t work), but security trumps strict adherence to the Data Model theoreticals.

---

### Conclusion

The `__repr__` and `__str__` methods are not merely syntactic sugar; they are the fundamental interface between your data and the world. `__repr__` is your lifeline during 3 AM debugging sessions, providing an unambiguous map of your object’s state. `__str__` is the polished veneer you present to the user.

By treating the implementation of `__repr__` as a mandatory requirement for any custom class, you dramatically reduce the cognitive load required to maintain your code. Never let your objects remain silent, opaque blocks of memory. Give them a voice.
