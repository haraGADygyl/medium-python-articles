"""One YAML config, three parsers: what each value becomes."""
import json
import subprocess
from pathlib import Path

import ruamel.yaml
import yaml

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "fleet.yaml"


def show(value: object) -> str:
    return repr(value)


def main() -> None:
    text = CONFIG.read_text()
    pyyaml = yaml.safe_load(text)
    from_ruamel = ruamel.yaml.YAML(typ="safe", pure=True).load(text)
    node = json.loads(subprocess.run(
        ["node", "-e",
         "const Y=require('yaml'),fs=require('fs');"
         "const v=Y.parse(fs.readFileSync(process.argv[1],'utf8'));"
         "console.log(JSON.stringify(v))", str(CONFIG)],
        capture_output=True, text=True, check=True, cwd=HERE).stdout)

    print(f"PyYAML {yaml.__version__} (YAML 1.1), ruamel.yaml "
          f"{ruamel.yaml.__version__} (YAML 1.2), npm yaml 2.9.1 (YAML 1.2)")
    print()
    print(f"{'key':<16}{'written':<14}{'PyYAML':<32}{'ruamel.yaml':<28}"
          f"{'npm yaml'}")
    raw = {line.split(":", 1)[0]: line.split(":", 1)[1].split("#")[0].strip()
           for line in text.splitlines() if line and not line.startswith("#")}
    for key in pyyaml:
        print(f"{key:<16}{raw[key]:<14}{show(pyyaml[key]):<32}"
              f"{show(from_ruamel[key]):<28}{show(node[key])}")
    differ = [k for k in pyyaml if pyyaml[k] != from_ruamel[k]]
    print()
    print(f"{len(differ)} of {len(pyyaml)} keys differ between PyYAML and "
          f"ruamel.yaml: {', '.join(differ)}")


if __name__ == "__main__":
    main()
