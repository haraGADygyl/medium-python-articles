from buoy_ingest.models import Sensor
from buoy_ingest.qc import evaluate


def test_healthy_observation_passes(make_observation):
    assert evaluate(make_observation()).passed


def test_out_of_range_wave_fails(make_observation):
    result = evaluate(make_observation(wave_height_m=31.0))
    assert not result.passed
    assert "wave_height_m" in result.reasons[0]


def test_low_battery_fails(make_observation):
    assert not evaluate(make_observation(battery_v=11.2)).passed


def test_degraded_sensor_is_not_a_failure(make_observation):
    sensors = [Sensor("thermistor", "degraded", 1866)]
    assert evaluate(make_observation(sensors=sensors)).passed
