-- After switching the default: repack the v4-era index online.
SELECT pg_size_pretty(pg_relation_size('delivery_v4_pkey')) AS before,
       (pgstatindex('delivery_v4_pkey')).avg_leaf_density AS density_before;
\timing on
REINDEX INDEX CONCURRENTLY delivery_v4_pkey;
\timing off
SELECT pg_size_pretty(pg_relation_size('delivery_v4_pkey')) AS after,
       (pgstatindex('delivery_v4_pkey')).avg_leaf_density AS density_after,
       (SELECT count(*) FROM delivery_v4) AS rows_v4,
       pg_size_pretty(pg_relation_size('delivery_v7_pkey')) AS v7_pkey,
       (SELECT count(*) FROM delivery_v7) AS rows_v7;
