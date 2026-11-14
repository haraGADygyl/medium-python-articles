"""A one-screen summary of a track."""

from dataclasses import dataclass

from trailhead.elevation import (
    DEFAULT_THRESHOLD_M,
    gain_and_loss,
    highest_and_lowest,
    steepest_grade,
)
from trailhead.geo import compass_point, haversine_km, initial_bearing
from trailhead.pace import naismith_hours
from trailhead.track import Track

LOOP_RADIUS_KM = 0.1


@dataclass(frozen=True, slots=True)
class Summary:
    name: str
    length_km: float
    gain_m: float
    loss_m: float
    highest_m: float
    lowest_m: float
    steepest_pct: float
    hours: float
    heading: str


def _heading(track: Track) -> str:
    start, finish = track.points[0], track.points[-1]
    if haversine_km(start.lat, start.lon, finish.lat, finish.lon) <= LOOP_RADIUS_KM:
        return "loop"
    return compass_point(initial_bearing(start.lat, start.lon, finish.lat, finish.lon))


def summarise(
    track: Track, fitness: float = 1.0, threshold: float = DEFAULT_THRESHOLD_M
) -> Summary:
    gain, loss = gain_and_loss([point.ele for point in track.points], threshold)
    highest, lowest = highest_and_lowest(track)
    length = track.length_km()
    return Summary(
        name=track.name,
        length_km=round(length, 1),
        gain_m=gain,
        loss_m=loss,
        highest_m=highest,
        lowest_m=lowest,
        steepest_pct=steepest_grade(track),
        hours=naismith_hours(length, gain, fitness),
        heading=_heading(track),
    )


def format_summary(summary: Summary) -> str:
    whole, minutes = divmod(round(summary.hours * 60), 60)
    return "\n".join(
        [
            summary.name,
            f"  distance  {summary.length_km:.1f} km",
            f"  ascent    +{summary.gain_m:.0f} m / -{summary.loss_m:.0f} m",
            f"  altitude  {summary.lowest_m:.0f}-{summary.highest_m:.0f} m",
            f"  steepest  {summary.steepest_pct:.1f}%",
            f"  time      {whole}h {minutes:02d}m",
            f"  heading   {summary.heading}",
        ]
    )
