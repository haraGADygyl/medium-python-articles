def test_parse_csv_keeps_ids_above_2_53():
    text = ("observation_id,buoy_id,recorded_at,lat,lon,wave_height_m\n"
            "9007199254740993,NE-08,2026-02-11T04:15:00+00:00,57.2,-2.3,3.5\n")
    [observation] = parse_csv(text)
    assert observation.observation_id == 9007199254740993
