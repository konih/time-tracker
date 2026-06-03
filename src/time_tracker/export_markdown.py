from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from time_tracker.calc import Calculator, MonthlyReport
from time_tracker.config import AppConfig
from time_tracker.csv_store import CsvStore
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.model import Interval, IntervalKind, WorkLocation

_ONSITE_TARGET = 3
_ONSITE_BASE_WEEK = 5
_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _fmt_time(t) -> str:
    return t.strftime("%H:%M")


def _minutes_to_hours(mins: int) -> float:
    return round(mins / 60.0, 2)


def _hhmm(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _signed_hours(mins: int) -> str:
    h = _minutes_to_hours(mins)
    if h > 0:
        return f"+{h:.2f} h"
    if h < 0:
        return f"{h:.2f} h"
    return "±0.00 h"


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _iter_days(start: date, end_exclusive: date):
    d = start
    while d < end_exclusive:
        yield d
        d += timedelta(days=1)


def _iter_weeks_in_year(year: int):
    """Yield (monday, sunday) for each calendar week overlapping ``year``."""
    start = _week_start(date(year, 1, 1))
    end = date(year + 1, 1, 1)
    monday = start
    while monday < end:
        sunday = monday + timedelta(days=6)
        yield monday, sunday
        monday += timedelta(days=7)


def _required_onsite_days(workdays: int) -> int:
    if workdays <= 0:
        return 0
    return math.floor(_ONSITE_TARGET * workdays / _ONSITE_BASE_WEEK)


def _location_label(loc: WorkLocation) -> str:
    labels = {
        WorkLocation.HOMEOFFICE: "Home",
        WorkLocation.REMOTE: "Remote",
        WorkLocation.OFFICE: "Office",
        WorkLocation.PORZ: "Porz",
        WorkLocation.KARLSWERK: "Karlswerk",
        WorkLocation.KIEL: "Kiel",
        WorkLocation.BUSINESS_TRAVEL: "Travel",
    }
    return labels.get(loc, loc.value)


def _day_off_note(d: date, holiday_service: NRWHolidayService) -> str | None:
    if d.weekday() >= 5:
        return "Weekend"
    h = holiday_service.is_holiday(d)
    if h is None:
        return None
    suffix = " (½ day)" if h.is_half_day else ""
    return f"Holiday — {h.name}{suffix}"


@dataclass(frozen=True)
class DaySummary:
    day: date
    worked_mins: int
    primary_location: WorkLocation | None
    is_scheduled: bool
    off_note: str | None

    @property
    def is_onsite(self) -> bool:
        if not self.is_scheduled or self.worked_mins <= 0:
            return False
        return self.primary_location is not WorkLocation.HOMEOFFICE

    def onsite_marker(self) -> str:
        if not self.is_scheduled:
            if self.day.weekday() < 5:
                return "-"
            return " "
        if self.worked_mins <= 0:
            return "·"
        if self.is_onsite:
            return "✓"
        return "🏠"


@dataclass(frozen=True)
class WeekSummary:
    monday: date
    sunday: date
    days: tuple[DaySummary, ...]
    worked_mins: int
    expected_mins: int
    workdays: int
    required_onsite: int
    actual_onsite: int

    @property
    def onsite_ok(self) -> bool:
        if self.workdays <= 0:
            return True
        return self.actual_onsite >= self.required_onsite

    @property
    def iso_week(self) -> int:
        return self.monday.isocalendar()[1]

    def onsite_bar(self) -> str:
        markers = "".join(d.onsite_marker() for d in self.days[:5])
        status = "✅" if self.onsite_ok else "❌"
        return f"`[{markers}]` **{self.actual_onsite} / {self.required_onsite}** required {status}"


def _primary_location(intervals: list[Interval]) -> WorkLocation | None:
    work = [it for it in intervals if it.kind == IntervalKind.WORK]
    if not work:
        return None
    by_loc: dict[WorkLocation, int] = {}
    for it in work:
        by_loc[it.location] = by_loc.get(it.location, 0) + it.minutes()
    return max(by_loc, key=by_loc.get)


def _build_day_summary(
    d: date,
    by_day: dict[str, list[Interval]],
    calc: Calculator,
    holiday_service: NRWHolidayService,
) -> DaySummary:
    expected = calc.expected_minutes_for_day(d)
    intervals = sorted(by_day.get(d.isoformat(), []), key=lambda x: x.start)
    worked = sum(it.minutes() for it in intervals if it.kind == IntervalKind.WORK)
    return DaySummary(
        day=d,
        worked_mins=worked,
        primary_location=_primary_location(intervals),
        is_scheduled=expected > 0,
        off_note=_day_off_note(d, holiday_service),
    )


def _build_week_summary(
    monday: date,
    by_day: dict[str, list[Interval]],
    calc: Calculator,
    holiday_service: NRWHolidayService,
) -> WeekSummary:
    days = tuple(
        _build_day_summary(monday + timedelta(days=i), by_day, calc, holiday_service)
        for i in range(7)
    )
    worked_mins = sum(d.worked_mins for d in days)
    expected_mins = sum(calc.expected_minutes_for_day(d.day) for d in days)
    workdays = sum(1 for d in days if d.is_scheduled)
    actual_onsite = sum(1 for d in days if d.is_onsite)
    return WeekSummary(
        monday=monday,
        sunday=monday + timedelta(days=6),
        days=days,
        worked_mins=worked_mins,
        expected_mins=expected_mins,
        workdays=workdays,
        required_onsite=_required_onsite_days(workdays),
        actual_onsite=actual_onsite,
    )


def _carry_into_year(calc: Calculator, intervals: list[Interval], year: int) -> float:
    if year <= 1:
        return 0.0
    reps_prev = calc.monthly_reports(
        intervals,
        start=None,
        end_inclusive=(year - 1, 12),
        initial_carry_hours=0.0,
    )
    if not reps_prev:
        return 0.0
    return reps_prev[-1].carry_out_hours


def _week_heading(week: WeekSummary) -> str:
    mon, sun = week.monday, week.sunday
    if mon.month == sun.month:
        span = f"{mon.day}-{sun.day} {_MONTH_NAMES[mon.month]}"
    else:
        span = (
            f"{mon.day} {_MONTH_NAMES[mon.month][:3]} - "
            f"{sun.day} {_MONTH_NAMES[sun.month][:3]}"
        )
    return f"### Week {week.iso_week} · {span} {mon.year}"


def _day_row(day: DaySummary) -> str:
    label = f"{_WEEKDAY_NAMES[day.day.weekday()]} {day.day.day:02d}"
    if not day.is_scheduled:
        note = day.off_note or "—"
        return f"| {label} | — | — | {note} |"
    if day.worked_mins <= 0:
        note = day.off_note or "No work logged"
        return f"| {label} | — | — | {note} |"
    loc = _location_label(day.primary_location) if day.primary_location else "—"
    marker = "✓ on-site" if day.is_onsite else "🏠 home"
    return f"| {label} | {_hhmm(day.worked_mins)} | {loc} | {marker} |"


def _format_month_row(rep: MonthlyReport, weeks_ok: int, weeks_total: int) -> str:
    month = _MONTH_NAMES[rep.month]
    balance = _signed_hours(round((rep.worked_hours - rep.expected_hours) * 60))
    if weeks_ok == weeks_total:
        onsite = f"{weeks_ok}/{weeks_total} ✅"
    else:
        onsite = f"{weeks_ok}/{weeks_total}"
    return (
        f"| {month} | {rep.worked_hours:.2f} h | {rep.expected_hours:.2f} h | "
        f"{balance} | {onsite} | {rep.carry_out_hours:.2f} h |"
    )


def write_year_markdown(cfg: AppConfig, year: int, out: Path) -> None:
    """Write a Markdown report for calendar ``year`` to ``out``."""
    store = CsvStore(cfg.csv_path)
    intervals = store.load_all()

    holiday_service = NRWHolidayService(
        cache_dir=cfg.cache_dir, half_day_dates=cfg.half_day_holidays
    )
    calc = Calculator(cfg, holiday_service)

    by_day: dict[str, list[Interval]] = {}
    for it in intervals:
        if it.day.year == year and it.kind == IntervalKind.WORK:
            by_day.setdefault(it.day.isoformat(), []).append(it)

    weeks = [
        _build_week_summary(monday, by_day, calc, holiday_service)
        for monday, _ in _iter_weeks_in_year(year)
        if monday.year == year or (monday + timedelta(days=6)).year == year
    ]
    weeks_in_year = [w for w in weeks if w.monday.year == year]

    carry_in = _carry_into_year(calc, intervals, year)
    monthly_reps = calc.monthly_reports(
        intervals,
        start=(year, 1),
        end_inclusive=(year, 12),
        initial_carry_hours=carry_in,
    )
    rep_by_month = {(r.year, r.month): r for r in monthly_reps}

    weeks_by_month: dict[int, list[WeekSummary]] = {m: [] for m in range(1, 13)}
    weeks_ok_by_month: dict[int, tuple[int, int]] = {m: (0, 0) for m in range(1, 13)}
    for week in weeks_in_year:
        month = week.monday.month
        weeks_by_month[month].append(week)
        if week.worked_mins <= 0:
            continue
        ok, total = weeks_ok_by_month[month]
        if week.workdays > 0:
            total += 1
            if week.onsite_ok:
                ok += 1
        weeks_ok_by_month[month] = (ok, total)

    worked_mins_y = sum(w.worked_mins for w in weeks_in_year)
    expected_mins_y = calc.expected_minutes_in_year(year)
    tracked_weeks = [w for w in weeks_in_year if w.worked_mins > 0 and w.workdays > 0]
    year_weeks_ok = sum(1 for w in tracked_weeks if w.onsite_ok)
    year_weeks_total = len(tracked_weeks)
    rep_dec = monthly_reps[-1] if monthly_reps else None

    nominal_day_h = cfg.weekly_hours / 5.0
    lines: list[str] = []

    lines.append(f"# Time report — {year}")
    lines.append("")
    lines.append(
        f"Weekly target **{cfg.weekly_hours:.2f} h** · "
        f"Nominal day **{nominal_day_h:.2f} h** · "
        f"On-site rule **{_ONSITE_TARGET} of {_ONSITE_BASE_WEEK} workdays** "
        f"(scaled down for short weeks)"
    )
    lines.append("")

    lines.append("## Year at a glance")
    lines.append("")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| Worked | **{_minutes_to_hours(worked_mins_y):.2f} h** |")
    lines.append(f"| Expected | **{_minutes_to_hours(expected_mins_y):.2f} h** |")
    lines.append(f"| Balance | **{_signed_hours(worked_mins_y - expected_mins_y)}** |")
    if rep_dec is not None:
        lines.append(f"| Overtime (Dec, uncapped) | **{rep_dec.overtime_hours:.2f} h** |")
        lines.append(f"| Carry-out (Dec) | **{rep_dec.carry_out_hours:.2f} h** |")
        if rep_dec.dropped_hours:
            lines.append(f"| Dropped by cap (Dec) | **{rep_dec.dropped_hours:.2f} h** |")
    onsite_year = (
        f"**{year_weeks_ok} / {year_weeks_total}** weeks ✅"
        if year_weeks_ok == year_weeks_total
        else f"**{year_weeks_ok} / {year_weeks_total}** weeks"
    )
    lines.append(f"| On-site weeks | {onsite_year} |")
    lines.append("")
    lines.append(
        "On-site bar per week: `✓` = worked off-site, `🏠` = home office, "
        "`·` = scheduled but not logged, `-` = holiday, spaces = weekend."
    )
    lines.append("")

    lines.append("## Months")
    lines.append("")
    lines.append(
        "| Month | Worked | Expected | Balance | On-site weeks | Carry-out |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for month in range(1, 13):
        rep = rep_by_month.get(
            (year, month),
            MonthlyReport(
                year=year,
                month=month,
                worked_hours=0.0,
                expected_hours=_minutes_to_hours(calc.expected_minutes_in_month(year, month)),
                delta_hours=0.0,
                carry_in_hours=0.0,
                overtime_hours=0.0,
                carry_out_hours=0.0,
                dropped_hours=0.0,
            ),
        )
        ok, total = weeks_ok_by_month[month]
        lines.append(_format_month_row(rep, ok, total))
    lines.append("")

    for month in range(1, 13):
        month_weeks = [w for w in weeks_by_month[month] if w.worked_mins > 0]
        if not month_weeks:
            continue
        lines.append(f"## {_MONTH_NAMES[month]} {year}")
        lines.append("")
        for week in month_weeks:
            lines.append(_week_heading(week))
            lines.append("")
            lines.append(
                f"**Hours** {_minutes_to_hours(week.worked_mins):.2f} h worked · "
                f"{_minutes_to_hours(week.expected_mins):.2f} h expected · "
                f"**{_signed_hours(week.worked_mins - week.expected_mins)}**"
            )
            lines.append(f"**On-site** {week.onsite_bar()}")
            lines.append("")
            lines.append("| Day | Worked | Location | On-site |")
            lines.append("|---|---:|---|---|")
            for day in week.days:
                if day.day.year != year:
                    continue
                lines.append(_day_row(day))
            lines.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
