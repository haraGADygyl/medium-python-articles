DROP TABLE IF EXISTS meter_reading;
CREATE TABLE meter_reading (
    reading_id   bigserial PRIMARY KEY,
    inverter_id  int         NOT NULL,
    read_at      timestamptz NOT NULL,
    watt_hours   numeric(9,2) NOT NULL,
    dc_volts     numeric(6,2) NOT NULL
);
INSERT INTO meter_reading (inverter_id, read_at, watt_hours, dc_volts)
SELECT (random() * 40000)::int + 1,
       now() - (random() * 400) * interval '1 day',
       round((random() * 9000)::numeric, 2),
       round((random() * 600)::numeric, 2)
FROM generate_series(1, 20000000);
CREATE INDEX meter_reading_inverter_read_at ON meter_reading (inverter_id, read_at);
ANALYZE meter_reading;
