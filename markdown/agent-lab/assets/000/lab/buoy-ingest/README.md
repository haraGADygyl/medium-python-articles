# buoy-ingest

Ingests observations from the north-east harbour buoys, checks them, aggregates them
by hour and publishes a JSON feed for the met offices.

```bash
python -m pytest
```

## Behaviour

- **Timestamps.** `ingest.parse_line` accepts ISO 8601 timestamps **with an explicit
  UTC offset** only (`2026-02-11T04:15:00+00:00`, `...+01:00`, `...Z`). A timestamp
  without an offset is ambiguous and raises `ParseError`. Parsed timestamps are
  converted to UTC.
- **Identifiers.** Observation ids are 64-bit integers and must survive every
  ingest path exactly, including ids above 2^53.
- **Duplicates.** Buoys re-send a batch when an upload is not acknowledged, so the
  same observation can arrive twice. `ingest.merge_batches` keeps the first copy of
  each `observation_id`.
- **Hourly windows.** `windows.bucket_by_hour` groups readings into UTC hours. A
  window covers `[start, start + 1 hour)`: a reading at exactly 13:00:00 belongs to
  the 13:00 window only.
- **Statistics.** `stats.summarise` reports the **mean** of each measurement over
  the readings that have it, rounded to 3 decimals once, at the end.
- **Units.** Wind speeds from older buoys arrive in knots; `units.knots_to_ms`
  converts with 1 kn = 0.514444 m/s.
- **Stations.** `stations.lookup` finds a station by name regardless of case or
  Unicode normalisation form.
- **Quality control.** `qc.evaluate` fails an observation if any value is out of
  range, the battery is below 11.5 V, or any sensor reports `offline`.
- **Uploads.** `uploader.Uploader.send` retries on timeout. A retried batch carries
  the same idempotency key, so the feed server applies it once.
- **Feed export.** `export.to_feed_json` writes strict JSON (RFC 8259): non-finite
  numbers become `null` and are listed under `faults`.
