# Your Users Cannot Spell: Typo-Tolerant Search in PostgreSQL with pg_trgm

#### Trigram similarity gives you fuzzy matching in a single extension — but the operator everyone reaches for first silently drops most of the matches.

**By Tihomir Manushev**

*Aug 4, 2026 · 9 min read*

---

A customer searches your plant catalog for `hydranga macrophyla`. The catalog contains 24,000 hydrangea listings. Your search returns nothing.

`ILIKE '%hydranga macrophyla%'` finds nothing, because the string does not occur. Full-text search finds nothing either, and that surprises people — `to_tsvector` splits text into lexemes and normalizes them, but `hydranga` and `hydrangea` are simply different lexemes. Stemming turns plurals into singulars; it does not repair typos. Both tools answer the question "does this text contain this token," and the user's token does not exist.

`pg_trgm` answers a different question: how similar are these two strings, character by character. That is the question a misspelling actually poses. This article builds typo-tolerant search on it — the trigram model itself, the operator choice that determines whether you find 14% or 100% of your matches, the GIN-versus-GiST decision that turns out to have no single winner, and where the whole approach stops working.

Everything runs on PostgreSQL 16 or later with no dependencies beyond a contrib extension. The measurements come from PostgreSQL 18.0 with `pg_trgm` 1.6.

---

### What a Trigram Actually Is

A trigram is three consecutive characters. `pg_trgm` lowercases the input, treats anything non-alphanumeric as a separator, pads each word with two leading spaces and one trailing space, and slices:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT show_trgm('Hydrangea');
--  {"  h"," hy",ang,dra,"ea ",gea,hyd,nge,ran,ydr}

SELECT show_trgm('hydranga');
--  {"  h"," hy",ang,dra,"ga ",hyd,nga,ran,ydr}
```

The padding is not decoration. It is what makes `hyd` at the start of a word rank differently from `hyd` in the middle, and it is why very short strings behave oddly later on.

Similarity is then set arithmetic — the size of the intersection divided by the size of the union. The two sets above share seven trigrams out of the twelve distinct ones between them, which is exactly what the function reports. Extending to the full two-word name, where the misspelled second word is long enough that one dropped letter costs proportionally less, the score climbs:

```sql
SELECT similarity('Hydrangea', 'hydranga');                         -- 0.5833333
SELECT similarity('hydranga macrophyla', 'Hydrangea macrophylla');  -- 0.68
SELECT similarity('hydranga macrophyla', 'Rhododendron japonica');  -- 0
```

0.68 for a string a human instantly recognizes as the same plant, 0 for a different one. That single number is the entire mechanism, and because it compares *sets*, it is completely insensitive to word order — `similarity('paniculata Limelight', 'Limelight paniculata')` is exactly 1. Depending on your product that is a gift or a trap, but it is worth knowing before a user reports it as a bug.

The catalog used throughout is a wholesale nursery marketplace: 480,000 listings across 48,000 distinct product labels, since multiple vendors stock the same plant. Labels average 41 characters and look like `Hydrangea macrophylla 'Annabelle' 1 gal`.

To reproduce every number below, build it:

```sql
CREATE TABLE nursery_listings (
    listing_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    botanical_name text NOT NULL,
    cultivar_name  text NOT NULL,
    pot_size       text NOT NULL,
    vendor         text NOT NULL,
    full_label     text NOT NULL
);

INSERT INTO nursery_listings (botanical_name, cultivar_name, pot_size, vendor, full_label)
SELECT g.genus || ' ' || s.species,
       c.cultivar,
       p.pot,
       (ARRAY['Thornbury Growers','Marchand Nurseries','Kestrel Field Stock',
              'Ravenswood Propagation','Alder Hollow Farms','Quarry Lane Plants',
              'Bramblewick Trade','Foxglove Wholesale','Ninebark Supply',
              'Sedgemoor Botanics'])[v],
       g.genus || ' ' || s.species || ' ''' || c.cultivar || ''' ' || p.pot
  FROM unnest(ARRAY['Hydrangea','Rhododendron','Echinacea','Heuchera','Clematis',
                    'Camellia','Viburnum','Weigela','Deutzia','Philadelphus',
                    'Ceanothus','Escallonia','Pittosporum','Nandina','Leucothoe',
                    'Physocarpus','Sarcococca','Osmanthus','Enkianthus','Fothergilla']) AS g(genus)
 CROSS JOIN unnest(ARRAY['macrophylla','paniculata','serrata','arborescens','quercifolia',
                         'purpurea','sanguinea','villosa','japonica','sinensis',
                         'occidentalis','glutinosa']) AS s(species)
 CROSS JOIN unnest(ARRAY['Endless Summer','Limelight','Annabelle','Nikko Blue','Pinky Winky',
                         'Bobo','Incrediball','Little Lime','Zinfin Doll','Vanilla Strawberry',
                         'Ruby Slippers','Munchkin','Gatsby Pink','Invincibelle Spirit',
                         'Tuff Stuff','Cityline Paris','Fire Light','Quick Fire',
                         'Strawberry Sundae','Diamond Rouge']) AS c(cultivar)
 CROSS JOIN unnest(ARRAY['1 gal','2 gal','3 gal','5 gal','7 gal','10 gal',
                         'bare root','4 in','6 in','15 gal']) AS p(pot)
 CROSS JOIN generate_series(1, 10) AS v;

VACUUM ANALYZE nursery_listings;
```

---

### The Operator That Loses Most of Your Results

The obvious way to use this is the `%` operator, which is true when `similarity()` clears a threshold — 0.3 by default. It is also the reason most pg_trgm deployments quietly underperform.

Search the catalog for `Annabelle`, a cultivar name that appears in 24,000 labels:

```sql
SELECT count(*) FROM nursery_listings WHERE full_label %    'Annabelle';  -- 3470
SELECT count(*) FROM nursery_listings WHERE full_label LIKE '%Annabelle%';  -- 24000
```

The `%` operator finds 3,470 of the 24,000 rows that literally contain the word. It misses 86% of them, and it misses them silently — the query succeeds, returns plausible results, and nobody notices until a vendor asks why their listing is unfindable.

The cause is dilution. `similarity()` compares the query against the *entire* target string, so a 9-character search term measured against a 40-character label can never score well no matter how perfectly it matches part of it:

```sql
SELECT full_label,
       similarity(full_label, 'Annabelle')             AS sim,
       word_similarity('Annabelle', full_label)        AS word_sim,
       strict_word_similarity('Annabelle', full_label) AS strict_sim
  FROM nursery_listings WHERE full_label LIKE '%Annabelle%' LIMIT 1;
```

```
                 full_label                 |    sim    | word_sim | strict_sim
--------------------------------------------+-----------+----------+------------
 Hydrangea macrophylla 'Annabelle' 1 gal    | 0.2631579 |        1 |          1
```

0.26 — below the default threshold, so the row is excluded despite containing the search term verbatim. `word_similarity` scores the same pair at 1.0 because it finds the best-matching *substring* of the target and measures against that instead of the whole thing. Its operator is `<%`, and note the argument order: the shorter query goes on the left.

```sql
SELECT count(*) FROM nursery_listings WHERE 'Annabelle' <%  full_label;  -- 24000
SELECT count(*) FROM nursery_listings WHERE 'Annabelle' <<% full_label;  -- 24000
```

Both find every row. `strict_word_similarity` (`<<%`) differs by respecting word boundaries — it will not match a fragment that starts mid-word, which makes it stricter and usually the better choice for search-as-you-type against names.

The rule that follows is simple and almost never stated: **use `%` only when the query and the target are the same kind of string** — deduplicating two company names, matching a full address against a full address. The moment you are searching for a term *inside* a longer field, `%` is the wrong operator and `<%` or `<<%` is the right one.

---

### Choosing an Index, and Why the Answer Is Both

`pg_trgm` supports two index types, and the folklore that "GIN is the fast one" is wrong often enough to be dangerous. They support different operators, and where one falls back to a sequential scan the other is thousands of times faster.

```sql
CREATE INDEX listings_label_gin  ON nursery_listings USING gin  (full_label gin_trgm_ops);
CREATE INDEX listings_label_gist ON nursery_listings USING gist (full_label gist_trgm_ops);
```

Measured on the 480,000-row catalog, PostgreSQL 18.0 in Docker on an AMD Ryzen 5 3600 (12 threads, 31 GB RAM) with the default 128 MB `shared_buffers`, warm cache, median of three runs:

| Operation | GIN | GiST |
|---|---|---|
| `%` similarity filter | 270 ms | 158 ms |
| `<->` similarity ranking, `LIMIT 10` | 726 ms — **seq scan** | 232 ms |
| `<%` word-similarity filter | 115 ms | 701 ms — **seq scan** |
| `<<->` word-similarity ranking, `LIMIT 5` | 732 ms — **seq scan** | **0.7 ms** |
| `ILIKE '%term%'` | 36 ms | 215 ms |
| Build time | 1.9 s | 6.2 s |
| Index size (69 MB heap) | 25 MB | 94 MB |

Read the two seq-scan rows against each other, because they are exact inverses. GIN cannot serve distance ordering at all — `ORDER BY ... <-> ...` degrades to scanning and sorting every row. GiST implements it as a genuine nearest-neighbour index scan. But GiST has no index support for the `<%` filter, which GIN handles well.

The most striking cell is the last ranking row. Ranking by word similarity — the query behind every decent autocomplete — takes 732 ms on GIN and 0.7 ms on GiST, a factor of a thousand, because GiST returns rows in distance order directly from the index and stops after five:

```
Limit (actual rows=5.00 loops=1)
  Buffers: shared hit=20
  ->  Index Scan using listings_label_gist on nursery_listings
        Order By: (full_label <->> 'Annabelle'::text)
Execution Time: 0.375 ms
```

Twenty buffers touched, for a top-5 over 480,000 rows.

GIN earns its place elsewhere. It is nearly 4× smaller, builds 3× faster, and dominates on `ILIKE '%term%'` — 36 ms against 215 ms — which is worth remembering on its own, since a trigram index accelerates unanchored `LIKE` and `ILIKE` patterns that no B-tree can ever help.

The GIN `%` row also hides a detail the plan makes clear: its bitmap index scan returned 62,000 candidate rows to produce 2,000 results, discarding the rest in a recheck against the heap. GIN indexes trigrams individually, so common trigrams produce large candidate sets that must be verified. On a catalog with a lot of repeated vocabulary, that recheck is most of the query's cost.

So build both. Together they add 119 MB to a 69 MB table, which is a real cost but a predictable one, and the planner picks correctly per query. If you must choose one: GiST when your product ranks results, GIN when it filters them or leans on `ILIKE`.

Writes pay for this. Inserting 20,000 rows, median of three runs:

| | Time | vs. no index |
|---|---|---|
| No trigram index | 46 ms | 1.0× |
| GIN | 306 ms | 6.6× |
| GiST | 367 ms | 8.0× |

A catalog absorbing a few thousand updates an hour will not notice. A table taking sustained bulk writes will, and the usual fix is to drop the trigram indexes for the load and rebuild after.

---

### The Threshold Is a Product Decision

`pg_trgm.similarity_threshold` controls what `%` accepts, and it is not a value you can reason your way to — it depends on your data and your tolerance for nonsense. Sweeping it across the original misspelled query shows how sharp the cliff is:

| Threshold | Matches |
|---|---|
| 0.1 | 62,000 |
| 0.2 | 23,960 |
| 0.3 (default) | 2,000 |
| 0.4 | 980 |
| 0.5 | 0 |

At 0.1 you return an eighth of the catalog. At 0.5 the correct answer disappears entirely. The useful range is narrow and sits in a different place for every dataset, so tune it against a real query log rather than intuition, and set it per transaction rather than globally:

```sql
BEGIN;
SET LOCAL pg_trgm.word_similarity_threshold = 0.55;
SELECT full_label FROM nursery_listings WHERE 'limelite' <% full_label LIMIT 10;
COMMIT;
```

The word-similarity operators read a separate setting, `pg_trgm.word_similarity_threshold` — changing `similarity_threshold` has no effect on `<%`, which is a quiet source of "my tuning did nothing" confusion.

---

### Where Trigrams Break

**Short strings.** With padding, a three-letter word has four trigrams, so unrelated short words collide:

```sql
SELECT similarity('fir', 'fig');   -- 0.33333334
```

That clears the default 0.3 threshold. Any catalog full of short codes or abbreviations needs a raised threshold or an exact-match path in front of the fuzzy one.

**Accents.** Trigrams are byte-level, so `ó` and `o` share nothing:

```sql
CREATE EXTENSION IF NOT EXISTS unaccent;
SELECT similarity('Escallonia rubra', 'Escallónia rúbra');                     -- 0.478
SELECT similarity(unaccent('Escallonia rubra'), unaccent('Escallónia rúbra')); -- 1
```

For any language with diacritics, index the unaccented form — `CREATE INDEX ... ON t USING gin (unaccent(col) gin_trgm_ops)` — which requires wrapping `unaccent` in an `IMMUTABLE` function, since the shipped one is not.

**Meaning.** Trigrams know nothing about language. `flowering shrub` and `flowering bush` score 0.48 purely on the shared first word; the synonym contributes nothing. There is no stemming, no synonym dictionary, no relevance model. That is precisely the gap full-text search fills, which is why the two belong together rather than in competition.

**CJK and other scripts without word separators** get little from trigrams, since the padding-and-splitting model assumes space-delimited words.

---

### Putting It Together

The production shape is tiered: try exact containment first, fall back to fuzzy only when it finds nothing, and rank the fuzzy results by word similarity.

```sql
CREATE OR REPLACE FUNCTION search_catalog(query text, max_rows int DEFAULT 5)
RETURNS TABLE (listing_id bigint, label text, match_kind text, score real)
LANGUAGE sql STABLE AS $$
    WITH exact AS (
        SELECT l.listing_id, l.full_label, 'exact'::text AS kind, 1.0::real AS score
          FROM nursery_listings l
         WHERE l.full_label ILIKE '%' || query || '%'
         LIMIT max_rows
    ), fuzzy AS (
        SELECT l.listing_id, l.full_label, 'fuzzy'::text, word_similarity(query, l.full_label)
          FROM nursery_listings l
         WHERE query <% l.full_label
         ORDER BY query <<-> l.full_label
         LIMIT max_rows
    )
    SELECT * FROM exact
     UNION ALL
    SELECT * FROM fuzzy WHERE NOT EXISTS (SELECT 1 FROM exact)
     LIMIT max_rows;
$$;
```

Each branch uses the index that suits it — `ILIKE` and `<%` hit GIN, the `<<->` ordering hits GiST — which is the concrete reason to keep both. The behaviour across query quality:

```sql
SELECT * FROM search_catalog('limelite', 3);
```

```
 listing_id |                  label                   | match_kind |   score
------------+------------------------------------------+------------+-----------
      32209 | Viburnum occidentalis 'Limelight' 1 gal  | fuzzy      | 0.6666667
      32208 | Viburnum occidentalis 'Limelight' 1 gal  | fuzzy      | 0.6666667
      32255 | Viburnum occidentalis 'Limelight' 10 gal | fuzzy      | 0.6666667
```

A correctly spelled term returns `exact` rows at score 1.0, `hydranga` returns hydrangeas at 0.78, and genuine nonsense returns zero rows rather than a page of weak matches — which matters, because a fuzzy search that always returns something is not a search, it is a random product recommender.

---

### Conclusion

Typo tolerance in Postgres is one `CREATE EXTENSION` away, and the mechanism is simple enough to hold in your head: split into three-character shingles, compare the sets, threshold the ratio. What is not simple is the surface around it, and the two decisions that matter both have unhelpful defaults.

Use `%` only when comparing whole strings to whole strings. For finding a term inside a longer field — which is nearly every product search — use `<%` or `<<%`, or accept that you are discarding most of your matches for no reason. Then build both index types unless you have measured that you only need one, because their capabilities are complements rather than alternatives, and the operator you did not index for does not run slowly, it runs as a sequential scan.

Trigrams are the right tool for misspellings, near-duplicate detection, and accelerating unanchored `LIKE`. They are the wrong tool for relevance ranking across documents, synonyms, or multi-field scoring with boosts — that is what a dedicated search engine sells, and it is a real product rather than an operator. The honest boundary is this: if your users are misspelling names, `pg_trgm` solves it completely and you should not run a second data store for it. If they are asking questions and expecting the best answer ranked out of many fields, you have a relevance problem, and trigrams have nothing to say about relevance.
