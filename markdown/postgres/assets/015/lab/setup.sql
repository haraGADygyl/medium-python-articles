-- Lab for 015: a denormalised EV-charging session table whose columns are
-- correlated on purpose (city -> state, model -> make, model -> connector).
-- 10M sessions, ~2,500 stations. Deterministic: setseed() before every random().
\timing on
DROP TABLE IF EXISTS charge_session, charge_station, city_dim, model_dim, tariff_rate CASCADE;

CREATE TABLE city_dim (city text, state text, utility text, weight int);
INSERT INTO city_dim VALUES
  ('Austin','TX','Austin Energy',40), ('Houston','TX','CenterPoint',55),
  ('Dallas','TX','Oncor',50), ('San Antonio','TX','CPS Energy',25),
  ('Los Angeles','CA','LADWP',90), ('San Francisco','CA','PG&E',70),
  ('San Diego','CA','SDG&E',50), ('San Jose','CA','PG&E',55),
  ('Sacramento','CA','SMUD',25), ('Seattle','WA','Seattle City Light',45),
  ('Spokane','WA','Avista',8), ('Portland','OR','PGE Oregon',35),
  ('Eugene','OR','EWEB',8), ('Portland','ME','Central Maine Power',4),
  ('New York','NY','Con Edison',70), ('Buffalo','NY','National Grid',10),
  ('Chicago','IL','ComEd',45), ('Denver','CO','Xcel Energy',35),
  ('Boulder','CO','Xcel Energy',12), ('Phoenix','AZ','APS',35),
  ('Tucson','AZ','TEP',12), ('Miami','FL','FPL',35), ('Orlando','FL','OUC',25),
  ('Tampa','FL','TECO',20), ('Atlanta','GA','Georgia Power',30),
  ('Boston','MA','Eversource',35), ('Boise','ID','Idaho Power',10),
  ('Salt Lake City','UT','Rocky Mountain Power',18), ('Las Vegas','NV','NV Energy',20),
  ('Minneapolis','MN','Xcel Energy',18), ('Charlotte','NC','Duke Energy',18),
  ('Raleigh','NC','Duke Energy',15);

CREATE TABLE model_dim (make text, model text, weight int);
INSERT INTO model_dim VALUES
  ('Tesla','Model Y',190), ('Tesla','Model 3',150), ('Tesla','Model S',25),
  ('Tesla','Model X',20), ('Tesla','Cybertruck',15),
  ('Chevrolet','Bolt EV',50), ('Chevrolet','Bolt EUV',25), ('Chevrolet','Equinox EV',25),
  ('Ford','Mustang Mach-E',55), ('Ford','F-150 Lightning',35),
  ('Hyundai','Ioniq 5',50), ('Hyundai','Kona Electric',20),
  ('Kia','EV6',40), ('Kia','Niro EV',20), ('Kia','EV9',15),
  ('Nissan','Leaf',45), ('Nissan','Ariya',15),
  ('Rivian','R1S',30), ('Rivian','R1T',25), ('Volkswagen','ID.4',45),
  ('BMW','i4',25), ('BMW','iX',20), ('Mercedes','EQE',15), ('Mercedes','EQS',10),
  ('Polestar','Polestar 2',20), ('Lucid','Air',15);

-- Stations: about one per 4 weight points, so big cities get more of them.
SELECT setseed(0.15);
CREATE TABLE charge_station AS
SELECT row_number() OVER (ORDER BY c.city, c.state, s)::int AS station_id,
       c.city, c.state,
       (ARRAY['VoltPath','AmpGrid','ChargeHub','Plugwell'])[1 + floor(random() * 4)::int] AS operator,
       (ARRAY[50, 150, 250, 350])[1 + floor(random() * 4)::int] AS max_kw
FROM city_dim c, generate_series(1, c.weight * 8) AS s;
ALTER TABLE charge_station ADD PRIMARY KEY (station_id);

-- One array slot per weight point, so a uniform pick in the array is a weighted pick.
ALTER TABLE city_dim ADD COLUMN city_no serial;
ALTER TABLE model_dim ADD COLUMN model_no serial;
CREATE TEMP TABLE city_slots AS
SELECT array_agg(city_no ORDER BY city_no) AS slots
FROM city_dim, generate_series(1, weight);
CREATE TEMP TABLE model_slots AS
SELECT array_agg(model_no ORDER BY model_no) AS slots
FROM model_dim, generate_series(1, weight);
CREATE TEMP TABLE station_ranges AS
SELECT city, state, min(station_id) AS lo, count(*) AS n
FROM charge_station GROUP BY city, state;

SELECT setseed(0.42);
CREATE TABLE charge_session AS
WITH picked AS (
    SELECT g,
           cs.slots[1 + floor(random() * array_length(cs.slots, 1))::int] AS city_no,
           ms.slots[1 + floor(random() * array_length(ms.slots, 1))::int] AS model_no,
           random() AS r_conn, random() AS r_station, random() AS r_time, random() AS r_kwh
    FROM generate_series(1, 10000000) AS g, city_slots cs, model_slots ms
)
SELECT p.g::bigint AS session_id,
       (sr.lo + floor(p.r_station * sr.n))::int AS station_id,
       cd.city AS city, cd.state AS state,
       md.make AS vehicle_make, md.model AS vehicle_model,
       CASE
         WHEN md.make = 'Tesla'  THEN CASE WHEN p.r_conn < 0.92 THEN 'NACS' ELSE 'CCS1' END
         WHEN md.model = 'Leaf'   THEN CASE WHEN p.r_conn < 0.97 THEN 'CHAdeMO' ELSE 'J1772' END
         ELSE CASE WHEN p.r_conn < 0.70 THEN 'CCS1' ELSE 'J1772' END
       END AS connector,
       CASE WHEN md.model = 'Leaf' AND p.r_conn >= 0.97 THEN 'L2'
            WHEN md.make NOT IN ('Tesla') AND md.model <> 'Leaf' AND p.r_conn >= 0.70 THEN 'L2'
            ELSE 'DCFC' END AS charger_level,
       timestamptz '2026-01-01' + p.r_time * interval '300 days' AS started_at,
       round((5 + p.r_kwh * 70)::numeric, 2) AS kwh
FROM picked p
JOIN city_dim cd USING (city_no)
JOIN model_dim md USING (model_no)
JOIN station_ranges sr ON sr.city = cd.city AND sr.state = cd.state;

ALTER TABLE charge_session ADD PRIMARY KEY (session_id);
CREATE INDEX ON charge_session (station_id);
CREATE INDEX ON charge_session (vehicle_model);
CREATE INDEX charge_session_city_model_idx ON charge_session (city, vehicle_model);

-- Tariff matrix: one price per state, connector and month. 816 rows, no index.
SELECT setseed(0.7);
CREATE TABLE tariff_rate AS
SELECT row_number() OVER ()::int AS tariff_id, st.state, c.connector, m AS month_no,
       tstzrange(timestamptz '2026-01-01' + (m - 1) * interval '1 month',
                 timestamptz '2026-01-01' + m * interval '1 month') AS valid_during,
       round((0.30 + random() * 0.35)::numeric, 3) AS usd_per_kwh
FROM (SELECT DISTINCT state FROM city_dim ORDER BY 1) st,
     (VALUES ('NACS'),('CCS1'),('CHAdeMO'),('J1772')) c(connector),
     generate_series(1, 12) m;
VACUUM ANALYZE charge_session, charge_station, tariff_rate;
SELECT pg_size_pretty(pg_total_relation_size('charge_session')) AS total,
       pg_size_pretty(pg_relation_size('charge_session')) AS heap,
       count(*) FROM charge_session;
