"""One buoy record written as TOML, and what each writer does with its null."""
import json
import tomllib

import rtoml
import tomli_w
import tomlkit

from convert import build, from_toml_doc, to_toml_doc

record = build(1)[0]
as_json = json.dumps(record, separators=(",", ":"))
print(f"notes in the JSON record: {record['notes']!r}")

print()
print("the record as it is, with its null")
for name, dump in (("tomli_w", tomli_w.dumps), ("tomlkit", tomlkit.dumps),
                   ("rtoml", rtoml.dumps)):
    try:
        text = dump({"observation": [record]})
        notes_line = next(line for line in text.splitlines() if line.startswith("notes"))
        read_back = tomllib.loads(text)["observation"][0]["notes"]
        print(f"  {name:<8} writes {notes_line!r}, read back as {read_back!r}")
    except Exception as error:
        print(f"  {name:<8} {type(error).__name__}: {error}")

shaped = to_toml_doc([record])
layouts = {
    "tomli_w": tomli_w.dumps(shaped),
    "tomlkit": tomlkit.dumps(shaped),
    "rtoml (none_value=None)": rtoml.dumps(shaped, none_value=None),
}
for name, text in layouts.items():
    print()
    print(f"--- shaped for TOML (notes dropped, datetime native), written by {name}")
    print(text, end="")

print()
print(f"{'JSON, compact':<28}{len(as_json.encode()):>5} bytes")
print(f"{'JSON, indent 2':<28}{len(json.dumps(record, indent=2).encode()):>5} bytes")
for name, text in layouts.items():
    same = from_toml_doc(tomllib.loads(text)) == [record]
    print(f"{'TOML, ' + name:<28}{len(text.encode()):>5} bytes, "
          f"{len(text.splitlines()):>2} lines, 'observation' x{text.count('observation')}, "
          f"round trip equal: {same}")
