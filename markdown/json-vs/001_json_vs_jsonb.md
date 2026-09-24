# JSON vs. JSONB

#### PostgreSQL's two JSON types: jsonb is 34% bigger and 2.6× slower to write, and up to 12× faster to query

**By Tihomir Manushev**

*Sep 24, 2026 · 7 min read*

---

PostgreSQL has two column types for JSON, and they accept exactly the same input. `json` checks that the text is valid and stores it character for character. `jsonb` parses it once, on write, into a binary tree and throws the original text away.

That makes this the one comparison in the series where both sides speak JSON. The difference is *when* you pay for parsing. `json` pays on every read: each `->>` re-parses the stored text from the beginning. `jsonb` pays once, on write, and in space. The PostgreSQL documentation says most applications should prefer `jsonb`. I loaded the series' 50,000 buoy observations into both to see what "most" leaves out.

On PostgreSQL 18.0, `jsonb` took 34% more disk, loaded 2.6 times slower and returned whole documents 3.3 times slower. It answered field queries up to 12 times faster, and it is the only one of the two that can use a GIN index or compare two documents for equality.

---

### The same document, both ways

One observation from the series' generator, stored in both types:

```json
{
  "observation_id": 9007199254740993,
  "buoy_id": "NE-08",
  "recorded_at": "2026-02-11T00:00:00+00:00",
  "position": {"lat": 57.21621, "lon": -2.37579},
  "wave_height_m": 3.5,
  "water_temp_c": 12.0,
  "wind_gust_ms": 10.7,
  "battery_v": 13.12,
  "qc_passed": true,
  "notes": null,
  "sensors": [
    {"tag": "accelerometer", "status": "offline", "samples": 1933},
    {"tag": "thermistor", "status": "degraded", "samples": 1866},
    {"tag": "anemometer", "status": "degraded", "samples": 318}
  ]
}
```

A smaller document shows the difference faster. Here is one with an extra space and a duplicated key, cast to each type:

```sql
SELECT '{"buoy_id": "NE-08",  "notes": null, "buoy_id": "HB-214"}'::json  AS as_json;
-- {"buoy_id": "NE-08",  "notes": null, "buoy_id": "HB-214"}

SELECT '{"buoy_id": "NE-08",  "notes": null, "buoy_id": "HB-214"}'::jsonb AS as_jsonb;
-- {"notes": null, "buoy_id": "HB-214"}
```

`json` returns what you gave it, including the double space and both `buoy_id` keys, which RFC 8259 allows and leaves to the reader to resolve. `jsonb` resolves it on write: the last duplicate wins, the whitespace goes, and the keys come back in its own order — shorter keys first, then bytewise — which is why `notes` now precedes `buoy_id`.

Numbers change form too, because `jsonb` stores them as PostgreSQL `numeric`:

```sql
SELECT '{"wave_height_m": 3.50, "samples": 2e3, "observation_id": 9007199254740993}'::jsonb
       AS as_jsonb;
-- {"samples": 2000, "wave_height_m": 3.50, "observation_id": 9007199254740993}
```

`2e3` becomes `2000`. `3.50` keeps its trailing zero, because `numeric` keeps scale. The 64-bit id past 2^53 survives exactly, which is more than a JavaScript client reading it will manage. The value is preserved; the text you typed is not.

---

### What JSONB actually changes

Reading a field stops being a parse. A `jsonb` value stores its keys sorted, with offsets, so `doc->>'qc_passed'` is a binary search into the binary tree. The same operator on `json` runs the JSON parser over the stored text on every call, for every row, so the cost grows with the size of the document rather than the size of the answer.

It gains operators `json` does not have. Containment (`@>`), key existence (`?`, `?|`, `?&`) and the jsonpath matches (`@?`, `@@`) are `jsonb`-only, and they are what a GIN index accelerates:

```sql
CREATE INDEX obs_jsonb_gin ON obs_jsonb USING gin (doc jsonb_path_ops);

SELECT count(*) FROM obs_jsonb
WHERE doc @> '{"buoy_id": "NE-08", "qc_passed": false}';
-- 662
```

One index answers containment queries on any key, including keys you had not thought of when you created it. `jsonb_path_ops` supports `@>` and jsonpath only; the default `jsonb_ops` also supports the existence operators, at a larger size.

It gains equality. `jsonb` compares values, so key order does not matter:

```sql
SELECT '{"buoy_id": "NE-08", "qc_passed": false}'::jsonb
     = '{"qc_passed": false, "buoy_id": "NE-08"}'::jsonb AS jsonb_equal;
-- t

SELECT '{"buoy_id": "NE-08"}'::json = '{"buoy_id": "NE-08"}'::json AS json_equal;
-- ERROR:  operator does not exist: json = json
```

`json` has no equality operator at all. `SELECT DISTINCT`, `GROUP BY doc`, `UNION` and a unique constraint on the column all fail on `json` and work on `jsonb`.

And it is stricter at the door. `\u0000` is valid JSON, and PostgreSQL text cannot hold it. `jsonb` rejects it on insert with `unsupported Unicode escape sequence`. `json` stores it without complaint and then raises the same error when `->>` tries to read the field. A bad value in a `json` column fails when you read it, not when it was written.

---

### The measurement

PostgreSQL 18.0 in Docker, 50,000 records, best of five after a warm-up, parallel query off so each number is one backend's work:

```
load: INSERT ... SELECT line::<type> FROM raw
  json      164.4 ms
  jsonb     428.3 ms

storage        table bytes  avg doc bytes
obs_json        23,142,400            419
obs_jsonb       31,023,104            566

query                        json ms  jsonb ms
count failed QC                137.0      14.4
avg wave height per buoy       278.9      69.5
sensors, the last key          157.8      15.8
NE-08 and failed QC            160.0      13.4
whole document as text          49.0     160.9

containment: doc @> '{"buoy_id": "NE-08", "qc_passed": false}'
  seq scan                      14.0 ms
  gin jsonb_ops                  1.5 ms   index 18,513,920 bytes, built in 1409 ms
  gin jsonb_path_ops             0.9 ms   index 12,533,760 bytes, built in 464 ms

expression index on doc->>'buoy_id'
  obs_json                      24.4 ms
  obs_jsonb                      4.1 ms
```

`jsonb` spent 2.6 times as long loading and stored 34% more, 566 bytes per document against 419. The offsets and `numeric` values that make reads fast are extra bytes. Neither table was compressed: at around 500 bytes the documents sit well under PostgreSQL's roughly 2 KB TOAST threshold, so larger documents may compare differently.

On field access the parse cost dominates. Counting failed QC was 9.5 times faster on `jsonb`, and the two-field filter 11.9 times. The aggregate gained least, 4.0 times, because computing a `numeric` average takes time that no storage format can remove.

The last row of the query table goes the other way. Returning whole documents was 3.3 times *slower* on `jsonb`: `json` hands back its stored text, while `jsonb` has to rebuild text from the tree. That text is also 10% longer, 22,790,154 characters against 20,740,508, because `jsonb` writes a space after every `:` and `,`.

Indexes are not `jsonb`-only. A B-tree on the expression `doc->>'buoy_id'` works on `json` too and took the filter from 160.0 ms to 24.4. What `json` cannot have is the GIN index: one 12.5 MB structure answering containment on any key in 0.9 ms.

---

### Where JSON still wins

When the bytes are the contract. A webhook signed with an HMAC is verified against the exact body the sender sent. Store it in `jsonb` and the reordered, re-spaced text will never match the signature again. Keep the original in `json`, or in `text`, if you might need to verify it later.

When you write far more than you read. An inbound-payload archive or an audit trail you query twice a year gets the 2.6× faster load and the 25% smaller table, and never pays the per-read parse.

When you return documents whole. An API that reads a row by primary key and sends the document untouched is doing the one thing `json` is 3.3 times faster at.

When key order or duplicates carry meaning — a legacy consumer that reads the first key, or a document you must reproduce exactly. `jsonb` discards both on insert, and they cannot be recovered.

---

### Conclusion

Use `jsonb` for documents you query: filters on fields, containment searches, GIN indexes, `DISTINCT` and `GROUP BY` on the document, uniqueness. On this payload that meant queries 9.5 to 11.9 times faster, and 0.9 ms containment lookups on any key.

Use `json`, or `text`, for documents you store and return unchanged: signed payloads, raw archives, write-heavy logs, responses served whole.

The cost of `jsonb` is 34% more disk, 2.6 times slower writes, slower whole-document reads, and the permanent loss of the original text: its formatting, key order, duplicate keys and number spelling. If any of that might matter later, keep the original next to the `jsonb` column.
