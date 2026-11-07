"""Trap 2: trending = this hour against the last 24 hours, read from sketches.

Every tag seen this hour is scored (the best case for any candidate list).
lift = (hour + 10) / (baseline / 24 + 10). The panel rule: a tag is trending
with at least 500 uses this hour and a lift of at least 5.
"""
import sys

import numpy as np

from common import MINUTES, connect, load, tag

MIN_SUPPORT, SMOOTH, DEPTH, MIN_LIFT = 500, 10, 7, 5.0


def lift(hour: np.ndarray, base: np.ndarray) -> np.ndarray:
    return np.where(hour >= MIN_SUPPORT, (hour + SMOOTH) / (base / 24 + SMOOTH), 0.0)


def fill(r, key: str, ids: np.ndarray, counts: np.ndarray, width: int) -> None:
    r.delete(key)
    r.execute_command("CMS.INITBYDIM", key, width, DEPTH)

    for start in range(0, len(ids), 5_000):
        flat = []

        for i, c in zip(ids[start:start + 5_000].tolist(), counts[start:start + 5_000].tolist()):
            flat += [tag(i), c]

        r.execute_command("CMS.INCRBY", key, *flat)


def query(r, key: str, ids: np.ndarray) -> np.ndarray:
    out = []

    for start in range(0, len(ids), 5_000):
        names = [tag(i) for i in ids[start:start + 5_000].tolist()]
        out += r.execute_command("CMS.QUERY", key, *names)

    return np.array(out, np.int64)


seed = int(sys.argv[1])
widths = [int(w) for w in sys.argv[2].split(",")]
r = connect()
r.flushall()
data = load(seed)
hour, base, bursts = data["hour"], data["base"], data["bursts"]
seen = np.flatnonzero(hour)
never = np.flatnonzero((hour == 0) & (base == 0))[:5_000]

exact_lift = lift(hour[seen], base[seen])
exact_top = seen[np.argsort(-exact_lift)[:10]]
popular = np.argsort(-hour)[:10]
print(f"seed {seed}: {len(seen):,} tags seen this hour; popular top 10 has "
      f"{np.isin(popular, bursts).sum()} new tags; exact lift top 10 has "
      f"{np.isin(exact_top, bursts).sum()} new tags, lifts "
      f"{np.round(np.sort(exact_lift)[::-1][:10]).astype(int).tolist()}")

if 2000 in widths:
    # a sketch merged from 60 minute sketches equals one sketch of the hour
    fill(r, "check:direct", seen, hour[seen], 2000)
    r.execute_command("CMS.INITBYDIM", "check:merged", 2000, DEPTH)

    for m, (ids, counts) in enumerate(data["minutes"]):
        fill(r, f"check:m{m}", ids, counts, 2000)

    keys = [f"check:m{m}" for m in range(MINUTES)]
    r.execute_command("CMS.MERGE", "check:merged", len(keys), *keys)
    probe = seen[::300]
    same = np.array_equal(query(r, "check:direct", probe), query(r, "check:merged", probe))
    print(f"merged 60 minute sketches == one hour sketch on {len(probe):,} tags: {same}")
    r.delete("check:direct", "check:merged", *keys)

exact_rule = seen[exact_lift >= MIN_LIFT]
print(f"exact rule (>= {MIN_SUPPORT} uses, lift >= {MIN_LIFT}): {len(exact_rule)} tags pass, "
      f"{np.isin(exact_rule, bursts).sum()} of them new")
print("top 10 by lift  | rule: >= 500 uses and lift >= 5")
print("width  KB/sketch  noise floor  ghosts  evergreens  new  =exact | pass  new  evergreen  ghost  "
      "| new tag shown/true lift (median)  new tag baseline read (per h, median)")

for width in widths:
    fill(r, "hour", seen, hour[seen], width)
    fill(r, "base", np.flatnonzero(base), base[np.flatnonzero(base)], width)
    kb = r.memory_usage("hour", samples=0) / 1e3
    h_est, b_est = query(r, "hour", seen), query(r, "base", seen)
    floor = int(np.median(query(r, "hour", never)))
    est_lift = lift(h_est, b_est)
    order = np.argsort(-est_lift)[:10]
    top = seen[order]
    ghosts = int((hour[top] < MIN_SUPPORT).sum())
    is_new = np.isin(top, bursts)
    evergreen = 10 - ghosts - int(is_new.sum())
    hits = len(set(top.tolist()) & set(exact_top.tolist()))
    passing = seen[(est_lift >= MIN_LIFT) & (h_est >= MIN_SUPPORT)]
    p_new = int(np.isin(passing, bursts).sum())
    p_ghost = int((hour[passing] < MIN_SUPPORT).sum())
    p_ever = len(passing) - p_new - p_ghost
    bmask = np.isin(seen, bursts)
    print(f"{width:>6,} {kb:>9,.0f} {floor:>12,} {ghosts:>7} {evergreen:>11} {int(is_new.sum()):>4} "
          f"{hits:>6} | {len(passing):>4} {p_new:>4} {p_ever:>10} {p_ghost:>6} | "
          f"{np.median(est_lift[bmask]):>6.1f} / {np.median(lift(hour[seen][bmask], base[seen][bmask])):<6.0f}"
          f"{np.median(b_est[bmask]) / 24:>24,.0f}")
    print(f"        tags reading >= {MIN_SUPPORT} uses: {(h_est >= MIN_SUPPORT).sum():,} "
          f"(truly: {(hour[seen] >= MIN_SUPPORT).sum():,})")
    ghost_ids = top[hour[top] < MIN_SUPPORT]

    for g in ghost_ids[:3]:
        i = int(np.flatnonzero(seen == g)[0])
        print(f"        ghost {tag(g)}: used {hour[g]} times this hour, baseline {base[g]}; "
              f"sketch says {h_est[i]:,} this hour, {b_est[i] / 24:,.0f}/h baseline, lift {est_lift[i]:.1f}")
