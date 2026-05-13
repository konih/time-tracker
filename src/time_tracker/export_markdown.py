from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path

from time_tracker.calc import Calculator
from time_tracker.config import AppConfig
from time_tracker.csv_store import CsvStore
from time_tracker.holidays_nrw import NRWHolidayService


def _fmt_time(t) -> str:
    return t.strftime("%H:%M")


def _iter_days_in_month(year: int, month: int):
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def _day_type_line(d: date, holiday_service: NRWHolidayService) -> str:
    if d.weekday() == 5:
        return "Weekend (Saturday)"
    if d.weekday() == 6:
        return "Weekend (Sunday)"
    h = holiday_service.is_holiday(d)
    if h is None:
        return "Workday"
    suffix = " (½ day)" if h.is_half_day else ""
    return f"Holiday - {h.name}{suffix}"


def _fmt_expected_hours(mins: int) -> str:
    if mins <= 0:
        return "-"
    return f"{mins / 60.0:.2f}"


def write_month_markdown(cfg: AppConfig, year_month: str, out: Path) -> None:
    """Write a Markdown report for ``year_month`` (YYYY-MM) to ``out``."""
    year, month = map(int, year_month.split("-", 1))
    store = CsvStore(cfg.csv_path)
    intervals = store.load_all()

    holiday_service = NRWHolidayService(
        cache_dir=cfg.cache_dir, half_day_dates=cfg.half_day_holidays
    )
    calc = Calculator(cfg, holiday_service)
    reps = calc.monthly_reports(
        intervals, start=None, end_inclusive=(year, month), initial_carry_hours=0.0
    )
    rep = reps[-1] if reps else calc.monthly_report(intervals, year, month, carry_in_hours=0.0)

    by_day: dict[str, list] = {}
    for it in intervals:
        if it.day.year == year and it.day.month == month and it.kind == "work":
            by_day.setdefault(it.day.isoformat(), []).append(it)

    def _hhmm(mins: int) -> str:
        return f"{mins // 60:02d}:{mins % 60:02d}"

    nominal_day_h = cfg.weekly_hours / 5.0

    lines: list[str] = []
    lines.append(f"# ⏱️ Time report — {year_month}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- 📆 Required per week: **{cfg.weekly_hours:.2f} h** (Mon-Fri schedule)")
    lines.append(f"- 📌 Nominal workday: **{nominal_day_h:.2f} h/day** (week hours ÷ 5)")
    lines.append(f"- ✅ Worked: **{rep.worked_hours:.2f} h**")
    lines.append(f"- 🎯 Expected (month): **{rep.expected_hours:.2f} h**")
    lines.append(f"- + Delta: **{rep.delta_hours:.2f} h**")
    lines.append(f"- 🧾 Overtime (uncapped): **{rep.overtime_hours:.2f} h**")
    lines.append(f"- 📦 Carry out: **{rep.carry_out_hours:.2f} h**")
    if rep.dropped_hours:
        lines.append(f"- 🗑️ Dropped (cap policy): **{rep.dropped_hours:.2f} h**")
    lines.append("")

    hol_year = holiday_service.get_year(year)
    in_month_holidays = sorted(
        (d, info)
        for iso, info in hol_year.items()
        if (d := date.fromisoformat(iso)).year == year and d.month == month
    )
    lines.append(f"## Public holidays (NRW, {year})")
    if not in_month_holidays:
        lines.append("*No public holidays this month.*")
    else:
        for d, info in in_month_holidays:
            extra = " (½ day)" if info.is_half_day else ""
            lines.append(f"- **{d.isoformat()}** ({d.strftime('%A')}): {info.name}{extra}")
    lines.append("")

    weekend_days = [d for d in _iter_days_in_month(year, month) if d.weekday() >= 5]
    lines.append("## Weekends (Saturday & Sunday)")
    if not weekend_days:
        lines.append("*None in this month.*")
    else:
        for d in weekend_days:
            lines.append(f"- **{d.isoformat()}** ({d.strftime('%A')})")
    lines.append("")

    lines.append("## Daily details (days with logged work)")
    lines.append("")
    lines.append(
        "| Date | Weekday | Day type | 📍 Location | 🕘 Work intervals | "
        "☕ Breaks (inferred) | ✅ Total | 🎯 Expected (h) |"
    )
    lines.append("|---|---|---|---|---|---|---:|---:|")

    for day in sorted(by_day.keys()):
        day_intervals = sorted(by_day[day], key=lambda x: x.start)
        if not day_intervals:
            continue

        d = date.fromisoformat(day)
        weekday = d.strftime("%a")
        dtype = _day_type_line(d, holiday_service)
        exp_mins = calc.expected_minutes_for_day(d)
        exp_col = _fmt_expected_hours(exp_mins)

        locs = ", ".join(sorted({it.location.value for it in day_intervals}))
        work = "<br>".join(f"{_fmt_time(it.start)}-{_fmt_time(it.end)}" for it in day_intervals)

        gaps: list[str] = []
        for prev, nxt in pairwise(day_intervals):
            if nxt.start > prev.end:
                gaps.append(f"{_fmt_time(prev.end)}-{_fmt_time(nxt.start)}")
        breaks = "<br>".join(gaps) if gaps else ""

        total_mins = sum(it.minutes() for it in day_intervals)
        lines.append(
            f"| {day} | {weekday} | {dtype} | {locs} | {work} | {breaks} | "
            f"{_hhmm(total_mins)} | {exp_col} |"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
