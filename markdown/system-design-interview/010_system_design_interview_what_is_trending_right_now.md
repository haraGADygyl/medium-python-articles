# System Design Interview: What Is Trending Right Now, and How Sure Are You?

#### Exact counts froze Redis for 9 seconds, and the sketch that replaced them showed an empty trending panel while 30 brand-new tags took off

**By Tihomir Manushev**

*Nov 7, 2026 · 9 min read*

---

A discovery team at a recipe-sharing app, hiring a senior backend engineer. The interviewer is Thiago.

The standard answer is to count every tag in a sliding window and sort. That's right, and the long tail makes it expensive: most tags are used once, and every one of them gets a counter. The standard fix is a count-min sketch, which is small and fast, and whose error is the same size for every tag, so the small counts that decide what's trending are the ones it gets wrong.

Everything below ran on Redis 8.4 in Docker, with Python 3.12.3, redis-py 5.2 and NumPy 1.26, on a Ryzen 5 3600 with 32 GB and an NVMe drive. The traffic is synthetic: 10 million tags with Zipf popularity, 5,000 tag uses a second, and 30 brand-new tags that take off during the hour.

---

### The question

**Thiago:** Every recipe carries hashtags, and the home screen shows what's trending: ten tags, refreshed every few seconds. We see about 5,000 tag uses a second. How do you build it?

**Tihomir:** Count each tag over the last hour and show the ten biggest. One sorted set per minute, one `ZINCRBY` per use, and the panel unions the last 60 minutes.

```python
import redis

r = redis.Redis(decode_responses=True)


def record(tag: str, now: float) -> None:
    """One ZINCRBY per use, into the bucket for the current minute."""
    key = f"trend:min:{int(now // 60)}"
    r.zincrby(key, 1, tag)
    r.expire(key, 3_900)


def trending_now(now: float) -> list[tuple[str, float]]:
    """Union the last 60 minutes and read the top 10."""
    minute = int(now // 60)
    keys = [f"trend:min:{m}" for m in range(minute - 59, minute + 1)]
    r.zunionstore("trend:hour", keys)

    return r.zrevrange("trend:hour", 0, 9, withscores=True)
```

**Thiago:** Writes?

**Tihomir:** 5,000 a second, and they're cheap. One pipelined client did 128,573 `ZINCRBY`s a second.

---

### The first trap

**Thiago:** And the read?

**Tihomir:** I loaded one hour: 18 million uses across 2.9 million distinct tags. Then I ran the union three times while another client sent a `PING` every millisecond.

```
60 minute buckets: 7,191,508 members, 119,858 per minute, bucket 0 = 10.9 MB, used_memory +680 MB
run 1: ZUNIONSTORE 60 keys -> 2,883,233 members in 8969 ms; PING worst 8968 ms, 1 pings over 100 ms
run 2: ZUNIONSTORE 60 keys -> 2,883,233 members in 8880 ms; PING worst 8880 ms, 1 pings over 100 ms
run 3: ZUNIONSTORE 60 keys -> 2,883,233 members in 8830 ms; PING worst 8829 ms, 1 pings over 100 ms
hour set: 270 MB; total used_memory 963 MB
tags used once this hour: 1,872,836 of 2,883,233 (65%)
```

**Tihomir:** The union takes nine seconds, and Redis runs commands on one thread, so the `PING` waited for all of it. So did every other client, the ingest workers included. And 65% of what it merged were tags used once, which will never be on the panel.

![The union holds Redis's only thread, so every other command waits behind it](assets/010/01-union.gif)

**Thiago:** Keep the hour set up to date instead of rebuilding it.

**Tihomir:** That fixes the read, and I haven't measured it. It doesn't fix the memory: the 60 buckets are still 680 MB, and the hour set adds 270 MB, almost all of it the long tail. A panel per country or per language multiplies that.

---

### Count less exactly

**Thiago:** So?

**Tihomir:** A count-min sketch per minute. It's a grid of counters, here 7 rows of 2,000, and each tag hashes to one counter in each row. A read returns the smallest of its seven, so the answer can be too high but never too low. Redis has it built in, and `CMS.INCRBY` returns the new estimates, which gives me a 200-tag candidate list per minute for free.

```python
ERROR, PROB, KEEP = 0.001, 0.01, 200


def record_batch(minute: int, counts: dict[str, int]) -> None:
    """Add a batch of uses to the minute's sketch; keep its 200 biggest."""
    key, cand = f"trend:cms:{minute}", f"trend:cand:{minute}"

    try:
        r.execute_command("CMS.INITBYPROB", key, ERROR, PROB)
    except redis.ResponseError:
        pass  # this minute's sketch already exists

    flat = [x for pair in counts.items() for x in pair]
    estimates = r.execute_command("CMS.INCRBY", key, *flat)
    r.zadd(cand, dict(zip(counts, estimates)), gt=True)
    r.zremrangebyrank(cand, 0, -(KEEP + 1))


def top_tags(minute: int) -> list[tuple[str, int]]:
    """Merge the hour's sketches, score the candidates, keep 10."""
    minutes = range(minute - 59, minute + 1)
    keys = [f"trend:cms:{m}" for m in minutes]
    r.delete("trend:cms:hour")
    r.execute_command("CMS.INITBYPROB", "trend:cms:hour", ERROR, PROB)
    r.execute_command("CMS.MERGE", "trend:cms:hour", len(keys), *keys)
    r.zunionstore("trend:cand:hour", [f"trend:cand:{m}" for m in minutes])
    names = r.zrange("trend:cand:hour", 0, -1)
    counts = r.execute_command("CMS.QUERY", "trend:cms:hour", *names)

    return sorted(zip(names, counts), key=lambda x: -x[1])[:10]
```

**Thiago:** Numbers.

**Tihomir:** `ERROR` 0.001 means the overestimate stays under 0.1% of all uses, with 99% probability. That's what gives 2,000 by 7.

```
per minute: CMS width 2000 depth 7 = 112 KB, candidates 200 = 35 KB (MEMORY USAGE); 60 minutes: used_memory +5.5 MB
run 1: merge 60 sketches + score 1054 candidates in 10.2 ms; PING worst 4.3 ms
run 2: merge 60 sketches + score 1054 candidates in 11.0 ms; PING worst 5.1 ms
run 3: merge 60 sketches + score 1054 candidates in 10.4 ms; PING worst 4.2 ms
same 10 tags: True; same order: True
```

**Tihomir:** 5.5 MB instead of 950, and 10 ms instead of nine seconds. Same ten tags, same order. One surprise: `MEMORY USAGE` reports 8 bytes per sketch counter, but Redis allocates 4, so I counted memory from `used_memory`.

---

### How sure are you?

**Thiago:** How sure are you?

**Tihomir:** The guarantee is 18,000, which is 0.1% of 18 million. What I measured is about 4,000 on every tag, wherever it sits in the ranking.

```
exact rank band   true count (median)   overestimate (median / max)   relative (median)
      1-10                  201,893          4,053 /    5,022              2.3%
     91-100                  11,049          4,432 /    5,575             38.6%
    991-1,000                 1,097          4,117 /    5,195            376.0%
  9,991-10,000                  107          4,086 /    4,352           3818.7%

2,000 tags never used this hour: estimate median 4,160, max 8,750
```

**Tihomir:** The error is additive. At the top it's 2.3%, and the gap between tenth and eleventh was 13,124, so the order held. At rank 10,000 it's 38 times the real count, and a tag nobody used this hour reads 4,160, because every counter it lands in is shared with about 1,440 other tags.

![Why a tag nobody used reads 4,160](assets/010/02-cells.png)

---

### The second trap

**Thiago:** Your top tag is tag0000000. It was top yesterday too.

**Tihomir:** And every hour before that. I counted what's popular, not what's trending, and of the 30 tags that were brand new this hour, the popular top ten held none. Trending means a tag is used far more than usual, so I compare this hour with its average hour over the previous day.

```python
MIN_USES, MIN_LIFT, SMOOTH = 500, 5.0, 10


def is_trending(this_hour: int, last_24h: int) -> tuple[bool, float]:
    """At least 500 uses, and five times the usual hourly rate."""
    lift = (this_hour + SMOOTH) / (last_24h / 24 + SMOOTH)

    return this_hour >= MIN_USES and lift >= MIN_LIFT, lift
```

**Thiago:** From the same sketches?

**Tihomir:** That's where it breaks. I scored every tag seen in the hour, which is the best case any candidate list can give, against a 24-hour baseline sketch of the same size. With exact counts, all 30 new tags pass and nothing else does. Here's the sketch, over three different hours of traffic.

```
exact rule (>= 500 uses, lift >= 5.0): 30 tags pass, 30 of them new

  width KB/sketch   noise floor            new pass         others pass       new-tag lift shown
  2,000        58   4,138 / 4,175 / 4,130  0 / 0 / 0        0 / 0 / 0         2.4 / 2.2 / 2.2

        tags reading >= 500 uses: 2,883,233 (truly: 2,179)
```

**Tihomir:** The panel was empty. A typical new tag was used three times in the previous 24 hours, and the sketch read its baseline as 4,260 an hour, about 102,000 for the day. So its lift came out at 2.4 instead of 571. The 500-use minimum filtered nothing either, because all 2.9 million tags read above it.

![The same 30 new tags through the same rule: exact counts, the narrow sketch, a wide one](assets/010/03-lift.png)

**Thiago:** And the ranking?

**Tihomir:** It survived. Sorted by lift, the top ten were new tags at every width, because the same noise sits in both sketches and mostly cancels in the ratio. What doesn't survive is any rule with a number in it.

---

### Size it for the smallest number

**Thiago:** Fix it.

**Tihomir:** Size the sketch from the smallest count the rule reads, not from the total. The rule asks whether a tag with 500 uses and no history has a lift of 5, which only works while the noise floor stays under about 115. So I swept the width.

```
rule: >= 500 uses, lift >= 5; 30 new tags; seeds 1 / 2 / 3
  width KB/sketch   noise floor            new pass         others pass       new-tag lift shown
  2,000        58   4,138 / 4,175 / 4,130  0 / 0 / 0        0 / 0 / 0         2.4 / 2.2 / 2.2
 10,000       328   658 / 662 / 651        22 / 21 / 25     0 / 0 / 0         10.2 / 8.5 / 8.5
 20,000       655   292 / 293 / 289        29 / 30 / 30     0 / 0 / 0         19.4 / 19.2 / 16.2
 50,000     1,573   96 / 96 / 95           30 / 30 / 30     0 / 0 / 0         60.9 / 46.4 / 44.0
100,000     3,146   40 / 40 / 39           30 / 30 / 30     0 / 0 / 0         114.8 / 92.6 / 100.6
```

**Tihomir:** At 50,000 wide the floor is 96, all 30 new tags pass in all three hours, and nothing passes that shouldn't. The lift it shows is still 44 to 61 instead of about 500, so the panel can say "new" but not "up 500 times".

**Thiago:** Sixty of those?

**Tihomir:** That would be 94 MB. I use twelve five-minute buckets for the hour and 24 hourly sketches for the baseline, so the window slides in five-minute steps, which is fine for a panel. Each bucket keeps its 1,000 biggest estimates as candidates.

```python
WIDTH, DEPTH = 50_000, 7


def merged(dest: str, keys: list[str]) -> None:
    """Rebuild dest as the sum of keys; all share width and depth."""
    r.delete(dest)
    r.execute_command("CMS.INITBYDIM", dest, WIDTH, DEPTH)
    r.execute_command("CMS.MERGE", dest, len(keys), *keys)


def trending_panel(bucket: int, hour: int) -> list[tuple[str, float]]:
    """12 five-minute buckets against 24 hourly baseline sketches."""
    buckets = range(bucket - 11, bucket + 1)
    merged("trend:hour", [f"trend:cms:{b}" for b in buckets])
    merged("trend:day", [f"trend:base:{h}" for h in range(hour - 24, hour)])
    names = list({n for b in buckets
                  for n in r.zrange(f"trend:cand:{b}", 0, -1)})
    now = r.execute_command("CMS.QUERY", "trend:hour", *names)
    day = r.execute_command("CMS.QUERY", "trend:day", *names)
    rows = []

    for name, uses, baseline in zip(names, now, day):
        ok, lift = is_trending(uses, baseline)

        if ok:
            rows.append((name, lift))

    return sorted(rows, key=lambda x: -x[1])
```

![Each bucket's life: open, in the hour window, folded into the baseline, reset](assets/010/04-rotation.gif)

**Thiago:** Numbers.

```
run 1: merge 12 + 24 sketches, score 1,206 candidates: 78 ms, PING worst 44.6 ms
run 2: merge 12 + 24 sketches, score 1,206 candidates: 78 ms, PING worst 44.7 ms
run 3: merge 12 + 24 sketches, score 1,206 candidates: 79 ms, PING worst 45.2 ms
memory: 36 sketches, MEMORY USAGE says 2.80 MB each, candidate lists 1.09 MB, used_memory 63 MB
panel: 30 tags pass, 30 of them new, 0 not; exact rule passes 30 (30 new)
missed by the panel: 0 []
  tag5808951: sketch 10,144 uses, lift 97.8  |  true 10,049 uses, baseline 2, lift 998
  tag6855625: sketch 7,959 uses, lift 85.0  |  true 7,869 uses, baseline 2, lift 781
```

**Tihomir:** The panel shows the same 30 tags as exact counting, with nothing missed and nothing extra, and the other two hours matched as well. The new tags' candidate lists caught every one of them, so discovery was never the problem. All of it fits in 63 MB.

---

### What it costs

**Thiago:** What does it cost?

**Tihomir:** First, memory: 63 MB against 5.5 MB for the sketch that showed nothing, and against 950 MB for one exact hour. I didn't load an exact 24-hour baseline, so I won't put a number on it, but it would be 24 hours of long tail. Second, the read holds Redis for about 45 ms, because merging 36 sketches of 350,000 counters runs on the same single thread. That's fine every few seconds, and it's not something to run on every page view, so the panel result gets cached.

**Thiago:** Anything else?

**Tihomir:** The floor grows with traffic. It comes from the uses that share each counter, so twice the traffic at the same width means roughly twice the floor, and the width has to follow. I checked that against widths, not against other traffic levels. I also haven't measured coordinated accounts pushing a tag, more than one Redis node, or a real tag distribution: mine is synthetic Zipf, and a heavier tail would raise the floor.

---

### Conclusion

**Thiago:** Summary.

**Tihomir:** Four lines.

**Exact counts pay for the long tail.** 65% of the 2.9 million tags were used once, the hour cost 950 MB, and the union held Redis for nine seconds.

**A count-min sketch adds the same error to every tag.** About 4,000 here: 2.3% on the top ten, 38 times the real count at rank 10,000, and 4,160 for a tag nobody used.

**Trending is a ratio, and its denominator is the smallest number in the system.** Sized at 0.1%, the sketch read a new tag's baseline as 4,260 an hour, and the panel stayed empty while 30 new tags took off.

**Size the sketch for the smallest count the rule reads.** At 50,000 wide the floor fell to 96, all 30 passed, nothing else did, and it took 63 MB and 79 ms.

The standard answer asks how many times each tag was used, and it treats the sketch's error bound as a property of the sketch. The bound is a fraction of the total, so the question to ask is which count you'll divide by, and whether the error is smaller than that.
