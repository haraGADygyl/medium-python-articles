# The Planner Thinks Your Query Returns One Row. It Returns 12,938.

#### Five dashboard filters, each one estimated correctly, multiplied into a guess of one row. Two CREATE STATISTICS objects made the query 20 times faster, and one bigger object fixed nothing

**By Tihomir Manushev**

*Nov 6, 2026 · 9 min read*

---

A charging-network dashboard has five dropdowns: state, city, make, model, connector. Pick Georgia, Atlanta, Nissan, Leaf and CHAdeMO, and the weekly revenue chart takes almost a second to draw. The table holds 10 million sessions, the right index exists, and the query reads 12,938 rows. Nothing about it should take 848 ms.

`EXPLAIN ANALYZE` shows the reason in one line: the planner expected **1 row**. Each of the five filters was estimated correctly on its own. The planner multiplied them together as if a Leaf's connector had nothing to do with its model, or Atlanta's state with its city. That guess led it to a join plan that suits one row and breaks down at thirteen thousand.

Two `CREATE STATISTICS` statements brought it to 41 ms. A single object over all five columns left the estimate at 1 row, and making it work cost 87 seconds per `ANALYZE`.

Everything below ran on PostgreSQL 18.6 in Docker on a Ryzen 5 3600, `shared_buffers = 1GB`, `jit = off`, with parallel query off so the plans stay readable.

---

### A query whose filters all agree with each other

The sessions table is denormalised, like most analytics tables: every row carries the city and state of its station and the make and model of the car.

```sql
CREATE TABLE charge_session (
    session_id     bigint PRIMARY KEY,
    station_id     integer     NOT NULL,
    city           text        NOT NULL,
    state          text        NOT NULL,
    vehicle_make   text        NOT NULL,
    vehicle_model  text        NOT NULL,
    connector      text        NOT NULL,   -- NACS, CCS1, CHAdeMO, J1772
    charger_level  text        NOT NULL,   -- DCFC or L2
    started_at     timestamptz NOT NULL,
    kwh            numeric     NOT NULL
);
CREATE INDEX charge_session_city_model_idx ON charge_session (city, vehicle_model);

CREATE TABLE tariff_rate (
    tariff_id     integer,
    state         text,
    connector     text,
    month_no      integer,
    valid_during  tstzrange,
    usd_per_kwh   numeric
);
```

I generated 10 million sessions across 32 cities and 26 models (922 MB of heap) and planted the correlations every real fleet has. A model always belongs to one make. A Leaf plugs into CHAdeMO 97% of the time, a Tesla into NACS 92% of the time. A city sits in one state, except Portland, which exists in Oregon and in Maine. `tariff_rate` is the price matrix: 816 rows, one per state, connector and month, and no index, because nobody indexes a table that small.

The dashboard query:

```sql
SELECT date_trunc('week', s.started_at) AS week,
       round(sum(s.kwh * t.usd_per_kwh), 2) AS revenue_usd
FROM charge_session s
JOIN tariff_rate t
  ON t.state = s.state
 AND t.connector = s.connector
 AND s.started_at <@ t.valid_during
WHERE s.city = 'Atlanta' AND s.state = 'GA'
  AND s.vehicle_make = 'Nissan' AND s.vehicle_model = 'Leaf'
  AND s.connector = 'CHAdeMO'
GROUP BY 1
ORDER BY 1;
```

Three of the five filters are redundant: Atlanta implies Georgia, Leaf implies Nissan and, almost always, CHAdeMO. Here is the plan, with costs trimmed so the estimated rows stay readable:

```
 Nested Loop  (rows=1 width=19) (actual time=2.942..940.086 rows=12938.00 loops=1)
   Join Filter: (s.started_at <@ t.valid_during)
   Rows Removed by Join Filter: 142318
   Buffers: shared hit=116138
   ->  Bitmap Heap Scan on charge_session s  (rows=1 width=22) (actual time=2.872..54.965 rows=12938.00 loops=1)
         Recheck Cond: ((city = 'Atlanta'::text) AND (vehicle_model = 'Leaf'::text))
         Filter: ((state = 'GA'::text) AND (connector = 'CHAdeMO'::text) AND (vehicle_make = 'Nissan'::text))
         ->  Bitmap Index Scan on charge_session_city_model_idx  (rows=13309 width=0) (actual ... rows=13349.00 loops=1)
   ->  Seq Scan on tariff_rate t  (rows=12 width=36) (actual time=0.054..0.066 rows=12.00 loops=12938)
         Filter: ((state = 'GA'::text) AND (connector = 'CHAdeMO'::text))
         Rows Removed by Filter: 804
         Buffers: shared hit=103504
```

The index scan estimate of 13,309 is close to the real 13,349, because city and model really are independent in this data. Then the three remaining filters divide that by about thirteen thousand, and the scan ends at `rows=1`. For one outer row, a nested loop that scans `tariff_rate` once is the cheapest plan available, and caching the inner side would be wasted work. So the planner did neither. The inner seq scan ran 12,938 times, read 103,504 buffers out of a total of 116,138, and took 885 of the 940 milliseconds.

---

### Where the 1 comes from

The planner keeps statistics for each column separately. You can read the numbers it used straight out of `pg_stats`:

```sql
SELECT attname, v AS value, round(f::numeric, 4) AS freq
FROM pg_stats,
     unnest(most_common_vals::text::text[], most_common_freqs) AS m(v, f)
WHERE tablename = 'charge_session'
  AND (attname, v) IN (('city', 'Atlanta'), ('state', 'GA'),
                       ('vehicle_make', 'Nissan'), ('vehicle_model', 'Leaf'),
                       ('connector', 'CHAdeMO'));
```

```
    attname    |  value  |  freq
---------------+---------+--------
 state         | GA      | 0.0309
 vehicle_make  | Nissan  | 0.0597
 connector     | CHAdeMO | 0.0440
 vehicle_model | Leaf    | 0.0454
 city          | Atlanta | 0.0309
```

Each value comes with the fraction of sampled rows that hold it, and all five are accurate. The planner assumes the columns vary independently, so it multiplies: 0.0309 × 0.0309 × 0.0597 × 0.0454 × 0.0440 × 9,997,545 rows comes to 1.14, which rounds to 1. Each redundant filter shrank the estimate by another factor of 20 to 30.

---

### Functional dependencies: "this column decides that one"

**Extended statistics** are statistics on a group of columns, created by name and filled by `ANALYZE`. Columns go into the same object only when they actually depend on each other:

```sql
CREATE STATISTICS charge_session_place (dependencies)
    ON city, state FROM charge_session;
CREATE STATISTICS charge_session_vehicle (dependencies)
    ON vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;

SELECT statistics_name, dependencies
FROM pg_stats_ext WHERE tablename = 'charge_session';
```

```
    statistics_name     |                          dependencies
------------------------+------------------------------------------------------------------
 charge_session_place   | {"3 => 4": 0.962567, "4 => 3": 0.177833}
 charge_session_vehicle | {"5 => 6": 0.078600, "6 => 5": 1.000000, "7 => 5": 0.410867,
                        |  "7 => 6": 0.043233, "5, 7 => 6": 0.132400, "6, 7 => 5": 1.000000}
```

The numbers are column positions: 3 is `city`, 4 `state`, 5 `vehicle_make`, 6 `vehicle_model`, 7 `connector`. `"6 => 5": 1.000000` says the model decides the make in every sampled row. Once the model is known, the make filter costs nothing.

`"3 => 4"` is the interesting one. City decides state, yet its degree is 0.96, not 1.0. The degree is the share of rows whose city group maps to exactly one state. Portland covers 3.8% of the rows and maps to two, so every Portland row counts as a violation, Oregon and Maine alike: 1 − 0.038 = 0.962. One duplicated city name weakens the dependency for every other city in the table.

`"6 => 7"` is missing because no model decides the connector completely. Even the Leaf only reaches 97%. With the make and state filters handled, the estimate rose from 1 to 1,026. That is still 12 times too low, but more than one, and that alone changed the plan: the planner put a `Materialize` node over `tariff_rate`, scanned its 816 rows once, and replayed the 12 matching rows from memory 12,938 times. The query dropped from 848 ms to 42 ms, measured with `pgbench` over 20 runs.

---

### MCV lists: the combinations themselves

A dependency says "this column decides that one". A **multivariate MCV list** stores the most common *combinations* of values, with their frequencies, which is what the connector needs. Recreating both objects with all three kinds is the same statement with a longer list:

```sql
DROP STATISTICS charge_session_place, charge_session_vehicle;
CREATE STATISTICS charge_session_place (ndistinct, dependencies, mcv)
    ON city, state FROM charge_session;
CREATE STATISTICS charge_session_vehicle (ndistinct, dependencies, mcv)
    ON vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;

SELECT m.values, round(m.frequency::numeric, 5) AS frequency
FROM pg_statistic_ext s
JOIN pg_statistic_ext_data d ON d.stxoid = s.oid,
     pg_mcv_list_items(d.stxdmcv) AS m
WHERE s.stxname = 'charge_session_vehicle' AND m.values[1] = 'Nissan'
ORDER BY m.frequency DESC;
```

```
        values         | frequency
-----------------------+-----------
 {Nissan,Leaf,CHAdeMO} |   0.04397
 {Nissan,Ariya,CCS1}   |   0.01023
 {Nissan,Ariya,J1772}  |   0.00413
 {Nissan,Leaf,J1772}   |   0.00140
```

`pg_mcv_list_items` unpacks the stored list. Here the planner looks up the frequency of the exact combination the query asks for, 4.4%, instead of computing it. The vehicle object holds all 52 combinations that occur, which fits easily inside the default 100-item list, and the two objects take 1.3 kB and 2.0 kB of catalog space. The scan estimate became 12,848 against 12,938 actual, within 1%. The plan kept the same shape as with dependencies alone, at 41 ms:

```
statistics                       estimated rows   tariff_rate scanned   pgbench latency
none                                          1   12,938 times                   848 ms
dependencies                              1,026   once, materialized              42 ms
ndistinct + dependencies + mcv           12,848   once, materialized              41 ms
```

The MCV list earns its place on the queries where dependencies give the wrong answer. A dependency assumes the values you filter on agree with each other. Ask for `vehicle_make = 'Tesla' AND vehicle_model = 'Leaf'` with dependencies only, and the planner reasons "model decides make" and estimates every Leaf, 445,362 rows, for a query that returns zero. `city = 'Atlanta' AND state = 'TX'` got 278,059. With the MCV list, both came out at 1, because the combination is absent from a list that covers the whole table.

**ndistinct** fixes the other estimate this table got wrong: the number of groups. `GROUP BY city, state` was estimated at 527 groups for 32 real ones. `GROUP BY city, state, vehicle_make, vehicle_model` was estimated at 164,424 groups for 832. Both became exact. In a bigger query, that number becomes the row count the next join is planned for.

---

### One big statistics object is not better

The obvious shortcut is one object over all five columns. Here is what it bought:

```sql
CREATE STATISTICS charge_session_all
    ON city, state, vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;
```

`ANALYZE` went from 0.3 s to 2.3 s, and the dashboard query's estimate went back to **1 row**. City and vehicle combinations number up to 1,664. The default list holds 100 of them, covering 40.6% of the rows, and Atlanta's Leafs at 0.13% are not among them. The planner applies the MCV list first, finds no match, and falls back to a number close to the original.

Raising the object's target fixes the estimate and moves the cost somewhere else:

```sql
ALTER STATISTICS charge_session_all SET STATISTICS 2000;
ANALYZE charge_session;
```

The list grew to 1,577 items covering 99.8% of the rows, the estimate became 14,050, and `ANALYZE` took **87 seconds**. The target also sets the sample size, so the sample grew from 30,000 rows to 600,000. Over five columns, the dependency and ndistinct computations run for every subset of the columns. At the default target, dependencies alone cost 1.75 s and ndistinct 0.79 s on this object. Autovacuum will pay the 87 seconds every time the table changes by 10%.

Keep one small object per group of columns that really depend on each other. Raise the target on one object only when its combinations outnumber the list, never through `default_statistics_target`, which enlarges every column on every table, and time `ANALYZE` before and after.

---

### What extended statistics cannot see

**Other tables.** An object covers one table. Filter `charge_station.city = 'Atlanta'` and `charge_session.city = 'Atlanta'` in the same join, and the planner applies the city selectivity twice: 374 estimated, 13,349 actual. Dropping the session-side filter gave 13,469.

**Expressions, unless you name them.** `lower(city) = 'atlanta' AND state = 'GA'` was estimated at 1,427 for 293,098 rows. The column statistics do not apply to `lower(city)`. Since PostgreSQL 14, an object can be built on the expression itself, which brought the estimate to 293,964:

```sql
CREATE STATISTICS charge_session_place_ci ON lower(city), state FROM charge_session;
ANALYZE charge_session;
```

**Join conditions.** Even with exact scan estimates, the nested loop above was still estimated at 158 rows for 12,938, because `started_at <@ valid_during` across two tables gets a fixed default selectivity. Extended statistics only estimate filters within one table.

---

### Gotchas

**`CREATE STATISTICS` does nothing until `ANALYZE` runs.** Before that, `pg_stats_ext` has no row for the object at all, and plans stay the same. Autovacuum will not analyze just because an object appeared; it waits for 10% of the table to change. Run `ANALYZE` yourself in the same migration.

**`pg_upgrade` leaves them empty.** PostgreSQL 18's `pg_upgrade` carries ordinary column statistics over, but its documentation says statistics created with `CREATE STATISTICS` are not transferred. Analyze those tables after the upgrade, or the 1-row estimates come back.

**Dependencies only understand `=` and `IN`.** With both objects in place, `city IN ('Atlanta', 'Boise') AND state IN ('GA', 'ID')` was estimated at 397,951 for 390,862. Inequalities and `OR` on correlated columns are outside what dependencies handle, and the MCV kind is the one that covers them.

---

### Conclusion

The planner estimates each column well and every combination badly, because it multiplies selectivities as if columns were independent. In a denormalised table with redundant filters, those multiplications compound until 12,938 rows become 1, and a plan built for one row ran 20 times slower than it needed to.

Look for the pattern in `EXPLAIN ANALYZE`: a node whose estimated rows sit orders of magnitude below its actual rows, directly under a `Nested Loop` with a large `loops` count. Then group the columns your queries filter together, create one small statistics object per group with `dependencies` and `mcv`, run `ANALYZE` in the same migration, and check the estimate moved. Leave the five-column object out. It cost 87 seconds per `ANALYZE` to match what two small objects did in under half a second.
