# More Than a String: A Deep Dive into Python’s bytes and bytearray
#### Why b’hello’[0] returns 104, and what that means for robust Python code.

**By Tihomir Manushev**  
*Nov 5, 2025 · 7 min read*

---

If you’ve ever been baffled by a Python error message, you’re not alone. But some are more baffling than others. Consider this seemingly simple piece of code:

```python
# A simple bytes object
binary_greeting = b'hello'

# Let's get the first character... or so we think.
first_item = binary_greeting[0]

print(f"The first item is: {first_item}")
print(f"Its type is: {type(first_item)}")
```

If you run this, you won’t get the string ‘h’. You’ll get this:

> The first item is: 104
> Its type is: <class 'int'>

An integer? What’s going on? This isn’t a bug; it’s a feature. It’s the key that unlocks a fundamental concept in modern Python: a bytes object is not a string of characters. It’s a sequence of numbers.

Understanding this distinction is one of the most important steps you can take to level up as a Python developer. It’s the difference between writing code that works most of the time and writing robust code that handles data correctly every time. Let’s dive deep into bytes, its mutable sibling bytearray, and the binary world they inhabit.

---

### The Great Divide: Text vs. Binary

The confusion stems from Python 2, where the standard `str` type was a jack-of-all-trades, ambiguously representing both text and binary data. This led to a swamp of encoding bugs and the infamous `UnicodeDecodeError`.

Python 3 fixed this with a clean, sharp separation:

1.  **`str` is for text.** It’s a sequence of Unicode code points. Think of it as representing abstract characters: ‘A’, ‘€’, ‘π’, ‘猫’. This is the stuff humans read.
2.  **`bytes` is for binary data.** It’s a sequence of integers, where each integer is between 0 and 255. This is the stuff computers speak: raw data from a network socket, the content of a JPEG file, or a UTF-8 encoded representation of a string.

A great mental model is to remember: **Humans use text. Computers speak bytes.** Your program lives at the border between these two worlds, and its job is to translate between them. The tools for this translation are `.encode()` (str -> bytes) and `.decode()` (bytes -> str).

---

### Meet bytes: The Immutable Sequence of Integers

The most important thing to burn into your memory is that a bytes object is an immutable sequence of integers. Let’s break that down.

*   **Sequence:** It’s an ordered collection, just like a list or a tuple. You can iterate over it, slice it, and get its length.
*   **Of Integers:** The items inside are numbers from 0 to 255, not characters. The 104 we saw earlier is the ASCII value for the character ‘h’.
*   **Immutable:** Once a bytes object is created, it cannot be changed. This makes it safe to use as a dictionary key and ensures data integrity.

---

### Creating bytes Objects

There are a few common ways to create a bytes object.

```python
# 1. Using the literal b'' syntax (for ASCII characters)
data_literal = b'some raw data'
print(f"Literal: {data_literal}")

# 2. Encoding a string into bytes
# This is the most common way you'll create bytes
text_message = "你好, world!"
utf8_data = text_message.encode('utf-8')
print(f"Encoded: {utf8_data}")

# 3. From an iterable of integers
# Useful for constructing specific byte patterns
numeric_data = bytes([72, 101, 108, 108, 111]) # [H, e, l, l, o]
print(f"From numbers: {numeric_data}")
```

Notice how Python displays the `utf8_data`. The ASCII parts (‘, world!’) are shown as characters for readability, but the non-ASCII Chinese characters are shown as hexadecimal escape sequences (`\xe4\xbd\xa0\xe5\xa5\xbd`). This is a convenient representation, but don’t let it fool you — under the hood, it’s all just numbers.

---

### The Integer Inside

Let’s revisit our initial example to prove the point.

```python
data = b'Protocol'

# Indexing a single item gives an integer
first_byte = data[0]
print(f"data[0] is {first_byte} (type: {type(first_byte)})") # 80 is ASCII for 'P'

# Slicing gives a new bytes object of length 1
first_byte_as_sequence = data[:1]
print(f"data[:1] is {first_byte_as_sequence} (type: {type(first_byte_as_sequence)})")
```

This is a critical distinction that often trips up beginners. `my_bytes[0]` is not the same as `my_bytes[:1]`. This behavior is consistent with all other Python sequences; a single item is not the same as a slice of length one. The `str` type is the odd one out where `s[0] == s[:1]`.

Because bytes are immutable, trying to change one will fail:

```python
data = b'immutable'
# data[0] = 102 # This will raise a TypeError!
```

---

### bytearray: The Mutable Sibling

What if you need to modify binary data in place? Maybe you’re reading from a network stream and need to build a message piece by piece, or you’re manipulating a binary file format. For this, Python gives us the `bytearray`.

The `bytearray` is to `bytes` what a list is to a tuple. It’s a mutable sequence of integers from 0 to 255.

```python
# Create a bytearray from a bytes object
mutable_data = bytearray(b'Initial packet')
print(f"Before: {mutable_data}")

# Modify a single byte using its integer value
# Let's change 'I' (73) to 'F' (70)
mutable_data[0] = 70
print(f"After modification: {mutable_data}")

# You can append and extend just like a list
mutable_data.append(33) # '!' is 33
mutable_data.extend(b' Extra')
print(f"After extending: {mutable_data}")
```

This mutability makes `bytearray` incredibly powerful for tasks that involve building binary sequences dynamically, without the performance overhead of creating new `bytes` objects for every small change.

---

### The str-like Façade: Methods and Operations

Here’s another source of confusion: both `bytes` and `bytearray` have many of the same methods as `str`. You’ll find `.upper()`, `.split()`, `.replace()`, `.startswith()`, and dozens more.

This is a convenience, allowing you to use familiar patterns to manipulate binary data that happens to contain text-like structures (like HTTP headers or configuration files with simple ASCII keys).

However, there is one golden rule: **the arguments to these methods must also be binary types.** You cannot mix `str` and `bytes`.

```python
http_header = b'Content-Type: text/html; charset=utf-8'

# This works beautifully
if http_header.startswith(b'Content-Type'):
    print("Found the content type header.")

# You can split and replace with bytes arguments
parts = http_header.split(b': ')
new_header = http_header.replace(b'text/html', b'application/json')

print(f"Header parts: {parts}")
print(f"New header: {new_header}")


# This will FAIL with a TypeError!
# if http_header.startswith('Content-Type'):
#    print("This line will never be reached.")
```

Furthermore, you won’t find methods that are intrinsically tied to the complexities of Unicode. Methods like `.casefold()`, `.isdecimal()`, or `.format()` do not exist on binary types, because those concepts don’t make sense for raw sequences of numbers.

---

### When Should You Use Them?

So when do you reach for `bytes` or `bytearray` instead of `str`?

1.  **Binary File I/O:** Any time you work with a non-text file — images, audio files, videos, PDFs, SQLite databases — you must open it in binary mode (‘rb’, ‘wb’, ‘ab’). The `read()` method will give you `bytes`, and `write()` will expect `bytes`.

    ```python
    # Read the first 8 bytes of a PNG file to check its signature
    with open('my_image.png', 'rb') as f:
        png_signature = b'\x89PNG\r\n\x1a\n'
        header = f.read(8)
        if header == png_signature:
            print("This looks like a valid PNG file.")
    ```

2.  **Networking:** All network communication, from low-level sockets to HTTP requests, is done with streams of bytes. Libraries like `socket` and `requests` handle the encoding and decoding for you, but at the lowest level, it’s all bytes.

3.  **Cryptography and Hashing:** Cryptographic algorithms operate on bytes, not text. If you want to hash a password or encrypt a message, you must first encode your string into a defined byte representation (usually UTF-8).

    ```python
    import hashlib

    password = "super-secret-p@ssw0rd"
    password_bytes = password.encode('utf-8')
    hashed = hashlib.sha256(password_bytes).hexdigest()
    print(f"SHA-256 Hash: {hashed}")
    ```

4.  **Interacting with C Libraries:** When using modules like `ctypes` or `cffi` to talk to C libraries, you will often need to pass data as pointers to raw byte buffers.

---

### Conclusion

Python 3’s strict separation of text (`str`) and binary data (`bytes`, `bytearray`) is not a burden; it’s a liberation. It forces us to be explicit about our data, eliminating a whole class of subtle and frustrating bugs.

The next time you see `b''`, don’t think of it as a “special string.” Think of it for what it truly is: an immutable sequence of numbers, a direct line to the binary heart of the machine. Embrace this distinction. Decode your inputs at the boundaries of your system, work with clean, abstract `str` throughout your application’s logic, and encode back to bytes only when you need to write to a file or send data across a network.

By mastering `bytes` and `bytearray`, you’re not just learning a new data type; you’re learning to speak the computer’s native language.