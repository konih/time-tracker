from __future__ import annotations

from datetime import date, time

from time_tracker.model import Interval, IntervalKind, WorkLocation
from time_tracker.tui.day_stats import (
    break_minutes,
    day_warnings,
    format_week_target_banner,
    week_expected_minutes,
    week_overview_lines,
    work_minutes,
)


def _work(start: str, end: str) -> Interval:
    return Interval(
        day=date(2026, 6, 24),
        start=time.fromisoformat(start),
        end=time.fromisoformat(end),
        kind=IntervalKind.WORK,
        location=WorkLocation.HOMEOFFICE,
    )


def _break(start: str, end: str) -> Interval:
    return Interval(
        day=date(2026, 6, 24),
        start=time.fromisoformat(start),
        end=time.fromisoformat(end),
        kind=IntervalKind.BREAK,
        location=WorkLocation.HOMEOFFICE,
    )


def test_work_minutes_sums_work_only():
    intervals = [_work("09:00", "12:00"), _break("12:00", "12:30"), _work("12:30", "17:00")]
    assert work_minutes(intervals) == 450


def test_break_minutes_counts_gaps_and_explicit_breaks():
    intervals = [_work("08:00", "14:00"), _work("14:30", "17:00")]
    assert break_minutes(intervals) == 30

    with_explicit = [*intervals, _break("17:00", "17:15")]
    assert break_minutes(with_explicit) == 45


def test_day_warnings_over_ten_hours():
    intervals = [_work("07:00", "18:00")]
    warnings = day_warnings(intervals)
    assert any("10 h" in w for w in warnings)


def test_day_warnings_missing_break_after_six_hours():
    intervals = [_work("08:00", "15:00")]
    warnings = day_warnings(intervals)
    assert any("30 min break" in w for w in warnings)

    with_lunch = [_work("08:00", "12:00"), _work("12:30", "15:00")]
    assert day_warnings(with_lunch) == []


def test_week_target_banner_met():
    banner = format_week_target_banner(38 * 60, 37 * 60 + 30)
    assert "✅" in banner
    assert "week target reached" in banner


def test_week_target_banner_not_met():
    banner = format_week_target_banner(30 * 60, 37 * 60 + 30)
    assert "⏳" in banner
    assert "left" in banner


def test_week_target_banner_uses_holiday_adjusted_target(tmp_path):
    """Week of 2026-05-25 has Whit Monday — only 30 h expected, not 37.5 h."""
    from time_tracker.calc import Calculator
    from time_tracker.config import AppConfig
    from time_tracker.holidays_nrw import NRWHolidayService

    cfg = AppConfig(cache_dir=tmp_path / ".cache", weekly_hours=37.5)
    calc = Calculator(cfg, NRWHolidayService(cfg.cache_dir))
    anchor = date(2026, 5, 25)
    target = week_expected_minutes(anchor, calc.expected_minutes_for_day)
    assert target == 30 * 60
    banner = format_week_target_banner(30 * 60, target)
    assert "✅" in banner


def test_week_overview_shows_holiday(tmp_path):
    from time_tracker.calc import Calculator
    from time_tracker.config import AppConfig
    from time_tracker.holidays_nrw import NRWHolidayService

    cfg = AppConfig(cache_dir=tmp_path / ".cache", weekly_hours=37.5)
    svc = NRWHolidayService(cfg.cache_dir)
    calc = Calculator(cfg, svc)
    anchor = date(2026, 5, 25)

    text = week_overview_lines(
        anchor,
        anchor,
        lambda _d: [],
        calc.expected_minutes_for_day,
        svc.is_holiday,
        cfg.weekly_hours,
    )
    assert "Public holidays" in text
    assert "Whit Monday" in text
    assert "Expected: 30:00 h" in text
    assert "Full week would be 37:30 h" in text
    assert "7:30 h off" in text
