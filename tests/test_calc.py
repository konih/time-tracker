from datetime import date, time
from pathlib import Path

from time_tracker.calc import Calculator
from time_tracker.config import AppConfig
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.model import Interval, IntervalKind, WorkLocation


def test_worked_minutes_ignores_break_rows(tmp_path: Path):
    cfg = AppConfig(cache_dir=tmp_path / ".cache")
    holidays = NRWHolidayService(cache_dir=cfg.cache_dir)
    calc = Calculator(cfg, holidays)

    intervals = [
        Interval(
            day=date(2026, 5, 8),
            start=time(9, 0),
            end=time(12, 0),
            kind=IntervalKind.WORK,
            location=WorkLocation.HOMEOFFICE,
        ),
        Interval(
            day=date(2026, 5, 8),
            start=time(12, 0),
            end=time(12, 30),
            kind=IntervalKind.BREAK,
            location=WorkLocation.HOMEOFFICE,
        ),
        Interval(
            day=date(2026, 5, 8),
            start=time(12, 30),
            end=time(17, 0),
            kind=IntervalKind.WORK,
            location=WorkLocation.HOMEOFFICE,
        ),
    ]

    assert calc.worked_minutes_in_month(intervals, 2026, 5) == (7 * 60 + 30)  # 7h30m


def test_expected_minutes_for_day_weekend_and_weekday(tmp_path: Path):
    cfg = AppConfig(cache_dir=tmp_path / ".cache", weekly_hours=37.7)
    holidays = NRWHolidayService(cache_dir=cfg.cache_dir)
    calc = Calculator(cfg, holidays)
    sat = date(2026, 5, 9)
    assert sat.weekday() == 5
    assert calc.expected_minutes_for_day(sat) == 0
    fri = date(2026, 5, 8)
    assert calc.expected_minutes_for_day(fri) == round((37.7 / 5.0) * 60)


def test_monthly_carry_cap(tmp_path: Path, monkeypatch):
    """
    We don't want this test to depend on the external holiday list.
    Patch expected_minutes_in_month to a small constant and verify capping.
    """
    cfg = AppConfig(cache_dir=tmp_path / ".cache", month_carry_cap_hours=60.0)
    holidays = NRWHolidayService(cache_dir=cfg.cache_dir)
    calc = Calculator(cfg, holidays)

    monkeypatch.setattr(calc, "expected_minutes_in_month", lambda y, m: 0)

    intervals = [
        Interval(
            day=date(2026, 5, 1),
            start=time(0, 0),
            end=time(23, 59),
            kind=IntervalKind.WORK,
            location=WorkLocation.HOMEOFFICE,
        )
        for _ in range(4)
    ]

    rep = calc.monthly_report(intervals, 2026, 5, carry_in_hours=0.0)
    assert rep.overtime_hours > 60.0
    assert rep.carry_out_hours == 60.0
    assert rep.dropped_hours >= 0.0
