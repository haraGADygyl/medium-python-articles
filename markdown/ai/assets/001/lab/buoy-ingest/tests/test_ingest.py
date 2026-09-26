import json
from datetime import datetime, timezone

import pytest

from buoy_ingest.ingest import merge_batches, parse_csv, parse_line, read_jsonl
from buoy_ingest.models import ParseError

LINE = json.dumps({
    "observation_id": 9007199254740993, "buoy_id": "NE-08",
    "recorded_at": "2026-02-11T05:15:00+01:00",
    "position": {"lat": 57.21621, "lon": -2.37579},
    "wave_height_m": 3.5, "battery_v": 13.12, "notes": None,
    "sensors": [{"tag": "gps", "status": "ok", "samples": 318}],
})


def test_parse_line_reads_every_field():
    observation = parse_line(LINE)
    assert observation.observation_id == 9007199254740993
    assert observation.buoy_id == "NE-08"
    assert observation.wave_height_m == 3.5
    assert observation.water_temp_c is None
    assert observation.sensors[0].tag == "gps"


def test_parse_line_converts_offsets_to_utc():
    observation = parse_line(LINE)
    assert observation.recorded_at == datetime(2026, 2, 11, 4, 15, tzinfo=timezone.utc)


def test_parse_line_accepts_z_suffix():
    record = json.loads(LINE) | {"recorded_at": "2026-02-11T04:15:00Z"}
    assert parse_line(json.dumps(record)).recorded_at.hour == 4


def test_parse_line_rejects_missing_fields():
    with pytest.raises(ParseError, match="position"):
        parse_line(json.dumps({"observation_id": 1, "buoy_id": "NE-08",
                               "recorded_at": "2026-02-11T04:15:00Z"}))


def test_parse_line_rejects_non_objects():
    with pytest.raises(ParseError):
        parse_line("[1, 2, 3]")


def test_read_jsonl_skips_blank_lines():
    assert len(read_jsonl([LINE, "", "  ", LINE])) == 2


def test_parse_csv_reads_small_ids():
    text = ("observation_id,buoy_id,recorded_at,lat,lon,wave_height_m\n"
            "1042,SW-42,2026-02-11T04:15:00+00:00,56.96,-2.2,1.25\n")
    [observation] = parse_csv(text)
    assert observation.observation_id == 1042
    assert observation.wave_height_m == 1.25


def test_merge_batches_keeps_distinct_observations(make_observation):
    first = [make_observation(1), make_observation(2)]
    second = [make_observation(3)]
    assert [o.observation_id for o in merge_batches([first, second])] == [1, 2, 3]
