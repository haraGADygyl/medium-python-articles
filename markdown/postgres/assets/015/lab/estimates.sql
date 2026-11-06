-- Estimate experiments, in the order the article reports them. Run after setup.sql.
-- e4: impossible combos and GROUP BY with dependencies only
SET max_parallel_workers_per_gather = 0;
\echo == impossible combo, deps only
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE vehicle_make='Tesla' AND vehicle_model='Leaf';
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE city='Atlanta' AND state='TX';
\echo == group by estimates
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT city, state, vehicle_make, vehicle_model, count(*) FROM charge_session GROUP BY 1,2,3,4;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT station_id, city, state, vehicle_make, vehicle_model, count(*) FROM charge_session GROUP BY 1,2,3,4,5;

-- e5: ndistinct + dependencies + mcv, sizes, ANALYZE time
SET max_parallel_workers_per_gather = 0;
DROP STATISTICS charge_session_place, charge_session_vehicle;
\timing on
ANALYZE charge_session;
ANALYZE charge_session;
CREATE STATISTICS charge_session_place (ndistinct, dependencies, mcv) ON city, state FROM charge_session;
CREATE STATISTICS charge_session_vehicle (ndistinct, dependencies, mcv) ON vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;
ANALYZE charge_session;
\timing off
SELECT statistics_name, n_distinct FROM pg_stats_ext WHERE tablename='charge_session';
SELECT s.stxname, pg_size_pretty(pg_column_size(d.*)::bigint) FROM pg_statistic_ext s JOIN pg_statistic_ext_data d ON d.stxoid=s.oid;

SELECT count(*) AS mcv_items FROM pg_stats_ext, unnest(most_common_freqs) WHERE statistics_name='charge_session_vehicle';
\echo == estimates
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session s WHERE s.city='Atlanta' AND s.state='GA' AND s.vehicle_make='Nissan' AND s.vehicle_model='Leaf' AND s.connector='CHAdeMO';
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE vehicle_make='Tesla' AND vehicle_model='Leaf';
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE city='Atlanta' AND state='TX';
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT city, state, vehicle_make, vehicle_model, count(*) FROM charge_session GROUP BY 1,2,3,4;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT city, state, count(*) FROM charge_session GROUP BY 1,2;

-- e6/e7: one five-column object, target 100 vs 2000, ANALYZE time per kind
SET max_parallel_workers_per_gather = 0;
DROP STATISTICS IF EXISTS charge_session_place, charge_session_vehicle, charge_session_all;
CREATE STATISTICS charge_session_all ON city, state, vehicle_make, vehicle_model, connector FROM charge_session;
\timing on
ANALYZE charge_session;
\timing off
SELECT count(*) AS mcv_items, round(sum(f)::numeric,3) AS covered FROM pg_stats_ext, unnest(most_common_freqs) f WHERE statistics_name='charge_session_all';
SELECT pg_size_pretty(pg_column_size(d.*)::bigint) FROM pg_statistic_ext s JOIN pg_statistic_ext_data d ON d.stxoid=s.oid;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session s WHERE s.city='Atlanta' AND s.state='GA' AND s.vehicle_make='Nissan' AND s.vehicle_model='Leaf' AND s.connector='CHAdeMO';
ALTER STATISTICS charge_session_all SET STATISTICS 2000;
\timing on
ANALYZE charge_session;
\timing off
SELECT count(*) AS mcv_items, round(sum(f)::numeric,3) AS covered FROM pg_stats_ext, unnest(most_common_freqs) f WHERE statistics_name='charge_session_all';
SELECT pg_size_pretty(pg_column_size(d.*)::bigint) FROM pg_statistic_ext s JOIN pg_statistic_ext_data d ON d.stxoid=s.oid;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session s WHERE s.city='Atlanta' AND s.state='GA' AND s.vehicle_make='Nissan' AND s.vehicle_model='Leaf' AND s.connector='CHAdeMO';
SET max_parallel_workers_per_gather = 0;
\timing on
DROP STATISTICS charge_session_all;
CREATE STATISTICS charge_session_all (mcv) ON city, state, vehicle_make, vehicle_model, connector FROM charge_session;
ALTER STATISTICS charge_session_all SET STATISTICS 2000;
ANALYZE charge_session;
DROP STATISTICS charge_session_all;
CREATE STATISTICS charge_session_all (dependencies) ON city, state, vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;
DROP STATISTICS charge_session_all;
CREATE STATISTICS charge_session_all (ndistinct) ON city, state, vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;
DROP STATISTICS charge_session_all;
CREATE STATISTICS charge_session_all (mcv) ON city, state, vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session;
\timing off
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session s WHERE s.city='Atlanta' AND s.state='GA' AND s.vehicle_make='Nissan' AND s.vehicle_model='Leaf' AND s.connector='CHAdeMO';
DROP STATISTICS charge_session_all;

-- e8: empty before ANALYZE, cross-table, expressions, IN
SET max_parallel_workers_per_gather = 0;
CREATE STATISTICS charge_session_place (ndistinct, dependencies, mcv) ON city, state FROM charge_session;
CREATE STATISTICS charge_session_vehicle (ndistinct, dependencies, mcv) ON vehicle_make, vehicle_model, connector FROM charge_session;
ANALYZE charge_session; ANALYZE charge_station;
\echo == empty before analyze?
CREATE STATISTICS charge_session_tmp (dependencies) ON station_id, city FROM charge_session;
SELECT statistics_name, dependencies IS NULL AS empty FROM pg_stats_ext WHERE statistics_name='charge_session_tmp';
DROP STATISTICS charge_session_tmp;
\echo == cross table
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session s JOIN charge_station st USING (station_id) WHERE st.city='Atlanta' AND s.vehicle_model='Leaf' AND s.city='Atlanta';
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session s JOIN charge_station st USING (station_id) WHERE st.city='Atlanta' AND st.state='GA' AND s.vehicle_model='Leaf';
\echo == expression
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE lower(city)='atlanta' AND state='GA';
CREATE STATISTICS charge_session_place_ci ON lower(city), state FROM charge_session;
ANALYZE charge_session;
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE lower(city)='atlanta' AND state='GA';
DROP STATISTICS charge_session_place_ci;
\echo == IN and range
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE city IN ('Atlanta','Boise') AND state IN ('GA','ID');
EXPLAIN (ANALYZE, TIMING OFF, SUMMARY OFF) SELECT count(*) FROM charge_session WHERE vehicle_make='Nissan' AND connector='CHAdeMO';
