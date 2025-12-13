# Beyond Inheritance: Mastering Static Duck Typing with Python Protocols
#### Unlocking Structural Subtyping to Decouple Architecture and Restore Pythonic Flexibility

**By Tihomir Manushev**  
*Dec 5, 2025 · 7 min read*

---

For decades, Python developers have reveled in the freedom of Duck Typing. It is the philosophical cornerstone of the language: if an object walks like a duck and quacks like a duck, the interpreter is happy to treat it as one. We didn’t care about the lineage of the object or what classes it inherited from; we only cared about its behavior — the methods and attributes it exposed at runtime.

Then came type hints.

When PEP 484 introduced static analysis to Python, it initially brought a rigid, “Nominal” type system familiar to Java or C++ developers. Suddenly, to satisfy the strict gaze of mypy or pyright, our objects had to explicitly inherit from specific classes. We found ourselves writing code that felt un-Pythonic, forcing inheritance hierarchies merely to satisfy a linter. We lost the fluidity of duck typing in exchange for the safety of static verification.

Enter PEP 544 and the `typing.Protocol`.

Protocols represent the “Alchemist’s Stone” of Python typing: they transmute the dynamic flexibility of duck typing into a form that static analysis tools can understand. This is Structural Subtyping (often called Static Duck Typing). It allows us to define interfaces that objects satisfy implicitly, without valid inheritance, bridging the gap between Python’s dynamic soul and its static future.

In this article, we will dissect the mechanics of Protocol, explore why it is superior to Abstract Base Classes (ABCs) for API design, and look at how to implement robust, loosely coupled systems using Python 3.10+.

---

### Core Explanation: Nominal vs. Structural Subtyping

To understand the power of Protocols, we must first understand the limitations of the system they replace.

**The Tyranny of Nominal Typing**

In a Nominal type system (the default for classes), type compatibility is determined by the explicit ancestry of the object.

If you have a function `def process(data: DataSource)`, the type checker looks at the object passed in. Is it an instance of `DataSource`? Does it inherit from `DataSource`? If the answer is “no,” the type checker raises an error — even if the object has every single method defined in `DataSource`. The name of the type is the authority.

**The Freedom of Structural Subtyping**

Structural subtyping turns this logic on its head. It doesn’t care what an object is; it cares what it can do.

When you define a Protocol, you are defining a schema of behavior. When a type checker encounters a function expecting a Protocol, it inspects the candidate object’s structure. Does this object have a method named `read` that returns `bytes`? Yes? Then it is compatible. The object does not need to know that the Protocol exists.

**The Mechanism**

Under the hood, during static analysis, mypy performs a set operation. It treats the Protocol as a collection of required attributes and method signatures. It then checks if the candidate class’s interface is a superset of the Protocol’s requirements.

If the signatures match (checking argument types, return types, and variance), the type is considered *consistent-with* the Protocol. This happens entirely at the static analysis layer; at runtime, standard Protocols (unless decorated) are erased, imposing zero performance penalty on the execution speed of your application.

---

### Code Demonstration: The Storage Backend

Let’s visualize this with a production-oriented scenario. Imagine we are building a cloud-agnostic file backup system. We want to support saving files to a local disk, AWS S3, or Azure Blob Storage.

**The Old Way (Nominal/ABC)**

Traditionally, we would define an Abstract Base Class and force every implementation to inherit from it.

```python
from abc import ABC, abstractmethod

# The rigid contract
class StorageABC(ABC):
    @abstractmethod
    def save(self, filename: str, content: bytes) -> None:
        pass

# The concrete implementation must inherit
class LocalDiskStorage(StorageABC):
    def save(self, filename: str, content: bytes) -> None:
        with open(filename, 'wb') as f:
            f.write(content)

# This third-party class is problematic
class ThirdPartyS3Client: 
    # It has the right method, but it doesn't know about our StorageABC!
    def save(self, filename: str, content: bytes) -> None:
        print(f"Uploading {len(content)} bytes to S3 bucket...")
```

If we write a function `def backup(s: StorageABC)`, we cannot pass an instance of `ThirdPartyS3Client` because the authors of that library didn’t inherit from our specific `StorageABC`. We are forced to write “Wrapper” or “Adapter” classes just to satisfy the type checker.

**The Alchemist’s Way (Protocol)**

With Protocols, we invert the dependency. We define what our function needs, and any class that fits the description works automatically.

Here is the modern, Python 3.10+ approach:

```python
from typing import Protocol, runtime_checkable

# 1. Define the capabilities we need
class BlobWriter(Protocol):
    """
    Any object that can save bytes to a filename.
    """
    def save(self, filename: str, content: bytes) -> None:
        ...

# 2. Our internal implementation (Notice: NO inheritance from BlobWriter)
class LocalDiskDriver:
    def __init__(self, root_path: str):
        self.root = root_path
        
    def save(self, filename: str, content: bytes) -> None:
        print(f"Writing {filename} to disk at {self.root}...")

# 3. A mock of a 3rd party library (NO inheritance)
class CloudServiceSDK:
    def connect(self) -> None:
        pass
        
    def save(self, filename: str, content: bytes) -> None:
        print(f"PUT /api/v1/{filename} - Payload: {len(content)} bytes")

# 4. The consumer function
def execute_backup(driver: BlobWriter, data: dict[str, bytes]) -> None:
    for name, payload in data.items():
        driver.save(name, payload)

# --- usage ---

local_disk = LocalDiskDriver("/tmp/backup")
cloud_service = CloudServiceSDK()

# These both pass static type checking!
execute_backup(local_disk, {"config.json": b'{"key": "value"}'})
execute_backup(cloud_service, {"image.png": b'\x89PNG...'})
```

In the example above, `LocalDiskDriver` and `CloudServiceSDK` share no common ancestor other than `object`. However, mypy will mark both lines at the bottom as valid.

Why? Because `BlobWriter` defines a structural requirement: “Must have a save method accepting `str` and `bytes`.” Both classes satisfy this structure. We have successfully decoupled our business logic (`execute_backup`) from the implementation details of the storage drivers.

---

### Best Practice Implementation

While basic Protocols are powerful, production environments require handling edge cases, specifically runtime checks and interface segregation.

**1. Runtime Checkable Protocols**

Protocols are ghost entities; they exist primarily for the type checker. By default, `isinstance(obj, MyProtocol)` raises a `TypeError`. However, sometimes we need to branch logic at runtime based on capabilities.

We can achieve this using the `@runtime_checkable` decorator.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Renderable(Protocol):
    def render(self) -> str: ...

def display(item: object) -> None:
    if isinstance(item, Renderable):
        # Mypy knows 'item' has .render() inside this block
        print(item.render())
    else:
        print(str(item))
```

*Warning:* Using `isinstance` with Protocols is significantly slower than with ABCs or standard classes. CPython must inspect the object’s MRO (Method Resolution Order) and iterate through attributes to verify method existence dynamically. Use this sparingly in hot loops.

**2. The Interface Segregation Principle (ISP)**

A common mistake is defining massive Protocols that mirror entire classes. This reintroduces rigidity. Follow the “Role Interface” pattern: define Protocols that capture the minimum surface area required for a specific function.

*Bad Practice:*

```python
class DatabaseProtocol(Protocol):
    def connect(self): ...
    def execute(self, query): ...
    def close(self): ...
    def rollback(self): ...
    def commit(self): ...
```

*Best Practice:*
If a logging function only needs to insert data, define a Protocol just for that.

```python
class QueryExecutor(Protocol):
    def execute(self, query: str) -> None: ...

def audit_log(db: QueryExecutor, message: str) -> None:
    db.execute(f"INSERT INTO logs VALUES ('{message}')")
```

This allows you to pass a full database connection, a lightweight cursor, or a mock testing object to `audit_log`, as long as they support `execute`.

**3. Handling External Libraries**

The “Killer Feature” of Protocols is typing code you don’t control.

Libraries like `boto3` (AWS) or specialized scientific packages often generate classes dynamically or don’t ship with perfect type stubs. Instead of typing your variables as `Any` (which disables the type checker), define a Protocol matching the one or two methods you actually use from that library.

```python
# Instead of:
# client: Any = boto3.client('s3')

# Do this:
class S3Uploader(Protocol):
    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None: ...

def upload_report(client: S3Uploader, file_path: str) -> None:
    client.upload_file(file_path, "my-bucket", "report.txt")
```

Now, your code is type-safe, documented, and you didn’t have to import the heavy implementation of the library just to get a type definition.

---

### Conclusion

The introduction of `typing.Protocol` in PEP 544 marked a maturation point for Python. It acknowledged that while Python is dynamically typed at runtime, developers need rigorous contracts at design time.

By favoring Protocols over inheritance (ABCs), we adhere to the ‘Gang of Four’ design principle: “Program to an interface, not an implementation.” We allow our functions to accept any object that behaves correctly, regardless of its pedigree. This restores the flexibility of Python’s original duck typing while granting us the safety and tooling support of modern static analysis.

The next time you reach for an ABC to define a type hint, ask yourself: Do I need to share implementation code, or do I just need to define a contract? If it’s the latter, reach for a Protocol.