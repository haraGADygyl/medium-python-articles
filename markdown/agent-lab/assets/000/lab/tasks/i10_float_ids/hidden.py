from buoy_ingest.ingest import parse_csv

HEADER = "observation_id,buoy_id,recorded_at,lat,lon,wave_height_m\n"


def test_ids_up_to_int64_max():
    for big in (9007199254740995, 9223372036854775807, 12345678901234567):
        [observation] = parse_csv(HEADER + f"{big},NE-08,2026-02-11T04:15:00Z,57.2,-2.3,3.5\n")
        assert observation.observation_id == big
        assert isinstance(observation.observation_id, int)
