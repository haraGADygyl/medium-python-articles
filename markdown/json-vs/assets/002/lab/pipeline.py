"""One NaN in 50,000 records: what each consumer of the file ends up with.

A Python producer writes the series payload with json.dump defaults, after one
buoy reports a dropped-out wave sensor as NaN. Each consumer then answers the
same question: how many records, and what is the mean wave height?
"""
import json
import math
import statistics
import sys
import tempfile
from pathlib import Path

from runtimes import jq, node, php, psql

PAYLOAD = Path(__file__).resolve().parents[1].parent / "payload"
sys.path.insert(0, str(PAYLOAD))

from make_payload import build                              # noqa: E402

RECORDS = 50000
FAULTY = 31337          # the one record whose wave sensor dropped out


def main() -> None:
    rows = build(RECORDS)
    rows[FAULTY]["wave_height_m"] = math.nan
    text = json.dumps(rows, separators=(",", ":"))
    lines = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows)
    valid = [r["wave_height_m"] for r in rows
             if not math.isnan(r["wave_height_m"])]

    work = Path(tempfile.mkdtemp(prefix="nan-lab-"))
    path = work / "buoy.json"
    path.write_text(text)

    print(f"{RECORDS:,} records, record {FAULTY:,} has wave_height_m = NaN, "
          f"{len(text):,} bytes")
    print(f"correct answer: {len(valid):,} valid readings, "
          f"mean {statistics.fmean(valid):.6f}")
    print()
    print(f"{'consumer':<28}{'records':>9}   mean wave height")

    loaded = json.loads(text)
    heights = [r["wave_height_m"] for r in loaded]
    print(f"{'Python json.load':<28}{len(loaded):>9,}   "
          f"{statistics.fmean(heights)}")

    count, note = node(
        "const fs=require('fs');"
        f"try{{const r=JSON.parse(fs.readFileSync('{path}','utf8'));"
        "console.log(r.length+'|parsed')}"
        "catch(e){console.log('0|'+e.name+': '+e.message.slice(0,40)+'...')}"
    ).split("|", 1)
    print(f"{'Node JSON.parse':<28}{int(count):>9,}   {note}")

    out = jq("length, (map(.wave_height_m) | add / length), "
             "(map(select(.wave_height_m | isnan)) | length)", text).split()
    print(f"{'jq 1.7':<28}{int(out[0]):>9,}   {out[1]}  "
          f"(holds {out[2]} NaN internally, prints it as null)")

    count, note = php(
        f"$r=json_decode(file_get_contents('{path}'), true);"
        "echo $r === null ? 0 : count($r), '|', json_last_error_msg();"
    ).split("|", 1)
    print(f"{'PHP json_decode':<28}{int(count):>9,}   {note}")

    jsonl = work / "buoy.jsonl"
    jsonl.write_text(lines)
    count, note = node(
        "const fs=require('fs');let ok=0,bad=[];"
        f"fs.readFileSync('{jsonl}','utf8').split('\\n').forEach((l,i)=>{{"
        "if(!l)return;try{JSON.parse(l);ok++}catch(e){bad.push(i+1)}});"
        "console.log(ok+'|skipped line '+bad.join(','))"
    ).split("|", 1)
    print(f"{'Node, JSON Lines per line':<28}{int(count):>9,}   {note}")
    jsonl.unlink()

    psql("DROP TABLE IF EXISTS obs; CREATE TABLE obs (doc jsonb)")
    copied = psql("COPY obs (doc) FROM STDIN", lines)
    count = psql("SELECT count(*) FROM obs")
    print(f"{'PostgreSQL COPY ... jsonb':<28}{int(count):>9,}   "
          f"{copied.splitlines()[0]}")
    psql("DROP TABLE obs")

    path.unlink()
    work.rmdir()


if __name__ == "__main__":
    main()
