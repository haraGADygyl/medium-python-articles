"""Do new tags reach a per-minute candidate list built from sketch estimates?"""
import sys

import numpy as np

from common import connect, load, tag

DEPTH = 7
seed = int(sys.argv[1])
widths = [int(w) for w in sys.argv[2].split(",")]
keeps = [int(k) for k in sys.argv[3].split(",")]
r = connect()
r.flushall()
data = load(seed)
hour, bursts = data["hour"], data["bursts"]
print(f"seed {seed}: 30 new tags, hour counts {sorted(hour[bursts].tolist())}")

for width in widths:
    found = {k: set() for k in keeps}
    noise = []

    for m, (ids, counts) in enumerate(data["minutes"]):
        key = f"min:{m % 2}"
        r.delete(key)
        r.execute_command("CMS.INITBYDIM", key, width, DEPTH)
        est = []

        for start in range(0, len(ids), 5_000):
            flat = []

            for i, c in zip(ids[start:start + 5_000].tolist(), counts[start:start + 5_000].tolist()):
                flat += [tag(i), c]

            est += r.execute_command("CMS.INCRBY", key, *flat)

        est = np.array(est)
        noise.append(np.median(est[counts == 1] - 1))
        order = np.argsort(-est)

        for k in keeps:
            found[k] |= set(ids[order[:k]].tolist()) & set(bursts.tolist())

    print(f"width {width:>7,}: per-minute noise floor {np.median(noise):.0f}; " + "; ".join(
        f"top {k}/min keeps {len(found[k])} of 30 new tags (smallest kept "
        f"{min(hour[list(found[k])]) if found[k] else '-'})" for k in keeps))
