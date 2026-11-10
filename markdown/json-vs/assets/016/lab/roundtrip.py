"""Change one threshold in fleet.toml, two ways, and count what survives."""
import tomllib
from pathlib import Path

import tomli_w
import tomlkit

original = Path("fleet.toml").read_text()


def comments(text: str) -> int:
    return sum(1 for line in text.splitlines() if "#" in line)


settings = tomllib.loads(original)
settings["thresholds"]["wave_height_m"] = 7.0
rewritten = tomli_w.dumps(settings)

document = tomlkit.parse(original)
document["thresholds"]["wave_height_m"] = 7.0
edited = tomlkit.dumps(document)

changed = [line for line in edited.splitlines() if line not in original.splitlines()]
print(f"{'':<22}{'bytes':>6}{'lines':>7}{'comments':>10}")
for label, text in (("original", original), ("tomllib + tomli_w", rewritten),
                    ("tomlkit", edited)):
    print(f"{label:<22}{len(text.encode()):>6}{len(text.splitlines()):>7}"
          f"{comments(text):>10}")

print()
print(f"tomlkit changed {len(changed)} line(s): {changed}")
print()
print("tomli_w output, first 10 lines:")
print("\n".join(rewritten.splitlines()[:10]))
