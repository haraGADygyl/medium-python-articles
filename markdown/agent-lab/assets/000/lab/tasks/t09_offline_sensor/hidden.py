from buoy_ingest.models import Sensor
from buoy_ingest.qc import evaluate


def test_any_offline_sensor_fails(make_observation):
    for tag in ("gps", "thermistor", "anemometer"):
        result = evaluate(make_observation(sensors=[Sensor(tag, "offline", 0)]))
        assert not result.passed
        assert tag in " ".join(result.reasons)


def test_all_offline_sensors_are_named(make_observation):
    sensors = [Sensor("gps", "offline", 0), Sensor("thermistor", "offline", 0)]
    result = evaluate(make_observation(sensors=sensors))
    assert "gps" in " ".join(result.reasons) and "thermistor" in " ".join(result.reasons)
