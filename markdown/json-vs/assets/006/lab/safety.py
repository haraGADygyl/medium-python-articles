"""Three things YAML can do to a reader that JSON cannot."""
import json
import time

import ruamel.yaml
import yaml

LEVELS = 6


def alias_bomb(levels: int) -> str:
    """Each level is a list of ten aliases to the level below."""
    lines = ["l0: &l0 [" + ", ".join(["lol"] * 10) + "]"]
    for n in range(1, levels + 1):
        refs = ", ".join([f"*l{n - 1}"] * 10)
        lines.append(f"l{n}: &l{n} [{refs}]")
    return "\n".join(lines) + "\n"


def main() -> None:
    bomb = alias_bomb(LEVELS)
    started = time.perf_counter()
    tree = yaml.safe_load(bomb)
    load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    expanded = json.dumps(tree[f"l{LEVELS}"])
    dump_ms = (time.perf_counter() - started) * 1000
    print(f"1. aliases: {len(bomb):,} bytes of YAML, {LEVELS} levels")
    print(f"   yaml.safe_load   {load_ms:8.1f} ms")
    print(f"   json.dumps       {dump_ms:8.1f} ms -> {len(expanded):,} bytes "
          f"({len(expanded) // len(bomb):,}x)")

    doubled = "buoy_id: NE-08\nwave_height_m: 3.5\nbuoy_id: HB-214\n"
    print()
    print("2. a duplicated key")
    print(f"   PyYAML           {yaml.safe_load(doubled)}")
    try:
        ruamel.yaml.YAML(typ="safe", pure=True).load(doubled)
    except ruamel.yaml.constructor.DuplicateKeyError as exc:
        print(f"   ruamel.yaml      DuplicateKeyError: {exc.problem}")
    print(f"   json.loads       "
          f"{json.loads('{\"buoy_id\": \"NE-08\", \"buoy_id\": \"HB-214\"}')}")

    tagged = "checksum: !!python/object/apply:builtins.sum [[1, 2, 3]]\n"
    print()
    print("3. a language-specific tag")
    try:
        yaml.safe_load(tagged)
    except yaml.constructor.ConstructorError as exc:
        print(f"   yaml.safe_load   ConstructorError: {exc.problem}")
    print(f"   yaml.unsafe_load {yaml.unsafe_load(tagged)}  "
          f"(builtins.sum was called)")


if __name__ == "__main__":
    main()
