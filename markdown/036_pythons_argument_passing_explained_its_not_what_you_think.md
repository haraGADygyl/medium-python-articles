# Python’s Argument Passing Explained: It’s Not What You Think
#### Unraveling the mystery of Python’s memory model, why it confuses C++ developers, and how to avoid the dreaded mutable default argument bug

**By Tihomir Manushev**  
*Nov 21, 2025 · 8 min read*

---

If you have ever sat through a technical interview for a Python role, you have likely faced the dreaded question: “Is Python pass-by-value or pass-by-reference?”

It is a trap.

If you answer “pass-by-value,” the interviewer will ask you to explain why a list modified inside a function changes outside of it. If you answer “pass-by-reference,” they will ask why reassigning a number inside a function doesn’t change the original variable.

The confusion stems from the fact that Python doesn’t strictly fit the definitions used by older languages like C++ or Pascal. To truly understand Python, we have to abandon the “variable as a box” mental model and embrace a third way.

We call this “Call by Sharing.”

---

### The “Box” vs. The “Label”

To understand how arguments are passed, we first need to understand what a variable actually is in Python. In many statically typed languages, a variable is a box in memory. If you say `int a = 10;`, you are finding a box, labeling it `a`, and putting the value 10 inside it. If you assign `b = a`, you copy the value 10 into a new box labeled `b`.

In Python, variables are not boxes. They are labels (or name tags) attached to objects.

When you write `a = 10`, Python creates an integer object with the value 10 somewhere in memory, and then ties the name tag `a` to it. If you then write `b = a`, you aren’t copying the number. You are simply tying a second name tag, `b`, to the same object.

This distinction — variables as references to objects rather than containers of data — is the key to unlocking “Call by Sharing.”

---

### The Illusion of Pass-by-Value (Immutable Types)

Let’s look at a scenario that often convinces beginners that Python is pass-by-value. This usually involves immutable types like integers, strings, or tuples.

Imagine we want to write a function that adds a bonus to a player’s score.

```python
def add_bonus(score):
    print(f"Inside function (before): score = {score}, id = {id(score)}")
    score += 50
    print(f"Inside function (after):  score = {score}, id = {id(score)}")

current_score = 100
print(f"Outside (before): score = {current_score}, id = {id(current_score)}")

add_bonus(current_score)

print(f"Outside (after):  score = {current_score}, id = {id(current_score)}")
```

What happened here?

1.  We created an integer object 100 and tagged it `current_score`.
2.  We passed `current_score` to the function. The function parameter `score` became an alias for the exact same object. Notice the IDs are identical at the start.
3.  We executed `score += 50`.
4.  Here is the trick: Integers are immutable. You cannot change the number 100 into 150. So, Python created a new object 150.
5.  The local variable `score` was ripped off the old object (100) and slapped onto the new object (150).
6.  The function ends. The local label `score` disappears.
7.  The outer label `current_score` is still attached to the original object 100.

To a Java or C developer, this looks like “Pass-by-Value” (the function got a copy). But it wasn’t a copy; it was a shared reference that got rebound because the object couldn’t be changed.

---

### The Illusion of Pass-by-Reference (Mutable Types)

Now, let’s look at the scenario that confuses the previous group. What happens if we pass a mutable object, like a list representing a shopping cart?

```python
def add_groceries(cart):
    print(f"Inside function (before): {cart}, id = {id(cart)}")
    cart.append("Milk")
    print(f"Inside function (after):  {cart}, id = {id(cart)}")

my_cart = ["Bread", "Eggs"]
print(f"Outside (before): {my_cart}, id = {id(my_cart)}")

add_groceries(my_cart)

print(f"Outside (after):  {my_cart}, id = {id(my_cart)}")
```

What happened here?

1.  We created a list object. `my_cart` refers to it.
2.  We passed `my_cart` to the function. The parameter `cart` becomes an alias for the same object.
3.  We called `cart.append(“Milk”)`.
4.  Lists are mutable. Python does not create a new list. It goes to the memory address 134371132230464 and modifies the object directly.
5.  Because `my_cart` and `cart` refer to the exact same object, the change is visible outside the function.

To a C++ developer, this looks exactly like “Pass-by-Reference.”

---

### Defining “Call by Sharing”

So, is Python inconsistent? Does it change its rules based on the variable type?

No. The rules are exactly the same in both cases.

The rule is: **Functions receive a copy of the reference to the object.**

This strategy is formally known as Call by Sharing (a term coined by Barbara Liskov for the CLU language in the 1970s).

*   “Sharing” means the function parameter and the outside variable share the same object.
*   However, the parameter is a copy of the reference, not the reference itself.

This leads us to the most important distinction in Python parameter passing: Mutation vs. Reassignment.

---

### The “Reassignment” Gotcha

If Python were truly “Pass-by-Reference” (like C++ `int &x`), we should be able to write a function that completely replaces the object inside the variable for the caller.

Let’s try to write a function that wipes our shopping cart by assigning a new empty list to it.

```python
def wipe_cart(cart):
    # We are trying to replace the object entirely
    cart = [] 
    print(f"Inside wipe_cart: {cart}, id = {id(cart)}")

shopping_list = ["Apples", "Bananas"]
wipe_cart(shopping_list)

print(f"Outside: {shopping_list}, id = {id(shopping_list)}")
```

It didn’t work. The shopping list outside is still full.

Why?

When we wrote `cart = []` inside the function, we did not overwrite the memory at address 126812667169600. We created a new list at 126812667171328, and we moved the local label `cart` to point to this new list.

The outer label `shopping_list` is just sitting there, still pointing to the original list. Rebinding a variable inside a function has zero effect on the variable outside the function.

Compare this to the append example earlier.

*   `cart.append(…)` modifies the object. The changes stick.
*   `cart = …` modifies the label. The changes are local.

---

### Visualizing the Difference

If you are struggling to visualize this, imagine a shared Google Doc.

*   **Pass-by-Value:** I download the Google Doc as a PDF and email it to you. You can draw all over that PDF, but my original Google Doc remains untouched.
*   **Call by Sharing (Python):** I send you the URL (the reference) to the Google Doc.
*   **Mutation:** You open the link and type a new paragraph. I see that paragraph immediately. We are sharing the document.
*   **Reassignment:** You decide you don’t like my document. You create a new blank Google Doc in your browser. Now you are looking at your new doc, and I am looking at my old doc. You didn’t delete my doc; you just stopped looking at it.

---

### Dangerous Defaults: A Side Effect of Sharing

Understanding Call by Sharing helps explain one of Python’s most infamous bugs: the Mutable Default Argument.

You might have seen code like this, intending to create a profile for a student with an optional list of courses.

```python
class StudentProfile:
    def __init__(self, name, courses=[]):
        self.name = name
        self.courses = courses

    def add_course(self, course):
        self.courses.append(course)

# Let's create Alice
alice = StudentProfile("Alice")
alice.add_course("Math 101")

# Let's create Bob, who hasn't enrolled yet
bob = StudentProfile("Bob")
bob.add_course("History 202")

print(f"Alice's courses: {alice.courses}")
print(f"Bob's courses:   {bob.courses}")
```

Wait, why is Alice taking History? And why does Bob have Math credit?

This happens because the default value `[]` is created once when the function is defined (when Python reads the file), not every time the function is called.

Because Python passes references, every `StudentProfile` that doesn’t provide a list gets a reference to that same pre-created list. When Alice appends to it, she is mutating the shared object. When Bob appends to it, he is mutating that same object.

If `courses` were an immutable tuple, this wouldn’t happen (because you can’t append to a tuple). This bug only exists because of the intersection of Call by Sharing and Mutability.

---

### Defensive Programming

Now that we know function arguments are aliases, we must code defensively. If your function accepts a mutable object (like a list or dict), ask yourself: Does the caller expect me to change this?

If the answer is “No,” or “I’m not sure,” you should create a copy.

The Dangerous Way:

```python
def normalize_data(data_list):
    # Modifies the list in place! 
    # The caller might not be happy if they needed the original data.
    for i in range(len(data_list)):
        data_list[i] = data_list[i].strip().lower()
    return data_list
```

The Safe Way:

```python
def normalize_data(data_list):
    # Create a local copy
    local_data = list(data_list) 
    # Or utilize list comprehensions which create new lists automatically
    return [item.strip().lower() for item in local_data]  
```

By making a copy, you break the link between the internal variable and the external one. You can mutate `local_data` to your heart’s content without affecting the rest of the program.

---

### Conclusion

The debate between “Pass-by-Value” and “Pass-by-Reference” in Python is a false dichotomy. Python uses Call by Sharing.

It is a mechanism that is consistent, predictable, and powerful — once you stop thinking of variables as boxes. Remember:

*   Variables are labels on objects.
*   Functions receive copies of these labels.
*   If the object is mutable, changes made through the label will be seen globally.
*   If you reassign the label (using `=`), you are only changing the local reference, breaking the link to the original object.

Understanding this distinction distinguishes the master Pythonista from the apprentice. It prevents “spooky action at a distance” bugs and explains why your lists sometimes act like they are haunted.