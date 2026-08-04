# Graph Queries with Recursive CTEs — You Don't Need Neo4j

#### Friend-of-friend, shortest path, dependency trees — Postgres solves 95% of graph problems with one keyword and a properly indexed edges table.

**By Tihomir Manushev**

*Apr 18, 2026 · 9 min read*

---

Your application has graph-shaped data. Comment threads with replies to replies. Organizational hierarchies five levels deep. Package dependencies that pull in other packages. The instinct is to reach for a graph database — Neo4j, Dgraph, ArangoDB — because the relational model "can't do graphs." It can. PostgreSQL has had a standard SQL feature for graph traversal since version 8.4: the `WITH RECURSIVE` query.

A recursive CTE lets you walk edges iteratively — start at a node, find its neighbors, find their neighbors, repeat until you run out — and return the whole traversal as a single result set. It handles trees, directed acyclic graphs, and cyclic graphs. With a properly indexed edges table, it scales to tens of millions of edges with sub-second response times for typical depths. For the vast majority of applications that have *some* graph data but are not primarily graph-native, recursive CTEs eliminate the operational and financial cost of running a second specialized database alongside your primary Postgres instance.

The pattern looks unfamiliar the first time you see it, but the mechanics are simple: two queries stitched together with `UNION ALL`, one for where to start and one for how to move one step further. Once the shape clicks, you can express ancestry lookups, descendant traversals, shortest paths, and transitive closures as ordinary SQL queries that join naturally with the rest of your schema.

---

### The Graph Is Already in Your Database

Before writing queries, you need to know how to store the graph. Relational databases support three main models for hierarchical or graph data, and the choice affects everything that follows.

**Adjacency list** is the simplest. One row per edge: a source column and a destination column. `child_id` points to `parent_id`. This is how every tree you have ever modeled in a relational database probably works already. Recursive CTEs are purpose-built for adjacency lists.

**Materialized path** stores the full path to each node as a string or array — `"1.4.17.32"`. The `ltree` extension formalizes this with operators for ancestor, descendant, and prefix queries. It excels at reading paths but requires every insert, move, or delete to maintain the path column on all affected descendants.

**Nested sets** encode tree membership as numeric `lft` and `rgt` intervals. Queries become range comparisons, which are fast for reads but painful for writes — inserting a node near the root can require rewriting millions of rows.

For recursive CTEs, stick with adjacency list. It is the model the syntax was designed for, and the only one that handles arbitrary directed graphs (not just trees). If your workload is overwhelmingly read-heavy and your paths rarely change, `ltree` or materialized views can give you faster reads — but they pay for it in write complexity, and the speedup usually only matters at a scale most applications never reach.

Here is a schema for package dependencies — a familiar directed acyclic graph where every package depends on zero or more other packages:

```sql
CREATE TABLE packages (
    package_id   int PRIMARY KEY,
    name         text NOT NULL UNIQUE,
    version      text NOT NULL,
    install_size bigint NOT NULL
);

CREATE TABLE package_dependencies (
    package_id        int NOT NULL REFERENCES packages(package_id),
    depends_on_id     int NOT NULL REFERENCES packages(package_id),
    PRIMARY KEY (package_id, depends_on_id)
);

CREATE INDEX idx_deps_depends_on ON package_dependencies (depends_on_id);
```

Two things deserve attention. First, the primary key on `(package_id, depends_on_id)` prevents duplicate edges and gives you a B-tree index that supports forward traversal (find dependencies of package X). Second, the explicit index on `depends_on_id` supports reverse traversal (find everything that depends on package X) — the "who uses this?" query. Without that reverse index, recursive CTEs walking upward degrade to sequential scans and become prohibitively slow on any real dataset.

Seed some data to make queries concrete:

```sql
INSERT INTO packages VALUES
    (1, 'web-server',      '2.1.0',  45000),
    (2, 'http-parser',     '1.8.3',  12000),
    (3, 'tls-library',     '3.4.1',  85000),
    (4, 'crypto-core',     '5.2.0',  34000),
    (5, 'logging',         '1.0.2',   6000),
    (6, 'compression',     '2.3.0',  18000),
    (7, 'string-utils',    '0.9.1',   3000),
    (8, 'analytics-agent', '1.2.4',  22000);

INSERT INTO package_dependencies VALUES
    (1, 2), (1, 3), (1, 5),    -- web-server needs http-parser, tls, logging
    (2, 7),                     -- http-parser needs string-utils
    (3, 4), (3, 6),            -- tls-library needs crypto-core and compression
    (4, 5),                     -- crypto-core needs logging
    (6, 5),                     -- compression needs logging
    (8, 1), (8, 3);            -- analytics-agent needs web-server and tls directly
```

The resulting graph: `web-server` transitively depends on seven other packages through a web of shared subdependencies. `logging` is used everywhere. `analytics-agent` depends on `tls-library` both directly and transitively through `web-server` — a classic diamond dependency that shows up in every real package ecosystem. This is exactly the kind of small-but-nontrivial graph that illustrates why recursive queries matter: writing any of the interesting questions ("what does X pull in?", "who uses Y?", "is there a path from A to B?") without `WITH RECURSIVE` means either dozens of self-joins or giving up and doing the traversal in application code.

---

### Building Graph Queries with WITH RECURSIVE

A recursive CTE has two parts joined by `UNION ALL`. The **anchor** produces the starting rows — the "where we begin" set. The **recursive term** references the CTE by name and produces the next layer based on what the previous iteration found. PostgreSQL keeps iterating until the recursive term returns zero rows, at which point the traversal naturally terminates. There is no explicit loop, no external counter, no procedural code. The recursion is declarative: you describe how to go one step further, and the engine figures out the rest.

Find all transitive dependencies of `web-server`:

```sql
WITH RECURSIVE deps AS (
    -- Anchor: direct dependencies of web-server
    SELECT package_id, depends_on_id, 1 AS depth
    FROM package_dependencies
    WHERE package_id = 1

    UNION ALL

    -- Recursive: dependencies of what we already found
    SELECT pd.package_id, pd.depends_on_id, d.depth + 1
    FROM package_dependencies pd
    JOIN deps d ON pd.package_id = d.depends_on_id
)
SELECT DISTINCT p.name, p.version, d.depth
FROM deps d
JOIN packages p ON p.package_id = d.depends_on_id
ORDER BY d.depth, p.name;
```

```
      name      | version | depth
----------------+---------+-------
 http-parser    | 1.8.3   |     1
 logging        | 1.0.2   |     1
 tls-library    | 3.4.1   |     1
 crypto-core    | 5.2.0   |     2
 compression    | 2.3.0   |     2
 string-utils   | 0.9.1   |     2
 logging        | 1.0.2   |     3
```

The `depth` column tracks how far from the root each dependency lives. Notice `logging` appears twice — it is a direct dependency of `web-server` and also pulled in transitively through `crypto-core`. A `DISTINCT` on `package_id` (rather than the full row) would dedupe, but keeping duplicates is often useful: it tells you how many paths lead to a package, which matters for diamond-dependency analysis, security audits ("how many ways can this vulnerable package be reached?"), and build-system optimizations.

Trace through what happens during execution. The anchor runs first and returns three rows — the direct edges from `web-server`. The recursive term then joins those three rows against `package_dependencies`, treating each previous result's `depends_on_id` as the next hop's `package_id`. It finds the dependencies of `http-parser`, `tls-library`, and `logging`. Those become the input for the next iteration. The process continues until an iteration returns no new rows, at which point PostgreSQL unions all the layers together and returns them as the CTE's final result.

**Reverse the direction.** Who depends on `logging`? Start from `logging` and walk up the dependents:

```sql
WITH RECURSIVE dependents AS (
    SELECT package_id, depends_on_id, 1 AS depth
    FROM package_dependencies
    WHERE depends_on_id = 5  -- logging

    UNION ALL

    SELECT pd.package_id, pd.depends_on_id, d.depth + 1
    FROM package_dependencies pd
    JOIN dependents d ON pd.depends_on_id = d.package_id
)
SELECT DISTINCT p.name, d.depth
FROM dependents d
JOIN packages p ON p.package_id = d.package_id
ORDER BY d.depth, p.name;
```

This query walks edges in the opposite direction — the join condition flips from `pd.package_id = d.depends_on_id` to `pd.depends_on_id = d.package_id`. The reverse index on `depends_on_id` makes this as fast as the forward traversal. Without that index, the same query would fall back to sequential scans on every iteration, and a graph with a few hundred thousand edges would take seconds instead of milliseconds. Bidirectional queries are the norm in production — you always end up needing both "what does X depend on?" and "what depends on X?" — so index both columns from the start.

**Shortest path.** Recursive CTEs naturally produce breadth-first results because each iteration adds one level of depth. PostgreSQL 14 added the `SEARCH BREADTH FIRST BY` clause to make this explicit and to return results in traversal order:

```sql
WITH RECURSIVE deps AS (
    SELECT package_id, depends_on_id
    FROM package_dependencies
    WHERE package_id = 1

    UNION ALL

    SELECT pd.package_id, pd.depends_on_id
    FROM package_dependencies pd
    JOIN deps d ON pd.package_id = d.depends_on_id
) SEARCH BREADTH FIRST BY depends_on_id SET ordering
SELECT p.name, ordering
FROM deps d JOIN packages p ON p.package_id = d.depends_on_id
ORDER BY ordering;
```

For shortest-path between specific nodes, add a `WHERE target_found` condition in the outer query and pick the minimum depth. Recursive CTEs cannot short-circuit mid-traversal — they always compute the full transitive closure reachable from the anchor — so this is best for small-to-medium graphs or when cached. If you are computing shortest paths on graphs with millions of nodes and need to terminate early, the recursive CTE approach stops making sense and a dedicated graph database earns its keep. But for every tree of comments, every organizational chart, every package dependency graph short of the entire npm registry, the full-closure cost is negligible.

**Aggregate across the graph.** Want the total install size of everything `web-server` pulls in? Wrap the recursive CTE and aggregate:

```sql
WITH RECURSIVE deps AS (
    SELECT depends_on_id
    FROM package_dependencies WHERE package_id = 1
    UNION
    SELECT pd.depends_on_id
    FROM package_dependencies pd
    JOIN deps d ON pd.package_id = d.depends_on_id
)
SELECT sum(install_size) AS total_bytes
FROM packages
WHERE package_id IN (SELECT depends_on_id FROM deps);
```

Note the `UNION` (not `UNION ALL`) — it deduplicates shared dependencies automatically, so `logging` only contributes its size once even though three packages depend on it.

---

### Performance, Cycles, and When Neo4j Actually Wins

Recursive CTEs are fast when the edges table is properly indexed and slow otherwise. There is no middle ground. The single most important performance rule: **every column used in the recursive join must be indexed**. Forward traversal needs an index on `package_id`. Reverse traversal needs an index on `depends_on_id`. Missing one turns a millisecond query into a minute-long table scan.

For tens of millions of edges with typical traversal depths of 2 to 10 levels, recursive CTEs return results in milliseconds on modest hardware. Past 20 levels of depth, performance degrades quickly because the query planner cannot predict recursion depth and the intermediate result sets balloon. Past a billion edges total, even well-indexed recursive CTEs start to struggle — not because the syntax breaks down, but because the intermediate tuples no longer fit comfortably in memory.

**Cycles** are a correctness concern, not just performance. Package dependency graphs should be acyclic, but user-generated graphs (social networks, comment threads with cross-references) can have cycles that cause recursive CTEs to loop forever. PostgreSQL 14 added the `CYCLE` clause to handle this:

```sql
WITH RECURSIVE deps AS (
    SELECT package_id, depends_on_id FROM package_dependencies WHERE package_id = 1
    UNION ALL
    SELECT pd.package_id, pd.depends_on_id
    FROM package_dependencies pd
    JOIN deps d ON pd.package_id = d.depends_on_id
) CYCLE depends_on_id SET is_cycle USING path
SELECT * FROM deps WHERE NOT is_cycle;
```

The `CYCLE` clause makes Postgres track visited nodes in an automatically-maintained `path` array and mark repeat visits with `is_cycle = true`. Before PG14, you had to maintain this path array manually with `array_append(path, id)` and filter `WHERE NOT id = ANY(path)` — still correct, just verbose.

**When Neo4j wins.** Specialized graph databases earn their cost when the graph *is* your primary data model. Recommendation engines that traverse hundreds of edges per query. Social networks computing six-degrees-of-separation across billions of users. Fraud detection systems walking 50-deep chains of suspicious transactions in real time. For those workloads, Neo4j's native graph storage — where edges are pointers rather than indexed rows — is genuinely faster. For everything else, recursive CTEs let you keep your graph data colocated with the rest of your application, transactional with the rest of your writes, and queryable with the same SQL your team already knows.

---

### Conclusion

`WITH RECURSIVE` turns PostgreSQL into a capable graph database for the 95% of use cases that don't need specialized infrastructure. Index your edges table in both directions. Use the `CYCLE` clause on any graph that might contain cycles. Add `SEARCH BREADTH FIRST BY` when traversal order matters. Keep your graph data in the same database as the rest of your application, and skip the second database until a workload genuinely demands it. Neo4j is a real tool for real problems — but most problems don't need it, and reaching for it reflexively is how teams end up with operational complexity they never earned.
