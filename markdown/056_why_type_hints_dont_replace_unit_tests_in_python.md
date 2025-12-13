# Why Type Hints Don’t Replace Unit Tests in Python
#### Why the green checkmark of your type checker is a false prophet, and how to reclaim actual software reliability through behavioral testing

**By Tihomir Manushev**  
*Dec 12, 2025 · 7 min read*

---

There is a seduction in the green checkmark. When we run mypy or pyright across a sprawling codebase and receive that dopamine-inducing “Success: no issues found,” we feel a profound sense of security. We feel that because our variables are annotated and our interfaces are aligned, our software is correct.

This is the great lie of modern Python development.

Don’t get me wrong — I am a staunch advocate for static analysis. I would not start a new project without strict type checking enabled. However, as we embrace Gradual Typing in Python, a dangerous mindset has emerged: the belief that if the types line up, the logic is sound. This fallacy, often imported from the “If it compiles, it works” philosophy of languages like Haskell or Rust, does not hold up in Python’s runtime environment.

Type hints verify the grammar of your code. Unit tests verify the story. You can write a grammatically perfect sentence that is complete nonsense. In this article, we will dismantle the illusion of safety provided by type hints and explore why behavioral testing remains the non-negotiable bedrock of software reliability.

---

### The Semantics vs. Syntax Gap

Type checkers operate on a simplified model of your program. They check for consistency, not correctness. They ensure that if a function asks for a `User` object, you aren’t passing it a `Toaster` object. This eliminates a specific class of bugs — `AttributeError`, `TypeError` — which is valuable.

However, business logic rarely lives in the types of the data; it lives in the values and the transformations of that data. A type checker cannot tell you that you calculated a tax rate of 150% instead of 15%. It cannot tell you that you deleted the production database instead of the staging one, provided the database connection object was of the correct class.

---

### The “Zero” Blind Spot

Let’s look at a classic example where the type system smiles while the application crashes. Mathematical operations are notoriously difficult to type-check for safety because the validity of the operation depends on the runtime value, not the static type.

```python
def calculate_growth_metric(current: float, previous: float) -> float:
    """
    Calculates the year-over-year growth ratio.
    """
    return (current - previous) / previous
```

From the perspective of a static type checker, this function is impeccable.

1.  It accepts two floats.
2.  It performs subtraction (valid for floats).
3.  It performs division (valid for floats).
4.  It returns a float.

> Mypy Report: Success: no issues found in 1 source file

Now, let’s run it in the real world where a new product launch has no previous data:

```python
calculate_growth_metric(100.0, 0.0)
```

The application crashed. The type system failed to protect us because `0.0` is a perfectly valid float. The constraint here is not “must be a float,” it is “must be a float not equal to zero.” While we can theoretically create distinct types for `NonZeroFloat`, it introduces immense friction. A simple unit test would have caught this immediately.

---

### The Boundary Problem: Where Types Lie

The illusion of safety is most dangerous at the boundaries of your application — the I/O layer. When your Python code interacts with the outside world (API payloads, database rows, user input), static analysis is effectively flying blind.

Type checkers analyze the code inside your `.py` files. They cannot see the JSON coming from an HTTP request. When we annotate data entering our system, we are often just promising the type checker that the data looks a certain way. If we are wrong, the type checker propagates that lie throughout the entire codebase.

Consider a payment processing system that ingests a transaction payload:

```python
import json

def process_transaction(raw_json: str) -> None:
    # We tell the type checker: "Trust me, this is a dict with string keys and int values"
    payload: dict[str, int] = json.loads(raw_json)
    
    # The type checker sees 'amount' as an int because we said so.
    amount = payload["amount"] 
    perform_transfer(amount)

def perform_transfer(value: int) -> None:
    print(f"Transferring ${value}")

# The Reality at Runtime:
bad_data = '{"amount": "100.50"}' # It's a string, not an int
process_transaction(bad_data)
```

In this scenario:

1.  `json.loads` returns `Any` (or a recursive type structure that is hard to pin down).
2.  We explicitly hinted `payload` as `dict[str, int]`.
3.  The type checker trusts us. It assumes `payload["amount"]` is an `int`.
4.  It allows the call to `perform_transfer` because `int` matches the signature.

**Runtime Result:**
The code might crash, or worse, behave unpredictably depending on what `perform_transfer` does with that string. If `perform_transfer` did math, it might crash. If it did string formatting or concatenation, it might succeed but produce corrupted data (e.g., `"100.50" * 2` becomes `"100.50100.50"` instead of `201.0`).

Type hints at the I/O boundary are documentation, not enforcement. Only runtime validation (tests or parsing libraries) can ensure safety here.

---

### Logic errors are invisible to Types

The most insidious bugs are not crashes; they are silent logic errors. These occur when the state of the program changes in a way that violates business rules, even if it adheres to type rules.

Imagine a specialized generic container for a logistical shipment chain. We want to ensure that we only process items that are in a ‘pending’ state.

```python
from dataclasses import dataclass
from typing import Literal

Status = Literal['PENDING', 'SHIPPED', 'DELIVERED']

@dataclass
class Shipment:
    id: str
    status: Status
    contents: list[str]

def archive_shipment(shipment: Shipment) -> None:
    if shipment.status == 'PENDING':
        # LOGIC ERROR: We are archiving pending shipments! 
        # Business rule says: Only archive DELIVERED shipments.
        _save_to_cold_storage(shipment)

def _save_to_cold_storage(s: Shipment) -> None:
    print(f"Archiving {s.id}")
```

Reviewing `archive_shipment` with a type checker yields no errors.

1.  `shipment.status` is compared to a string literal that exists in the `Status` type definition.
2.  The argument types are correct.

However, the code is logically catastrophic. We are throwing away active orders. Static analysis cannot know your company’s policy on shipment archival. It only knows that ‘PENDING’ is a valid string for that field.

---

### Best Practice: The Hybrid Approach
#### 1. The Implementation (with Types)

The goal of a Senior Engineer is not to choose between types and tests, but to understand the domain of each. Use type hints to structure your data and enforce architectural boundaries. Use unit tests to verify behavior, data transformations, and edge cases.

Here is how we rewrite the “Growth Metric” example using a robust, production-grade approach that leverages both.

We keep the types, but we handle the runtime edge case explicitly.

```python
def calculate_roi(net_profit: float, cost_basis: float) -> float:
    """
    Calculates Return on Investment.
    
    Raises:
        ValueError: If cost_basis is 0, as ROI is undefined.
    """
    if cost_basis == 0.0:
        raise ValueError("Cost basis cannot be zero for ROI calculation.")
        
    return net_profit / cost_basis
```

#### 2. The Test Suite (The Safety Net)

We use pytest to assert behavior. This catches what Mypy misses.

```python
import pytest
from metrics import calculate_roi

def test_calculate_roi_standard_case():
    # Verify the math
    assert calculate_roi(50.0, 100.0) == 0.5

def test_calculate_roi_zero_division_guard():
    # Verify the logic/exception handling
    # This is the test that Mypy cannot perform for us.
    with pytest.raises(ValueError) as exc_info:
        calculate_roi(100.0, 0.0)
    
    assert "Cost basis cannot be zero" in str(exc_info.value)

def test_calculate_roi_negative_values():
    # Verify domain logic: losing money logic works
    assert calculate_roi(-20.0, 100.0) == -0.2
```

#### 3. The I/O Boundary (Runtime Enforcement)

For the JSON boundary problem, we stop relying on “trust me” type hints and move to parsing. Pydantic is the industry standard for bridging the gap between runtime data and static types.

```python
from pydantic import BaseModel, ValidationError

class Transaction(BaseModel):
    amount: int
    currency: str

def process_transaction_safe(raw_json: str) -> None:
    try:
        # Runtime validation that converts to static types!
        payload = Transaction.model_validate_json(raw_json)
        perform_transfer(payload.amount)
    except ValidationError as e:
        print(f"Security Alert: Invalid payload received: {e}")

def perform_transfer(value: int) -> None:
    # Now this is genuinely safe. Pydantic guaranteed 'value' is an int 
    # before this function was ever called.
    print(f"Transferring ${value}")
```

In this pattern:

1.  Pydantic validates the values at runtime and ensures they match the types.
2.  Mypy analyzes the payload object and knows `payload.amount` is an integer.
3.  Tests ensure that invalid JSON triggers the error handling logic correctly.

---

### Conclusion

Type hints in Python are a form of rigid documentation. They are excellent for developer ergonomics, IDE autocompletion, and catching simple structural misalignments. They reduce the cognitive load of reading code because you don’t have to guess what `x` is.

But they are not a safety net. They are a guardrail made of holographic tape.

If you rely solely on type hints, you are vulnerable to runtime data corruption, logic errors, and boundary failures. Strong testing is what breathes life into your architecture, ensuring that the machine doesn’t just look correctly assembled, but actually runs.

Do not let the green checkmark lull you into complacency. Annotate your code, yes — but verify it with tests.