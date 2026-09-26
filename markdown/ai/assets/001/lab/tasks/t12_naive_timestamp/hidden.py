import json

import pytest

from buoy_ingest.ingest import parse_line, parse_timestamp
from buoy_ingest.models import ParseError


def test_naive_timestamps_are_rejected():
    for naive in ("2026-02-11T04:15:00", "2026-02-11 04:15", "2026-02-11"):
        with pytest.raises(ParseError):
            parse_timestamp(naive)


def test_offset_timestamps_still_parse():
    assert parse_timestamp("2026-02-11T05:15:00+01:00").hour == 4
