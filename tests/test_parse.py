from datetime import time

import pytest

from time_tracker.parse import parse_time_flexible, parse_time_range, parse_time_ranges


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8", time(8, 0)),
        ("08", time(8, 0)),
        ("8:15", time(8, 15)),
        ("15,30", time(15, 30)),
        ("15.30", time(15, 30)),
    ],
)
def test_parse_time_flexible(raw: str, expected: time):
    assert parse_time_flexible(raw) == expected


@pytest.mark.parametrize(
    ("raw", "start", "end"),
    [
        ("8 - 12", time(8, 0), time(12, 0)),
        ("8:15 to 15,30", time(8, 15), time(15, 30)),
        ("08:15-17:00", time(8, 15), time(17, 0)),
    ],
)
def test_parse_time_range(raw: str, start: time, end: time):
    assert parse_time_range(raw) == (start, end)


def test_parse_time_range_rejects_garbage():
    with pytest.raises(ValueError):
        parse_time_range("tomorrow maybe")


def test_parse_multiple_ranges():
    assert parse_time_ranges("8-12, 13-17") == [
        (time(8, 0), time(12, 0)),
        (time(13, 0), time(17, 0)),
    ]
