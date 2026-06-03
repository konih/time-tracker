from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from time_tracker.config import AppConfig
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.model import Interval, IntervalKind


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _iter_days(start: date, end_exclusive: date):
    d = start
    while d < end_exclusive:
        yield d
        d += timedelta(days=1)


def _minutes_to_hours(mins: int) -> float:
    return round(mins / 60.0, 2)


@dataclass(frozen=True)
class MonthlyReport:
    year: int
    month: int
    worked_hours: float
    expected_hours: float
    delta_hours: float
    carry_in_hours: float
    overtime_hours: float  # carry_in + delta (uncapped)
    carry_out_hours: float
    dropped_hours: float


class Calculator:
    def __init__(self, config: AppConfig, holiday_service: NRWHolidayService):
        self.config = config
        self.holidays = holiday_service

    def worked_minutes_in_month(self, intervals: list[Interval], year: int, month: int) -> int:
        start, end = _month_range(year, month)
        mins = 0
        for it in intervals:
            if start <= it.day < end:
                m = it.minutes()
                if it.kind == IntervalKind.WORK:
                    mins += m
        return mins

    def worked_minutes_in_year(self, intervals: list[Interval], year: int) -> int:
        return sum(self.worked_minutes_in_month(intervals, year, m) for m in range(1, 13))

    def expected_minutes_in_year(self, year: int) -> int:
        return sum(self.expected_minutes_in_month(year, m) for m in range(1, 13))

    def expected_minutes_for_day(self, d: date) -> int:
        """Expected working minutes on ``d`` (0 on weekends; holidays per NRW cache)."""
        if d.weekday() >= 5:
            return 0
        daily_minutes = round((self.config.weekly_hours / 5.0) * 60)
        holiday = self.holidays.is_holiday(d)
        if holiday is None:
            return daily_minutes
        if holiday.is_half_day:
            return daily_minutes // 2
        return 0

    def expected_minutes_in_month(self, year: int, month: int) -> int:
        start, end = _month_range(year, month)
        return sum(self.expected_minutes_for_day(d) for d in _iter_days(start, end))

    @staticmethod
    def _month_key(d: date) -> tuple[int, int]:
        return d.year, d.month

    @staticmethod
    def _next_month(year: int, month: int) -> tuple[int, int]:
        return (year + 1, 1) if month == 12 else (year, month + 1)

    @staticmethod
    def _iter_months(start: tuple[int, int], end_inclusive: tuple[int, int]):
        y, m = start
        while (y, m) <= end_inclusive:
            yield y, m
            y, m = Calculator._next_month(y, m)

    @staticmethod
    def _first_month(intervals: list[Interval]) -> tuple[int, int] | None:
        days = [it.day for it in intervals if it.kind == IntervalKind.WORK]
        if not days:
            return None
        d = min(days)
        return d.year, d.month

    def monthly_reports(
        self,
        intervals: list[Interval],
        start: tuple[int, int] | None,
        end_inclusive: tuple[int, int],
        initial_carry_hours: float = 0.0,
    ) -> list[MonthlyReport]:
        """
        Compute month-by-month overtime ledger with carry caps.

        - month cap: anything above `month_carry_cap_hours` is dropped (not carried to next month)
        - year cap: on Jan carry-in, anything above `year_carry_cap_hours` is dropped
        """
        if start is None:
            start = self._first_month(intervals)
        if start is None:
            return []

        carry = float(initial_carry_hours)
        out: list[MonthlyReport] = []

        for y, m in self._iter_months(start, end_inclusive):
            worked_mins = self.worked_minutes_in_month(intervals, y, m)
            expected_mins = self.expected_minutes_in_month(y, m)
            delta_hours = _minutes_to_hours(worked_mins - expected_mins)

            carry_in = carry
            overtime_uncapped = round(carry_in + delta_hours, 2)

            carry_out = overtime_uncapped
            dropped = 0.0
            if carry_out > self.config.month_carry_cap_hours:
                dropped = round(carry_out - self.config.month_carry_cap_hours, 2)
                carry_out = self.config.month_carry_cap_hours

            # Apply year cap when rolling into January (for the next month carry-in).
            _, next_m = self._next_month(y, m)
            carry_next = carry_out
            if next_m == 1 and carry_next > self.config.year_carry_cap_hours:
                dropped = round(
                    dropped + (carry_next - self.config.year_carry_cap_hours),
                    2,
                )
                carry_next = self.config.year_carry_cap_hours

            out.append(
                MonthlyReport(
                    year=y,
                    month=m,
                    worked_hours=_minutes_to_hours(worked_mins),
                    expected_hours=_minutes_to_hours(expected_mins),
                    delta_hours=delta_hours,
                    carry_in_hours=round(carry_in, 2),
                    overtime_hours=round(overtime_uncapped, 2),
                    carry_out_hours=round(carry_out, 2),
                    dropped_hours=round(dropped, 2),
                )
            )
            carry = carry_next

        return out

    def monthly_report(
        self,
        intervals: list[Interval],
        year: int,
        month: int,
        carry_in_hours: float = 0.0,
    ) -> MonthlyReport:
        rep = self.monthly_reports(
            intervals,
            start=(year, month),
            end_inclusive=(year, month),
            initial_carry_hours=carry_in_hours,
        )
        if not rep:
            return MonthlyReport(
                year=year,
                month=month,
                worked_hours=0.0,
                expected_hours=_minutes_to_hours(self.expected_minutes_in_month(year, month)),
                delta_hours=0.0,
                carry_in_hours=round(carry_in_hours, 2),
                overtime_hours=round(carry_in_hours, 2),
                carry_out_hours=round(min(carry_in_hours, self.config.month_carry_cap_hours), 2),
                dropped_hours=0.0,
            )
        return rep[0]
