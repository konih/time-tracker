from datetime import date, time
from pathlib import Path

from time_tracker.csv_store import CsvStore
from time_tracker.model import Interval, IntervalKind, WorkLocation


def test_csv_roundtrip(tmp_path: Path):
    path = tmp_path / "time_log.csv"
    store = CsvStore(path)

    intervals = [
        Interval(
            day=date(2026, 5, 8),
            start=time(9, 10),
            end=time(12, 10),
            kind=IntervalKind.WORK,
            location=WorkLocation.HOMEOFFICE,
            note="Onboarding",
        ),
        Interval(
            day=date(2026, 5, 8),
            start=time(12, 10),
            end=time(12, 40),
            kind=IntervalKind.BREAK,
            location=WorkLocation.HOMEOFFICE,
            note="lunch",
        ),
    ]

    store.save_all(intervals)
    loaded = store.load_all()

    assert loaded == intervals


def test_upsert_day_replaces_only_that_day(tmp_path: Path):
    path = tmp_path / "time_log.csv"
    store = CsvStore(path)

    day1 = date(2026, 5, 8)
    day2 = date(2026, 5, 9)

    store.save_all(
        [
            Interval(
                day=day1,
                start=time(9, 0),
                end=time(10, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.HOMEOFFICE,
                note="d1",
            ),
            Interval(
                day=day2,
                start=time(9, 0),
                end=time(10, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.HOMEOFFICE,
                note="d2",
            ),
        ]
    )

    store.upsert_day(
        day1,
        [
            Interval(
                day=day1,
                start=time(13, 0),
                end=time(14, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.HOMEOFFICE,
                note="d1-new",
            )
        ],
    )

    loaded = store.load_all()
    assert next(i for i in loaded if i.day == day1).note == "d1-new"
    assert next(i for i in loaded if i.day == day2).note == "d2"
