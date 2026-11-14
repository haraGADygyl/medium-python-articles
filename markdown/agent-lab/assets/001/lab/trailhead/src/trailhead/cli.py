"""Command line: ``trailhead summary FILE`` and ``trailhead plan FILE``."""

import argparse
import sys
from collections.abc import Sequence

from trailhead.elevation import DEFAULT_THRESHOLD_M
from trailhead.plan import DEFAULT_MAX_HOURS, describe_plan, split_days
from trailhead.report import format_summary, summarise
from trailhead.track import TrackError, load_track


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trailhead")
    commands = parser.add_subparsers(dest="command", required=True)

    summary = commands.add_parser("summary", help="distance, ascent and time for a track")
    summary.add_argument("file")
    summary.add_argument("--fitness", type=float, default=1.0)
    summary.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_M)

    plan = commands.add_parser("plan", help="split a track into days of walking")
    plan.add_argument("file")
    plan.add_argument("--max-hours", type=float, default=DEFAULT_MAX_HOURS)
    plan.add_argument("--fitness", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        track = load_track(args.file)
    except (OSError, TrackError) as exc:
        print(f"trailhead: {exc}", file=sys.stderr)
        return 1
    if args.command == "summary":
        print(format_summary(summarise(track, args.fitness, args.threshold)))
    else:
        for line in describe_plan(split_days(track, args.max_hours, args.fitness)):
            print(line)
    return 0
