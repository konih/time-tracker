from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from itertools import pairwise

from time_tracker.holidays_nrw import HolidayInfo
from time_tracker.model import Interval, IntervalKind

MAX_DAILY_WORK_MINUTES = 10 * 60
_BREAK_THRESHOLD_MINUTES = 6 * 60
REQUIRED_BREAK_MINUTES = 30

_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTH_ABBR = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _minutes_between(end: time, start: time) -> int:
    end_dt = datetime.combine(date.min, end)
    start_dt = datetime.combine(date.min, start)
    if start_dt <= end_dt:
        return 0
    return int((start_dt - end_dt).total_seconds() // 60)


def work_minutes(intervals: list[Interval]) -> int:
    return sum(i.minutes() for i in intervals if i.kind == IntervalKind.WORK)


def break_minutes(intervals: list[Interval]) -> int:
    explicit = sum(i.minutes() for i in intervals if i.kind == IntervalKind.BREAK)
    work = sorted(
        (i for i in intervals if i.kind == IntervalKind.WORK),
        key=lambda i: i.start,
    )
    gaps = 0
    for prev, nxt in pairwise(work):
        gap = _minutes_between(prev.end, nxt.start)
        if gap > 0:
            gaps += gap
    return explicit + gaps


def format_hours_minutes(minutes: int) -> str:
    sign = "-" if minutes < 0 else ""
    minutes = abs(minutes)
    return f"{sign}{minutes // 60}:{minutes % 60:02d} h"


def day_warnings(intervals: list[Interval]) -> list[str]:
    warnings: list[str] = []
    worked = work_minutes(intervals)
    if worked > MAX_DAILY_WORK_MINUTES:
        limit_h = MAX_DAILY_WORK_MINUTES // 60
        warnings.append(
            f"Over {limit_h} h daily limit ({format_hours_minutes(worked)} worked)"
        )
    breaks = break_minutes(intervals)
    if worked >= _BREAK_THRESHOLD_MINUTES and breaks < REQUIRED_BREAK_MINUTES:
        warnings.append(
            f"Need {REQUIRED_BREAK_MINUTES} min break after 6 h "
            f"(only {breaks} min recorded)"
        )
    return warnings


def format_week_target_banner(total_worked: int, target_minutes: int) -> str:
    if target_minutes <= 0:
        return "[dim]No workdays scheduled this week[/dim]"
    worked_label = format_hours_minutes(total_worked)
    target_label = format_hours_minutes(target_minutes)
    if total_worked >= target_minutes:
        return (
            f"[bold white on green]  ✅  {worked_label} / {target_label}  "
            f"week target reached  [/]"
        )
    remaining = target_minutes - total_worked
    return (
        f"[bold black on yellow]  ⏳  {worked_label} / {target_label}  "
        f"({format_hours_minutes(remaining)} left)  [/]"
    )


def week_expected_minutes(
    anchor: date,
    expected_minutes_for_day: Callable[[date], int],
) -> int:
    monday = week_start(anchor)
    return sum(
        expected_minutes_for_day(monday + timedelta(days=offset)) for offset in range(7)
    )


def week_total_worked(
    anchor: date,
    intervals_for_day: Callable[[date], list[Interval]],
) -> int:
    monday = week_start(anchor)
    total = 0
    for offset in range(7):
        day = monday + timedelta(days=offset)
        total += work_minutes(intervals_for_day(day))
    return total


def _week_heading(anchor: date) -> str:
    monday = week_start(anchor)
    sunday = monday + timedelta(days=6)
    week_no = monday.isocalendar()[1]
    if monday.month == sunday.month:
        span = f"{monday.day}-{sunday.day} {_MONTH_ABBR[monday.month]}"
    else:
        span = (
            f"{monday.day} {_MONTH_ABBR[monday.month]}"
            f" - {sunday.day} {_MONTH_ABBR[sunday.month]}"
        )
    return f"[bold]Week {week_no}[/bold] · {span} {monday.year}"


def _format_day_line(
    day: date,
    offset: int,
    selected: date,
    worked: int,
    expected: int,
    holiday: HolidayInfo | None,
) -> str:
    name = _WEEKDAY_NAMES[offset]
    if day == date.today():
        name = f"[bold]{name}[/bold]"
    marker = " ▸" if day == selected else ""

    if day.weekday() >= 5:
        body = format_hours_minutes(worked) if worked else "[dim]weekend[/dim]"
    elif holiday and holiday.is_half_day:
        if worked:
            body = (
                f"{format_hours_minutes(worked)} "
                f"[cyan](½ {holiday.name})[/cyan]"
            )
        else:
            body = (
                f"[bold cyan]½ {holiday.name}[/bold cyan] · "
                f"{format_hours_minutes(expected)} exp"
            )
    elif holiday and not worked:
        body = f"[bold cyan]🎉 {holiday.name}[/bold cyan]"
    elif worked:
        if holiday:
            body = (
                f"{format_hours_minutes(worked)} "
                f"[yellow]({holiday.name})[/yellow]"
            )
        else:
            body = format_hours_minutes(worked)
    elif expected:
        body = f"— · [dim]{format_hours_minutes(expected)} exp[/dim]"
    else:
        body = "—"

    return f"{name} {day.day:02d}: {body}{marker}"


def week_overview_lines(
    anchor: date,
    selected: date,
    intervals_for_day: Callable[[date], list[Interval]],
    expected_minutes_for_day: Callable[[date], int] | None = None,
    holiday_for_day: Callable[[date], HolidayInfo | None] | None = None,
    weekly_hours: float | None = None,
) -> str:
    monday = week_start(anchor)
    lines: list[str] = [_week_heading(anchor), ""]

    week_holidays: list[str] = []
    day_lines: list[str] = []
    total_worked = 0
    total_expected = 0

    for offset in range(7):
        day = monday + timedelta(days=offset)
        intervals = intervals_for_day(day)
        worked = work_minutes(intervals)
        total_worked += worked
        expected = expected_minutes_for_day(day) if expected_minutes_for_day else 0
        total_expected += expected
        holiday = holiday_for_day(day) if holiday_for_day else None
        if holiday and day.weekday() < 5:
            label = f"½ {holiday.name}" if holiday.is_half_day else holiday.name
            week_holidays.append(
                f"  [cyan]{_WEEKDAY_NAMES[offset]} {day.day:02d}[/cyan] {label}"
            )
        day_lines.append(
            _format_day_line(day, offset, selected, worked, expected, holiday)
        )

    if week_holidays:
        lines.append("[bold yellow]Public holidays[/bold yellow]")
        lines.extend(week_holidays)
        lines.append("")

    lines.extend(day_lines)

    lines.append("")
    lines.append(f"Worked:   {format_hours_minutes(total_worked)}")
    if expected_minutes_for_day is not None:
        lines.append(f"Expected: {format_hours_minutes(total_expected)}")
        nominal = round(weekly_hours * 60) if weekly_hours is not None else None
        if nominal is not None and nominal != total_expected:
            lines.append(
                f"[dim]Full week would be {format_hours_minutes(nominal)} "
                f"({format_hours_minutes(nominal - total_expected)} off)[/dim]"
            )
        balance = total_worked - total_expected
        balance_label = format_hours_minutes(balance)
        if balance > 0:
            balance_label = f"+{balance_label.lstrip('-')}"
        lines.append(f"Balance:  {balance_label}")

    return "\n".join(lines)
