# trailhead

Plan hikes from recorded tracks: distance, ascent, walking time and how to split the
walk into days. Pure Python 3.12, no dependencies.

```bash
python -m trailhead summary rila.csv
python -m trailhead plan rila.csv --max-hours 6 --fitness 1.2
```

## Track format

A track is a UTF-8 text file:

```
# name: Seven Rila Lakes
# units: m
lat,lon,ele
42.2031,23.3205,2140
42.2049,23.3188,2196
```

- Blank lines are ignored. Lines starting with `#` are comments; two of them are
  settings: `# name: <text>` and `# units: m` or `# units: ft`.
- Without a `# name:` line, `load_track` names the track after the file (`rila.csv` →
  `rila`) and `parse_track` uses its `default_name` argument, or `unnamed` if none is given.
- With `# units: ft`, elevations are converted to metres (1 ft = 0.3048 m). Any other
  units value is an error. Everything after parsing is in metres.
- The first non-comment line must be exactly the header `lat,lon,ele`.
- Each point has three numbers. Latitude must be within -90 to 90 and longitude within
  -180 to 180, both inclusive.
- A track needs at least two points.
- Problems raise `TrackError` (a `ValueError`). When the problem is on a line, the
  message starts with `line N:`, where N counts every line in the file from 1,
  comments and blank lines included.

## Behaviour

- **Distance** is great-circle distance on a sphere of radius 6371.0088 km.
- **Ascent and descent** (`elevation.gain_and_loss`) ignore changes smaller than a
  threshold, 3 m by default. A change counts once the elevation has moved at least the
  threshold away from the last counted elevation, so jitter of a metre either way
  adds nothing, but a 300 m climb recorded in 1 m steps still counts as 300 m. Totals
  are rounded to 0.1 m. A negative threshold is a `ValueError`.
- **Steepest grade** (`elevation.steepest_grade`) is the gradient of the steepest leg
  (the stretch between two consecutive points) in **percent**, uphill or downhill,
  rounded to 0.1: a leg climbing 18 m over 100 m is `18.0`. Repeated points
  (zero-length legs) are skipped.
- **Walking time** uses Naismith's rule: 5 km/h on the flat plus one hour for every
  600 m of ascent; descent adds nothing. `fitness` divides the time: 1.25 is 25%
  faster than average. Zero or negative fitness, and negative distance or ascent, are
  a `ValueError`. Times are not rounded until they are displayed.
- **Tobler's hiking function** (`pace.tobler_kmh`) gives speed on a slope as
  `6 * exp(-3.5 * |grade + 0.05|)` km/h, with grade as rise over run.
- **Day plans** (`plan.split_days`) group consecutive legs into days, timing each leg
  by Naismith's rule with only that leg's own climb. The default limit is 7 hours a
  day. A day never goes over the limit unless a single leg on its own does, in which
  case that leg is a day by itself. `fitness` applies to the plan exactly as it does
  to the summary.
- **Heading** in the summary is the compass point (N, NE, E, SE, S, SW, W, NW) from the
  start to the finish, or `loop` when the finish is within 0.1 km of the start.
- **Durations** are displayed as `<hours>h <minutes>m` with two-digit minutes, rounded
  to the nearest minute: `5h 07m`, `0h 45m`, `12h 00m`.

## Development

```bash
python -m pytest
ruff check
mypy
```
