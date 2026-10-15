# Your Grammar Is a Sequence Pattern: Writing an Interpreter with `match`/`case`

#### Parse a tiny rules language into nested lists, and each rule of its grammar becomes one `case` clause, with guards doing the job of reserved keywords

**By Tihomir Manushev**

*Oct 15, 2026 · 9 min read*

---

The greenhouse controller started with a config file: water zone 3 for eight minutes when soil moisture drops below 35%. Then the growers asked for "unless the air is above 31 degrees", then for "half a minute per point of deficit, capped at fifteen". Each request added a key to the YAML and a branch to the Python that read it. After a year, the config format was a programming language with no grammar, and the code that read it was a pile of `if` statements.

The honest fix is to admit it's a language and give it a grammar. That sounds like a compiler course, but Python 3.10 made the hard part short. Once rule text is parsed into nested lists, a `match` statement can read the grammar straight off the shape of each list, one `case` per rule.

This article builds a small rules language called Trellis, whose whole evaluator is one `match` statement of eight cases. Along the way it covers why sequence patterns never match strings, why keyword forms need guards, the rule OR-patterns impose on the names they bind, the constant that silently captures everything, and what a `match` statement costs per node.

---

### From Text to Nested Lists

Trellis uses parenthesised prefix notation. `(- 40 soil)` means 40 minus the soil reading, and a rule is just one expression nested inside another. The parser's only job is to turn parentheses into lists, numbers into numbers and everything else into names:

```python
import re

type Expr = int | float | str | list[Expr]


def to_atom(token: str) -> int | float | str:
    """Read a token as an int, then a float, and fall back to a name."""
    for kind in (int, float):
        try:
            return kind(token)
        except ValueError:
            pass
    return token


def parse(source: str) -> list[Expr]:
    """Turn rule text into a list of top-level expressions."""
    source = re.sub(r";.*", "", source)
    stack: list[list[Expr]] = [[]]
    for token in re.findall(r"[()]|[^\s()]+", source):
        match token:
            case "(":
                stack.append([])
            case ")" if len(stack) > 1:
                finished = stack.pop()
                stack[-1].append(finished)
            case ")":
                raise SyntaxError("unexpected ')'")
            case _:
                stack[-1].append(to_atom(token))
    if len(stack) > 1:
        raise SyntaxError("missing ')'")
    return stack[0]


print(parse("(min 15 (* 0.5 (- 40 soil)))"))
# [['min', 15, ['*', 0.5, ['-', 40, 'soil']]]]
```

Comments start with `;` and are stripped first. The regex splits the text into parentheses and runs of anything else. The stack holds every list that is still open: `(` pushes a new one, `)` pops the finished list and appends it to its parent. The outermost list collects the top-level forms, so a rule file with three expressions parses into a list of three. The recursive `type Expr` alias, new in 3.12, says what comes out: an atom or a list of more `Expr`. That nested list *is* the abstract syntax tree, with no node classes needed. Even the parser uses `match`: a guard splits the `")"` literal into a close paren with a list to finish, and one without.

---

### One Case per Grammar Rule

Here's the whole grammar of Trellis, written as the evaluator that runs it:

```python
import operator
from collections.abc import Callable
from typing import Any

KEYWORDS = frozenset({"if", "unless", "and", "or", "let", "def"})

BUILTINS: dict[str, Callable[..., Any]] = {
    "+": operator.add, "-": operator.sub, "*": operator.mul,
    "/": operator.truediv, "<": operator.lt, ">": operator.gt,
    "<=": operator.le, ">=": operator.ge, "=": operator.eq,
    "not": operator.not_, "min": min, "max": max,
}


def to_source(exp: Expr) -> str:
    """Print an expression back as rule text, for error messages."""
    if isinstance(exp, list):
        return f"({' '.join(to_source(item) for item in exp)})"
    return str(exp)


def evaluate(exp: Expr, env: dict[str, Any]) -> Any:
    """Compute the value of one expression against an environment."""
    match exp:
        case int() | float():
            return exp
        case str(name):
            return env[name]
        case ["if", test, then, otherwise] | ["unless", test, otherwise, then]:
            branch = then if evaluate(test, env) else otherwise
            return evaluate(branch, env)
        case ["and" | "or" as op, *operands]:
            results = (evaluate(item, env) for item in operands)
            return all(results) if op == "and" else any(results)
        case ["let", [str(name), value], body]:
            return evaluate(body, env | {name: evaluate(value, env)})
        case ["def", str(name), value]:
            env[name] = evaluate(value, env)
        case [str(head), *args] if head not in KEYWORDS:
            func = evaluate(head, env)
            return func(*(evaluate(arg, env) for arg in args))
        case _:
            raise SyntaxError(f"malformed rule: {to_source(exp)}")
```

Read the cases top to bottom and you're reading the language reference. Numbers evaluate to themselves. A name is looked up in the environment, which holds the built-in functions and the sensor readings. `if` takes exactly three expressions, because the pattern has exactly four slots. `and` and `or` take any number of operands. `let` binds one name to one value for the duration of one body expression. `def` writes a name into the environment and returns `None`, the way an assignment statement produces no value. Anything else that starts with a name is a function call. Whatever is left is a syntax error.

The patterns also do validation that would otherwise be scattered `isinstance` checks. `["let", [str(name), value], body]` is a nested sequence pattern with a class pattern inside it: the binding must be a two-item list whose first item is a string. `(let (3 5) soil)` doesn't fit that shape, so it falls through every case and lands on `case _` with a readable message. Here it is running a real zone rule:

```python
def run(source: str, readings: dict[str, float]) -> Any:
    """Evaluate every top-level form and return the last value."""
    env = BUILTINS | readings
    result = None
    for exp in parse(source):
        result = evaluate(exp, env)
    return result


ZONE_RULES = """
; minutes of water for one greenhouse zone
(def target 40)
(let (deficit (- target soil))
  (if (or (> deficit 0) (> air 31))
      (min 15 (max 3 (* 0.5 deficit)))
      0))
"""

print(run(ZONE_RULES, {"soil": 22, "air": 27.5}))  # 9.0
print(run(ZONE_RULES, {"soil": 47, "air": 33.0}))  # 3
print(run(ZONE_RULES, {"soil": 47, "air": 24.0}))  # 0
print(run("(unless (> soil 30) 12 0)", {"soil": 18}))  # 12

for broken in ["(if (> soil 30) 12)", "(let (3 5) soil)", "(3 4)"]:
    try:
        run(broken, {"soil": 18})
    except SyntaxError as error:
        print(error)
# malformed rule: (if (> soil 30) 12)
# malformed rule: (let (3 5) soil)
# malformed rule: (3 4)
```

Dry soil gets nine minutes, wet soil on a hot afternoon gets the three-minute floor, and wet soil on a mild day gets nothing. The broken rules all reach `case _`: an `if` with no alternative, a `let` binding a number, and a call whose head isn't a name.

---

### Why Strings Never Look Like Lists

A Python `str` is a sequence: it has a length, and you can index and unpack it. If sequence patterns treated strings as sequences, the name `"soil"` would match `[str(head), *args]` as `head="s"`, `args=["o", "i", "l"]`, and every symbol would turn into a function call.

The language rules out that confusion. Sequence patterns match lists, tuples, `range` and anything registered as a `collections.abc.Sequence`, but they explicitly exclude `str`, `bytes` and `bytearray`:

```python
for subject in ["soil", ("max", 1, 2), ["max", 1, 2]]:
    match subject:
        case [head, *rest]:
            print(f"sequence: {head!r} {rest!r}")
        case _:
            print(f"not a sequence: {subject!r}")
# not a sequence: 'soil'
# sequence: 'max' [1, 2]
# sequence: 'max' [1, 2]
```

Tuples do match, and the star capture always binds a list. That exclusion is what makes `str` a safe type for symbols: atoms and compound forms get sorted for free.

---

### Keywords Need a Guard

The guard on the call case, `if head not in KEYWORDS`, looks redundant, since the keyword cases come earlier. It isn't, when the `if` is malformed. Take the guard away and watch where `(if (> soil 30) 12)` goes:

```python
def route(exp: Expr) -> str:
    """Say which case a form reaches when the call case has no guard."""
    match exp:
        case ["if", test, then, otherwise]:
            return "if-form"
        case [str(head), *args]:
            return f"call to {head!r}"
        case _:
            return "syntax error"


print(route(["if", [">", "soil", 30], 12]))  # call to 'if'
```

Three items don't fit the four-slot `if` pattern, so the form falls into the call case, and the evaluator would look up `"if"` in the environment. The grower sees `KeyError: 'if'`, which points at the wrong problem entirely. With the guard, a keyword can never be called like a function, so a broken keyword form falls through to `case _` and gets reported as what it is. That's the practical reason languages reserve keywords: a keyword form has its own evaluation rules, and it must never be mistaken for an ordinary call.

`and` shows those rules most clearly. A function receives its arguments already evaluated. The `and` case evaluates its operands lazily, through a generator that `all()` stops consuming at the first falsy value:

```python
print(run("(and (> soil 30) (/ 1 0))", {"soil": 18}))  # False
```

If `and` were an entry in `BUILTINS`, `(/ 1 0)` would run before `and` ever saw it, and the rule would raise `ZeroDivisionError`. Short-circuiting is only possible as a special form.

One more detail: guards run arbitrary code, and that code can raise. The obvious first version of the call case is `[head, *args] if head not in KEYWORDS`. A form like `((min 1) 2)` reaches it with a list as `head`, and the `frozenset` membership test fails with `TypeError: unhashable type: 'list'` before the pattern can reject anything. Writing `str(head)` moves the check into the pattern, where a mismatch simply means "try the next case".

---

### OR-Patterns Must Bind the Same Names

The `if` case carries a second form. `["if", test, then, otherwise] | ["unless", test, otherwise, then]` is an OR-pattern whose alternatives bind the same three names in different positions. `unless` puts the "otherwise" branch second, and the pattern swaps it back, so one body handles both keywords.

This works because of a rule the compiler enforces: every alternative of an OR-pattern must bind exactly the same set of names. The body runs whichever alternative matched, so every name it reads must exist on every path. Try to add a two-branch `when` the same way and the code doesn't compile:

```python
broken_case = """
match exp:
    case ["if", test, then, otherwise] | ["when", test, then]:
        pass
"""
try:
    compile(broken_case, "<rules>", "exec")
except SyntaxError as error:
    print(f"SyntaxError: {error.msg}")
# SyntaxError: alternative patterns bind different names
```

The fix is a separate case for `when`. OR-patterns without captures are free of this rule, which is why `"and" | "or" as op` is fine: the alternatives are literals, and the single `as` binding wraps the whole group.

---

### The Constant That Captures Everything

A tidy reviewer will pull the bare `"if"` strings into constants. That turns the evaluator into a trap:

```python
IF = "if"


def classify(exp: Expr) -> str:
    """Spot an if-form, using a constant for the keyword."""
    match exp:
        case [IF, test, then, otherwise]:
            return f"if-form, and IF is now {IF!r}"
        case _:
            return "something else"


print(classify(["max", 3, 9, 4]))  # if-form, and IF is now 'max'
print(IF)  # if
```

A bare name in a pattern is a **capture pattern**: it matches anything and binds it. It never compares. Every four-item list is now an `if`, and inside the function `IF` is a local variable holding `"max"`. Python catches the obvious version: a bare name as the whole pattern of any case but the last raises `SyntaxError: name capture 'IF' makes remaining patterns unreachable`. Nested inside a sequence, it's perfectly legal. Patterns compare against a value only when the name is dotted, so constants belong on a class or an enum:

```python
from enum import StrEnum


class Keyword(StrEnum):
    """Reserved words of the rules language."""

    IF = "if"


def classify_dotted(exp: Expr) -> str:
    """Spot an if-form, comparing against a dotted constant."""
    match exp:
        case [Keyword.IF, test, then, otherwise]:
            return "if-form"
        case _:
            return "something else"


print(classify_dotted(["max", 3, 9, 4]))  # something else
print(classify_dotted(["if", 1, 2, 3]))  # if-form
```

`Keyword.IF` is a value pattern, compared with `==`, and a `StrEnum` member equals its string.

---

### What a `match` Statement Costs

`match` isn't a jump table. Running `dis` on `evaluate` shows each sequence case compiled to its own chain: `MATCH_SEQUENCE` checks the type, `GET_LEN` and a comparison check the length, `UNPACK_SEQUENCE` spreads the items, and only then does a literal like `"if"` get compared. A failed case falls through to the next, which repeats the checks from scratch. Evaluating one node costs O(k), where k is the number of cases tried before one matches, and a rule with n nodes costs O(n·k).

That makes case order a performance question, and in Trellis the most common compound node, the function call, sits last. Because its guard keeps keywords out, it can move to the top without changing what any rule means:

```python
import timeit


def evaluate_calls_first(exp: Expr, env: dict[str, Any]) -> Any:
    """The same evaluator with the call case moved to the top."""
    match exp:
        case [str(head), *args] if head not in KEYWORDS:
            func = evaluate_calls_first(head, env)
            return func(*(evaluate_calls_first(arg, env) for arg in args))
        case int() | float():
            return exp
        case str(name):
            return env[name]
        case ["if", test, then, otherwise] | ["unless", test, otherwise, then]:
            branch = then if evaluate_calls_first(test, env) else otherwise
            return evaluate_calls_first(branch, env)
        case ["and" | "or" as op, *operands]:
            results = (evaluate_calls_first(item, env) for item in operands)
            return all(results) if op == "and" else any(results)
        case ["let", [str(name), value], body]:
            bound = {name: evaluate_calls_first(value, env)}
            return evaluate_calls_first(body, env | bound)
        case ["def", str(name), value]:
            env[name] = evaluate_calls_first(value, env)
        case _:
            raise SyntaxError(f"malformed rule: {to_source(exp)}")


rule = parse("(min 15 (max 3 (* 0.5 (- 40 soil))))")[0]
sensor_env = BUILTINS | {"soil": 22}
for evaluator in (evaluate, evaluate_calls_first):
    timings = timeit.repeat(
        lambda: evaluator(rule, sensor_env), number=100_000, repeat=7
    )
    print(f"{evaluator.__name__}: {min(timings) * 10:.2f} µs per rule")
# evaluate: 12.60 µs per rule
# evaluate_calls_first: 10.55 µs per rule
```

On Python 3.12.3 the reordered evaluator was about 16% faster on this call-heavy rule, and repeated runs stayed between 15% and 19%. The absolute numbers will differ on your machine; the ratio is the point. Profile your own rule files before reordering, because a language whose programs are mostly `let` and `if` would favour the original order.

Two other costs are worth knowing. `env | {...}` in `let` copies the whole environment, O(size of env) per binding: fine for a dozen sensors, wasteful for thousands of names. And `evaluate` recurses once per nesting level, and each level costs two frames: the call to `evaluate` and the generator expression feeding the function its arguments. With the default recursion limit of 1,000, a rule nested about 500 calls deep raises `RecursionError`. Hand-written rules never get there, but generated ones can.

---

### Conclusion

A parsed program is nested lists, and a `match` statement can describe nested lists by shape, so the grammar of a small language and the evaluator for it end up being the same piece of code. Sequence patterns give each form its arity, class patterns like `str(name)` check the types of its parts, and `case _` is where syntax errors go. Guards keep keyword forms from being treated as calls, which is the whole reason reserved words exist. OR-patterns must bind the same names in every alternative, bare names capture instead of comparing, and case order is a real performance setting. The next time a config format starts growing conditionals, give it a grammar instead. In Python, the evaluator is one `match` statement.
