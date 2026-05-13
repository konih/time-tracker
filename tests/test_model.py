from datetime import date, time

import pytest

from time_tracker.model import Interval, IntervalKind, WorkLocation


def test_interval_minutes_positive():
    i = Interval(
        day=date(2026, 5, 8),
        start=time(9, 0),
        end=time(10, 30),
        kind=IntervalKind.WORK,
        location=WorkLocation.HOMEOFFICE,
    )
    assert i.minutes() == 90


def test_interval_rejects_end_before_start():
    i = Interval(
        day=date(2026, 5, 8),
        start=time(10, 0),
        end=time(9, 0),
        kind=IntervalKind.WORK,
        location=WorkLocation.HOMEOFFICE,
    )
    with pytest.raises(ValueError, match="end must be after start"):
        i.minutes()
