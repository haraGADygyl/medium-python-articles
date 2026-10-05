# Reader comments — 006, rank among 50 million players

Not published, not linked from the article. Read this before replying to a new
comment on 006 so the answers stay consistent.

---

## 2026-10-05 — praise for the tie finding and the sharding caveat

**Comment (verbatim):**

> Good read. The ZREVRANK tie thing is nasty, 231 people on the top score and each gets a different rank just because of member names. Also liked that you called out sharding as the unmeasured part.

**What the reader means.** Two points, both accurate restatements of the article:
the 231 players tied on the top score each got a distinct `ZREVRANK`, decided by
member name, and the article flags sharding as unbuilt and unmeasured.

**Does it hold?** Yes. No new technical claim, so no new lab run. The evidence is
already in the lab: `lab/output-ties.txt` line 12 (231 members on the top score
250,000) and `lab/output-competition.txt` (`ZREVRANK` 230, 229, 228, ... for
those players with `ZCOUNT` above = 0 for all of them, and `ZSCORE` + `ZCOUNT`
p50 0.22 ms).

**Added in the reply.** Ties are ordered by the member *string* (byte-wise
lexicographic), and `ZREVRANK` reverses the whole order. So among equal scores,
`p9` gets a better rank than `p10015500`. That's string order, not numeric id
order. The members in the lab are `p<number>`, so this applies directly.

**Known imprecision in the article.** The conclusion line says the tied players
were ordered "by player id". Strictly it's by the member string, which is not
numeric id order. The dialogue (line ~122) says "member name", which is correct.
Not changed so far; fix only if the author asks.

**Reply:**

> Thanks! The ties were the one result I wouldn't have predicted without running it. It's also string order on the member, not numeric id order: if p9 and p10015500 tie, p9 gets the better rank. If the product wants everyone on the top score to be #1, ZSCORE + ZCOUNT does it in 0.22 ms. Sharding is still the open question, and I'd rather say that than guess at it.

**Likely follow-ups.**

- *"How would you shard it then?"* The article's position is score-bucketed counters
  on top of the sorted sets, unbuilt. Say again that it's unmeasured. Don't
  improvise numbers.
- *"Why not encode a tiebreaker in the score?"* The article already proposes that
  for ordinal rank (pack achievement time into the score). Point there.
- *"Does Redis Cluster help?"* No. The leaderboard is one key, so it lives on one
  slot (article, Sharding section).
