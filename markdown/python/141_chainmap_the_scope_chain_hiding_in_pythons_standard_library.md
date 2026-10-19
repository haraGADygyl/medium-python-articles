# `ChainMap`: The Scope Chain Hiding in Python's Standard Library

#### Lookups fall through every layer and writes land only in the first, and that one rule explains both what `ChainMap` is good for and the method you still have to write yourself

**By Tihomir Manushev**

*Oct 19, 2026 · 8 min read*

---

Every program with settings ends up with layers. A print shop's job ticket has house defaults (matte paper, one copy, 3 mm bleed), a client profile that overrides some of them, and the order itself, which overrides a few more. The usual way to combine them is a merge: `defaults | profile | order`, with the result handed to whoever needs it. That works until one layer changes after the merge, or until someone on the shop floor asks why a job is printing on silk, and the flat dictionary can't tell them.

Python has shipped a structure for this since 3.3. `collections.ChainMap` keeps the layers as a list and searches them in order on every lookup, without copying anything. Interpreters use the same structure for variable scopes: look in the local scope, then the enclosing one, then the globals. Layered configuration and lexical scope are the same problem, and `ChainMap` handles both.

It has one rule that catches people out: reads search every layer, but writes and deletes only ever touch the first. This article covers how lookups resolve, why the write rule exists, how `new_child()` models nested scopes, and the in-place update that `ChainMap` leaves for you to write. The running example is a print shop that turns orders into job tickets.

---

### A Merge Is a Snapshot

Here's the merge version. Three dictionaries, combined with the `|` operator, where the right-hand operand wins every collision:

```python
house_defaults = {"paper": "matte", "copies": 1, "duplex": False, "bleed_mm": 3}
client_profile = {"client": "Lindqvist Bakery", "paper": "silk", "duplex": True}
order_overrides = {"copies": 250}

flat_ticket = house_defaults | client_profile | order_overrides
client_profile["paper"] = "recycled"
print(flat_ticket["paper"])  # silk
```

The bakery switched to recycled stock after the ticket was built, and the ticket never heard about it. `|` copies every key and value into a new dictionary, so the result is a snapshot of the three layers at one moment. To pick up the change you merge again, which means knowing every place that kept a merged copy. The merge also throws away the answer to "which layer set this?" Once the keys are in one dictionary, the house's `matte` and the client's `silk` look the same.

---

### Reads Fall Through, Writes Stay on Top

A `ChainMap` takes the same three dictionaries without merging them:

```python
from collections import ChainMap

ticket = ChainMap(order_overrides, client_profile, house_defaults)
print(ticket["paper"])  # recycled
print(ticket["bleed_mm"])  # 3
print(ticket.maps[1] is client_profile)  # True
print(list(ticket))  # ['paper', 'copies', 'duplex', 'bleed_mm', 'client']
```

The argument order is the reverse of the merge. With `|` the *last* operand wins. In a `ChainMap` the *first* mapping is searched first, so the most specific layer goes on the left. Mixing the two up silently promotes your defaults over your overrides, and nothing raises.

The **`maps`** attribute is an ordinary list that holds the original dictionary objects, not copies. That's why the bakery's switch to recycled stock shows up immediately: the ticket reads `client_profile` on every lookup. A lookup walks the list until some layer has the key, so it costs O(L) dictionary lookups for L layers. With three to five layers that's negligible.

Iteration is a little odd. `list(ticket)` starts with the house defaults' keys in the house's own order, and `client` comes last. CPython builds the key order by merging the layers from the deepest one upward, so the bottom layer decides the order. The same method shows the cost of operations that see the whole chain: `len()` builds a set union of every layer on every call, and iteration builds a temporary dictionary. Both are O(N) in the total number of keys, and neither result is cached, so keep them out of hot loops.

Writes are where `ChainMap` stops being symmetrical:

```python
ticket["duplex"] = False
print(order_overrides)  # {'copies': 250, 'duplex': False}
print(client_profile["duplex"])  # True

print("bleed_mm" in ticket)  # True
try:
    del ticket["bleed_mm"]
except KeyError as error:
    print(error)  # "Key not found in the first mapping: 'bleed_mm'"
```

Assigning through the chain wrote into `order_overrides`, the first mapping, even though `duplex` already existed two layers down. For a job ticket that's the right call. "Print this one single-sided" is a fact about this order, and the bakery's profile stays clean for the next one. Deletion follows the same rule, and that's the surprise: `in` says `bleed_mm` exists, while `del` says it doesn't, because `in` searches every layer and `del` checks only the first.

The rule exists to protect shared layers. `house_defaults` sits under every ticket the shop prints. If assignment searched for the key and wrote wherever it found it, one order's tweak would change the default for every job after it. Python's own assignment rule works the same way: `x = 1` inside a function creates a local and never rebinds a global unless you declare `global` or `nonlocal`.

---

### Asking Where a Value Came From

Because the layers are still separate, you can answer the shop floor's question. This helper walks `maps` for each visible key and reports the first layer that defines it:

```python
def explain(
    chain: ChainMap[str, object], layer_names: tuple[str, ...]
) -> dict[str, str]:
    """Map every visible key to the name of the layer that supplies it."""
    report: dict[str, str] = {}
    for key in chain:
        for name, layer in zip(layer_names, chain.maps):
            if key in layer:
                report[key] = name
                break
    return report


print(explain(ticket, ("order", "client", "house")))
# {'paper': 'client', 'copies': 'order', 'duplex': 'order',
#  'bleed_mm': 'house', 'client': 'client'}
```

The inner loop repeats the search `ChainMap` does on every lookup, but it records the layer as well as the value. Hang this off a `--explain-config` flag and "why is this job on recycled stock?" takes one command to answer. A flat dictionary can't support this at all, because by the time you hold it, the information is gone.

---

### Nested Scopes With `new_child()`

Configuration is the static case. Scopes are the dynamic one: a new layer appears, a few names are shadowed, and the layer goes away. **`new_child()`** returns a new `ChainMap` with a fresh mapping in front of all the existing layers. The shop's packing slips use it. Each parcel gets its own scope, so a parcel can override the job's copy count without touching the ticket:

```python
def render_slip(
    job: ChainMap[str, object], parcels: list[dict[str, object]]
) -> list[str]:
    """Render a packing slip, giving each parcel its own scope over the job."""
    lines = ["{client}: {copies} copies on {paper}".format_map(job)]
    for number, parcel in enumerate(parcels, start=1):
        parcel_scope = job.new_child({"parcel_no": number, **parcel})
        lines.append("  #{parcel_no} {copies} to {address}".format_map(parcel_scope))
    return lines


shipments: list[dict[str, object]] = [
    {"copies": 200, "address": "Main Street shop"},
    {"copies": 50, "address": "Harbour kiosk"},
]
for slip_line in render_slip(ticket, shipments):
    print(slip_line)
# Lindqvist Bakery: 250 copies on recycled
#   #1 200 to Main Street shop
#   #2 50 to Harbour kiosk
print(ticket["copies"])  # 250
```

`str.format_map()` accepts any mapping, so the template resolves `{copies}` against the parcel layer and `{client}` against the bakery's profile with no extra code. Each parcel's scope disappears when the loop moves on. Nothing had to be "popped", because the job's own `ChainMap` was never changed. Its counterpart, the **`parents`** property, returns the chain without its first layer. That's the "leave this scope" operation when you hold a child and need its enclosing scope.

This is the scope chain in miniature. A template engine's `for` blocks, a rule interpreter's function calls, and a CLI's subcommand settings all push a layer, read through it, and drop it. Pushing costs one small dictionary plus a copy of the list of layer references, and that list stays short.

---

### The Method `ChainMap` Doesn't Have

Sometimes you do want to change a value where it lives. If the bakery calls to say they've switched to kraft paper for good, the change belongs in their profile, not in this one order. `ChainMap` has no operation for "find the layer that defines this key and update it there", but `maps` makes it a short subclass:

```python
from types import MappingProxyType


class JobTicket(ChainMap[str, object]):
    """A layered job ticket that can also edit a value where it lives."""

    def amend(self, key: str, value: object) -> None:
        """Overwrite key in the first layer that defines it."""
        for layer in self.maps:
            if key in layer:
                layer[key] = value
                return
        raise KeyError(key)


frozen_house = MappingProxyType({"paper": "matte", "bleed_mm": 3})
bakery = {"client": "Lindqvist Bakery", "paper": "silk"}
standing_order = JobTicket({}, bakery, frozen_house)

standing_order.amend("paper", "kraft")
print(bakery)  # {'client': 'Lindqvist Bakery', 'paper': 'kraft'}
try:
    standing_order.amend("bleed_mm", 5)
except TypeError as error:
    print(error)  # 'mappingproxy' object does not support item assignment
```

`amend` searches the same way a lookup does and writes into the first layer that has the key, so the bakery's profile changes and the empty order layer stays empty. A key that no layer defines raises `KeyError`. Inserting it silently would hide typos like `amend("papper", ...)`.

This is exactly the write path the default rule exists to block, so the example guards the bottom layer. Wrapping the house defaults in **`MappingProxyType`** gives a read-only view: lookups through the chain work normally, ordinary writes still go to the first layer, and anything that reaches the defaults directly fails loudly. Lock the layers no single job should be able to change, and `amend` can't touch them by accident. The cost is one extra level of indirection on lookups that reach the bottom layer.

---

### Gotchas Before You Ship It

`copy()` and the `|` operator copy only the first layer. Everything underneath is shared by reference, so a "copy" of a ticket still sees changes to the client's profile:

```python
draft = standing_order | {"copies": 10}
bakery["paper"] = "linen"
print(draft["paper"])  # linen
print(standing_order.maps[0])  # {}
```

Usually that's what you want. If you need a real snapshot, `dict(chain)` flattens the visible values into one new dictionary in O(N).

`new_child()` also accepts keyword arguments, but when you pass a mapping as well, it calls `update()` on *your* mapping before using it. `job.new_child(parcel, parcel_no=1)` writes `parcel_no` into the caller's parcel dictionary. That's why `render_slip` builds a new dictionary with `{"parcel_no": number, **parcel}` instead.

Finally, decide where flattening happens. `ChainMap` is a good fit while the layers are still changing: at startup, during a request, inside a scope. Once they stop changing, a code path that reads the same keys millions of times does better with one `dict(chain)` up front than with L lookups per key.

---

### Conclusion

`ChainMap` is a list of mappings with a search order, and almost everything about it follows from that. Lookups fall through the layers and see changes immediately, because nothing was copied. Writes and deletes stay in the first layer, so shared defaults can't be changed by accident, and that's also why `del` can fail on a key that `in` reports as present. `new_child()` and `parents` push and pop scopes cheaply. Updating a value in the layer that defines it is the one operation you have to add yourself, and the `maps` attribute makes that a five-line method.

Next time you reach for `defaults | profile | overrides`, ask whether anyone will need to know where a value came from, or whether a layer can change after the merge. If either answer is yes, keep the layers and chain them.
