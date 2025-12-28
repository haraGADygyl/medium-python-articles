# Debugging Python Scope with Bytecode Disassembly
#### LOAD_FAST_CHECK vs. LOAD_GLOBAL

**By Tihomir Manushev**  
*Dec 23, 2025 · 7 min read*

---

One of the most baffling experiences for an intermediate Python developer is encountering the `UnboundLocalError`. It usually happens like this: you have a script working perfectly, reading a global configuration variable. You decide to add a line of logic that updates that variable inside a function. Suddenly, the code that previously worked — the line strictly reading the variable — crashes.

It feels like a paradox. How can a line of code fail based on something that happens after it?

To the casual observer, Python appears to be an interpreted language that executes line-by-line. If that were strictly true, the interpreter wouldn’t know about the assignment on line 10 while executing line 2. The crash proves that Python does more than just interpret; it compiles.

To understand why Python makes these decisions, we cannot rely on intuition. We must look at the “assembly” of the Python Virtual Machine (PVM). In this article, we will use the `dis` module to dismantle CPython’s scoping rules and prove that variable scope is determined at compile time, not runtime.

---

### The Paradox of the “Local” Global

Let’s look at a concrete example. We have a simple script that manages a database connection timeout. We define a global default, and we have a function that logs the current timeout.

```python
DB_TIMEOUT = 30  # Module-level global

def log_current_status():
    print(f"Current timeout setting: {DB_TIMEOUT}")

log_current_status()
```

If you run this, it works as expected. The function looks for `DB_TIMEOUT` in its local scope, fails to find it, searches the global scope, finds 30, and prints it.

Now, requirements change. We want the function to toggle the timeout to a “safe mode” after logging the current status. We add one line:

```python
DB_TIMEOUT = 30

def log_and_update():
    print(f"Current timeout setting: {DB_TIMEOUT}") # Line A
    DB_TIMEOUT = 5                                  # Line B

log_and_update()
```

This error message reveals a crucial implementation detail. Python does not say `NameError: name ‘DB_TIMEOUT’ is not defined`. It says the variable is local, but it hasn’t been assigned a value yet.

This means that before the function even ran, Python decided that `DB_TIMEOUT` belonged to the local scope, shielding it from the global variable of the same name. Because the assignment (Line B) hasn’t happened when Line A executes, the local variable slot is empty.

To see exactly how Python came to this conclusion, we need to inspect the bytecode.

---

### The Disassembler: dis

The `dis` module allows us to view the human-readable instructions that the CPython compiler generates from our source code. These instructions, or opcodes, are what the Python stack machine actually executes.

Let’s look at the bytecode for the version of the function that worked (`log_current_status`), where we only read the variable.

```python
import dis

DB_TIMEOUT = 30

def log_current_status():
    print(f"Current timeout setting: {DB_TIMEOUT}")

print("--- Bytecode for Global Read ---")
dis.dis(log_current_status)
```

Focus on offset 14 `LOAD_GLOBAL`.

When Python compiles this function, it scans the function body. It sees `DB_TIMEOUT` is referenced, but never assigned. Therefore, it emits the `LOAD_GLOBAL` opcode.

At runtime, `LOAD_GLOBAL` tells the interpreter: “Go look in the module’s dictionary (`__dict__`) for a key named `DB_TIMEOUT`.” This is a hash map lookup. It works, and the value 30 is retrieved.

---

### The “Hybrid” Failure

Now, let’s disassemble the broken function (`log_and_update`), where we attempt to print the variable and then assign to it.

```python
import dis

DB_TIMEOUT = 30

def log_and_update():
    print(f"Current timeout setting: {DB_TIMEOUT}")
    DB_TIMEOUT = 5

print("\n--- Bytecode for Local Crash ---")
dis.dis(log_and_update)
```

Look closely at offset 14. It has changed from `LOAD_GLOBAL` to `LOAD_FAST_CHECK`.

Also, notice offset 32, where the assignment happens: `STORE_FAST`.

---

### The Compiler’s Logic

This output proves that scope determination is a compile-time event. Here is the sequence of events inside the CPython compiler:

1.  **Parsing:** The compiler parses the source code of `log_and_update` into an Abstract Syntax Tree (AST).
2.  **Symbol Table Generation:** The compiler walks the AST to build a symbol table. It notes every variable name used in the block.
3.  **Scope Determination:** It sees the assignment `DB_TIMEOUT = 5`.
4.  **Rule:** If a name is assigned anywhere within a function block (and is not explicitly declared `global` or `nonlocal`), it is treated as local to that block. Crucially, this decision applies to the entire block, not just the lines following the assignment.
5.  **Bytecode Emission:** Because `DB_TIMEOUT` is flagged as local, the compiler uses `LOAD_FAST_CHECK` for the read and `STORE_FAST` for the write.

---

### Why LOAD_FAST Crashes

When the function actually runs:

1.  It hits offset 14 `LOAD_FAST_CHECK 0`.
2.  `LOAD_FAST_CHECK` is an optimized opcode. It doesn’t check the dictionary where the global variables are stored. It checks a specific slot in a C-array attached to the stack frame.
3.  Python checks the slot at index 0. It finds it empty (it hasn’t been written to yet).
4.  Because the slot is empty, it raises `UnboundLocalError`.

It does not fall back to checking globals. `LOAD_FAST_CHECK` implies “I know this is local; if it’s not here, it’s nowhere.”

---

### Forcing the Issue: The global Keyword

If our intention was to update the module-level variable, we must explicitly tell the compiler to opt out of this default behavior using the `global` keyword.

```python
import dis

DB_TIMEOUT = 10

def log_and_update_fixed():
    global DB_TIMEOUT
    print(f"Current timeout setting: {DB_TIMEOUT}")
    DB_TIMEOUT = 5

print("\n--- Bytecode for Local Crash ---")
dis.dis(log_and_update_fixed)
```

The presence of the `global` declaration changed the symbol table generation phase. The compiler now knows that despite the assignment, `DB_TIMEOUT` should be treated as global. Consequently:

*   The read at offset 14 uses `LOAD_GLOBAL`.
*   The assignment at offset 40 uses `STORE_GLOBAL`.

This function will now successfully print “30” and then update the module-level `DB_TIMEOUT` to “5”.

---

### Why Does Python Do This?
#### 1. The Speed of LOAD_FAST_CHECK

You might wonder why Python assumes variables are local by default. Why not check the local scope, and if it’s missing, fall back to global? (This is known as dynamic scoping, or at least a variation of it).

The answer lies in Performance and Safety.

In CPython, global variables are stored in a dictionary (`__dict__`). Local variables are stored in a fixed-size array.

*   **LOAD_GLOBAL:** Requires hashing the variable name, resolving hash collisions, and searching the dictionary. It is relatively slow.
*   **LOAD_FAST_CHECK:** Uses an integer index to access an array directly. It is essentially a pointer offset in C. It is blazingly fast.

Since most code inside functions operates on local variables, Python optimizes for the common case. By deciding at compile time which variables are locals, Python can compile them into these rapid array lookups. If Python had to check for a global every time a local wasn’t initialized yet, every local variable access would incur the overhead of a “maybe global” check.

#### 2. Predictability (Lexical Scoping)

Python uses Lexical Scoping (also called Static Scoping). This means you can determine the scope of a variable just by reading the code text, without needing to know the caller’s state.

If `DB_TIMEOUT` wasn’t implicitly local, we might accidentally overwrite a global variable we didn’t know existed just by assigning `DB_TIMEOUT = 5` in a helper function. By assuming assignment implies locality, Python prevents functions from side-effecting globals unless the programmer explicitly requests it (with `global`).

---

### Conclusion

The `UnboundLocalError` is not a quirk of the interpreter confusing the order of lines; it is the result of a rigorous compilation process designed for optimization. By using the `dis` module, we can pull back the curtain and see the specific opcodes, `LOAD_FAST_CHECK` versus `LOAD_GLOBAL`, that dictate program behavior.

Understanding these internals transforms the way you debug. You stop looking for typos in the line number reported by the crash and start looking for assignments further down the function body that are “shadowing” your variable. It highlights the beauty of Python’s design: a dynamic language that leverages static analysis to gain performance and safety.
