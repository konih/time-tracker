from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from time_tracker.calc import Calculator
from time_tracker.config import AppConfig
from time_tracker.csv_store import CsvStore
from time_tracker.export_markdown import (
    _build_week_summary,
    _required_onsite_days,
    write_year_markdown,
)
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.model import Interval, IntervalKind, WorkLocation


@pytest.mark.parametrize(
    ("workdays", "required"),
    [
        (5, 3),
        (4, 2),
        (3, 1),
        (2, 1),
        (1, 0),
        (0, 0),
    ],
)
def test_required_onsite_days_scales_with_floor(workdays: int, required: int):
    assert _required_onsite_days(workdays) == required


def test_week_summary_onsite_bar(tmp_path: Path):
    cfg = AppConfig(cache_dir=tmp_path / ".cache")
    holidays = NRWHolidayService(cache_dir=cfg.cache_dir)
    calc = Calculator(cfg, holidays)

    # Week of 2026-05-04 (Mon) — Labor Day Fri 2026-05-01 is previous week
    by_day = {
        "2026-05-04": [
            Interval(
                day=date(2026, 5, 4),
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            )
        ],
        "2026-05-05": [
            Interval(
                day=date(2026, 5, 5),
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.HOMEOFFICE,
            )
        ],
        "2026-05-06": [
            Interval(
                day=date(2026, 5, 6),
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.OFFICE,
            )
        ],
        "2026-05-07": [
            Interval(
                day=date(2026, 5, 7),
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            )
        ],
        "2026-05-08": [
            Interval(
                day=date(2026, 5, 8),
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.HOMEOFFICE,
            )
        ],
    }
    week = _build_week_summary(date(2026, 5, 4), by_day, calc, holidays)
    assert week.workdays == 5
    assert week.required_onsite == 3
    assert week.actual_onsite == 3
    assert week.onsite_ok
    assert "✓" in week.onsite_bar()
    assert "3 / 3" in week.onsite_bar()


def test_write_year_markdown_creates_file(tmp_path: Path):
    csv_path = tmp_path / "time_log.csv"
    store = CsvStore(csv_path)
    store.save_all(
        [
            Interval(
                day=date(2026, 5, 8),
                start=time(9, 0),
                end=time(12, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            ),
            Interval(
                day=date(2026, 5, 8),
                start=time(13, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            ),
        ]
    )

    out = tmp_path / "nested" / "rep.md"
    cfg = AppConfig(csv_path=csv_path, cache_dir=tmp_path / ".cache")
    write_year_markdown(cfg, 2026, out)

    text = out.read_text(encoding="utf-8")
    assert "Time report — 2026" in text
    assert "Year at a glance" in text
    assert "## Months" in text
    assert "## May 2026" in text
    assert "Week" in text
    assert "**On-site**" in text
    assert "Porz" in text
    assert "Fri 08" in text
