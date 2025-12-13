# Playing with Fire: The Hidden Dangers of Python’s Default Encodings
#### Why your “works on my machine” Python script fails on other computers, and how to fix it for good

**By Tihomir Manushev**  
*Nov 1, 2025 · 7 min read*

---

It’s a story every developer knows. You write a piece of brilliant code. It reads from a file, processes some text, and saves the result. It works flawlessly on your machine. You run the tests, you commit the code, you push it to production or hand it off to a colleague.

And then you get the bug report.

On your colleague’s machine, the script doesn’t just fail; it produces utter nonsense. The beautiful “résumé” you saved comes out as “rÃ©sumÃ©”. Or worse, the whole program crashes with a UnicodeDecodeError. You stare at their screen, baffled. “But… it works on my machine!”

Friend, you haven’t been bitten by a mysterious bug. You’ve just been burned by one of Python’s most common and treacherous hidden dangers: the default encoding. Relying on it is like playing with fire. It feels fine until your whole application goes up in flames.

---

### The Scene of the Crime: An Invisible Bug

Let’s dissect a simple case. Imagine you’re writing a script to save a single, simple word to a file: “café”.

You’re on your shiny new MacBook, and you write this perfectly reasonable code:

```python
# writer.py
with open('cafe.txt', 'w') as f:
    f.write('café')
```

You run it. No errors. You then write a second script to read it back.

```python
# reader.py
with open('cafe.txt', 'r') as f:
    content = f.read()
    print(content)
```

You run reader.py, and your terminal dutifully prints café. Perfection. You zip up the folder and send it to your colleague, who happens to use a Windows machine.

They run writer.py. No errors. Then they run reader.py, and their screen shows this abomination:

```
cafÃ©
```

What just happened? The code is identical. The input was the same. The only difference was the computer it ran on. The culprit is an argument you didn’t pass to the open() function: the encoding argument.

When you don’t specify an encoding, Python is forced to guess. And its guess is based on a tangled web of system settings, operating system history, and locale configurations. You didn’t just write a file; you wrote a file in your machine’s “native language.” Your colleague’s machine spoke a different one.

---

### A Tale of Two Worlds: The UTF-8 Bubble vs. The Code Page Jungle

The reason this bug is so insidious is that it often stays hidden for developers on Linux and macOS. For the better part of a decade, these platforms have wisely standardized on UTF-8 as their default encoding.

UTF-8 is the de facto standard of the modern internet. It can represent every single character in the Unicode standard — from ‘A’ to ‘é’ to ‘😂’ — making it a robust and universal choice.

If you run this script on a typical Linux or macOS system, you’ll likely see this:

```python
# check_defaults.py
import sys
import locale

print(f"Default for opening files: {locale.getpreferredencoding()}")
print(f"Default for stdout:        {sys.stdout.encoding}")
```

Life is good. The default for opening files is UTF-8. The default for printing to the terminal is UTF-8. As long as you stay within this cozy ecosystem, you’re living in a bubble of safety. You can forget to specify `encoding='utf-8'`, and everything will probably just work.

Now, let’s run that exact same script on a standard US-English Windows machine:

**Output on Windows:**

```
Default for opening files: cp1252
Default for stdout:        utf-8
```

Hold on. cp1252? What’s that?

Welcome to the jungle of code pages. cp1252, or Windows-1252, is a legacy encoding from a time before Unicode was dominant. It’s great at handling English and most Western European languages, but it’s a tiny subset of what UTF-8 can do. It has no concept of Japanese characters, most emojis, or countless other symbols.

This is the source of our bug.

1.  On the Mac, `writer.py` ran with a default encoding of UTF-8. It wrote the bytes `b’caf\xc3\xa9'` to the file. (In UTF-8, ‘é’ is represented by two bytes, C3 and A9).
2.  On Windows, when `reader.py` ran, it used its default, cp1252. It read the two bytes `\xc3` and `\xa9`.
3.  According to the cp1252 map, the byte `\xc3` corresponds to the character ‘Ã’.
4.  The byte `\xa9` corresponds to the character ‘©’ (the copyright symbol). Wait, that’s not what happened in the example! Ah, but it seems in my colleague’s terminal, the display might have rendered it differently, as the é part of Ã©. This kind of garbled output is what we call *mojibake*.

The computer did exactly what it was told. It just got two different sets of instructions because we let it guess.

---

### The Problem Goes Deeper: Standard Output Isn’t Safe Either

You might think, “Okay, I’ll just be careful with files.” But the danger extends to something as simple as `print()`.

As our `check_defaults.py` script showed, modern Windows terminals (like Windows Terminal and PowerShell) have adopted UTF-8 for their standard input/output streams. This is a huge improvement! But it introduces a bizarre inconsistency.

Consider this script, which tries to print a few characters. One exists in cp1252, one exists in an old DOS code page (cp437), and one exists in neither.

```python
# stdout_check.py
import sys

print(f"Is stdout a terminal? {sys.stdout.isatty()}")
print(f"Stdout encoding:       {sys.stdout.encoding}")
print("-" * 20)

# HORIZONTAL ELLIPSIS (…), exists in cp1252
print("Trying to print …")

# INFINITY (∞), does NOT exist in cp1252
print("Trying to print ∞")
```

If you run this directly in a Windows PowerShell terminal, it works beautifully:

```
Is stdout a terminal? True
Stdout encoding:       utf-8
--------------------
Trying to print …
Trying to print ∞
```

Because stdout is an interactive terminal (`isatty()` is True), Python 3.6+ uses UTF-8. Hooray!

But now, for the horrifying plot twist. Let’s redirect that output to a file, a common practice for logging.

```bash
python stdout_check.py > output.log
```

The script now crashes.

```
Is stdout a terminal? False
Stdout encoding:       cp1252
--------------------
Trying to print …
Traceback (most recent call last):
  File "C:\stdout_check.py", line 12, in <module>
    print("Trying to print ∞")
UnicodeEncodeError: 'charmap' codec can't encode character '\u221e' in position 16: character maps to <undefined>
```

Look closely at the output. When we redirected to a file, `sys.stdout.isatty()` became False. Python saw that it was no longer writing to an interactive terminal, so it fell back to the system’s default file encoding: cp1252. And cp1252 has no idea what an infinity symbol is.

This is maddening. The exact same script can either succeed or fail based entirely on how it is executed. This is the definition of a fragile system.

---

### The Golden Rule: Always Be Explicit

By now, the solution should be screamingly obvious. The only way to win this game is not to play. Don’t let Python guess. Always tell it what you want.

The fix to our original problem is a single, simple addition:

```python
# writer_fixed.py
with open('cafe.txt', 'w', encoding='utf-8') as f:
    f.write('café')

# reader_fixed.py
with open('cafe.txt', 'r', encoding='utf-8') as f:
    content = f.read()
    print(content)
```

This code is now robust. It will work identically on Linux, macOS, and Windows. It will work today, and it will work in five years. We have removed the ambiguity and replaced it with a clear, explicit instruction. UTF-8 is the lingua franca of modern computing; use it everywhere unless you have a very specific, documented reason not to (like interacting with a legacy system that demands cp1252).

Treating the encoding argument as mandatory, not optional, will save you from entire classes of bugs. It will make your code more portable, more predictable, and more professional.

Stop letting your programs play with fire. It’s a fun way to get warm, but a terrible way to build a house. Be explicit. Your future self — and your colleagues — will thank you.

---

### Conclusion

The “it works on my machine” syndrome is often a symptom of a deeper problem: hidden environmental dependencies. Python’s default encodings are a prime example. While well-intentioned, they create a dangerous rift between different operating systems and even different execution contexts on the same machine. By understanding where these defaults come from — the UTF-8 bubble of the Unix-like world versus the legacy code page jungle of Windows — we can diagnose and prevent these frustrating bugs. The solution is simple but profound: adopt the discipline of always specifying `encoding='utf-8'` when dealing with text files. This single habit transforms fragile, platform-dependent code into a robust, portable, and professional application.