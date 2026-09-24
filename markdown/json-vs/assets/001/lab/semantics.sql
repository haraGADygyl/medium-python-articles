-- What each type keeps of the text you gave it. Run: psql -X -f semantics.sql
\pset footer off

-- 1. Whitespace, key order, duplicate keys
SELECT '{"buoy_id": "NE-08",  "notes": null, "buoy_id": "HB-214"}'::json  AS as_json;
SELECT '{"buoy_id": "NE-08",  "notes": null, "buoy_id": "HB-214"}'::jsonb AS as_jsonb;

-- 2. Numbers: jsonb stores numeric, not the digits you typed
SELECT '{"wave_height_m": 3.50, "samples": 2e3, "observation_id": 9007199254740993}'::jsonb
       AS as_jsonb;

-- 3. A NUL escape: legal JSON, not storable as Postgres text
SELECT '{"notes": "\u0000"}'::json AS as_json;
SELECT '{"notes": "\u0000"}'::jsonb AS as_jsonb;
SELECT '{"notes": "\u0000"}'::json ->> 'notes' AS read_back;

-- 4. Equality
SELECT '{"buoy_id": "NE-08", "qc_passed": false}'::jsonb
     = '{"qc_passed": false, "buoy_id": "NE-08"}'::jsonb AS jsonb_equal;
SELECT '{"buoy_id": "NE-08"}'::json = '{"buoy_id": "NE-08"}'::json AS json_equal;
