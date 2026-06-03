from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import typer

from time_tracker.calc import Calculator
from time_tracker.config import AppConfig, load_app_config
from time_tracker.csv_store import CsvStore
from time_tracker.export_markdown import write_year_markdown
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.location_parse import parse_location
from time_tracker.model import Interval, IntervalKind
from time_tracker.parse import parse_time_ranges

app = typer.Typer(add_completion=False, help="Working time tracker (CSV + TUI).")


@app.callback()
def _main(
    ctx: typer.Context,
    config: Path | None = typer.Option(  # noqa: B008
        None,
        "--config",
        "-c",
        help="JSON config file (overrides default discovery).",
    ),
) -> None:
    ctx.obj = load_app_config(config)


@app.command()
def ui(
    ctx: typer.Context,
    csv_path: Path = typer.Option(  # noqa: B008
        None, help="Path to CSV (overrides config csv_path)"
    ),
):
    """Launch the clickable terminal UI."""
    cfg: AppConfig = ctx.obj
    if csv_path is not None:
        cfg = replace(cfg, csv_path=csv_path)

    from time_tracker.tui.app import TimeTrackerApp

    store = CsvStore(cfg.csv_path)
    store.ensure_exists()
    TimeTrackerApp(store=store, config=cfg).run()


@app.command()
def report(
    ctx: typer.Context,
    year_month: str = typer.Argument(..., help="Month in YYYY-MM format, e.g. 2026-05"),
    csv_path: Path = typer.Option(  # noqa: B008
        None, help="Path to CSV (overrides config csv_path)"
    ),
):
    """Print a monthly report (worked, expected, overtime, carry-over)."""
    cfg: AppConfig = ctx.obj
    if csv_path is not None:
        cfg = replace(cfg, csv_path=csv_path)

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

    typer.echo(f"{year_month}")
    typer.echo(f"Worked:   {rep.worked_hours:.2f} h")
    typer.echo(f"Expected: {rep.expected_hours:.2f} h (37.7h/week, NRW holidays)")
    typer.echo(f"Delta:    {rep.delta_hours:.2f} h")
    typer.echo(f"Carry-in: {rep.carry_in_hours:.2f} h")
    typer.echo(f"Overtime: {rep.overtime_hours:.2f} h (carry-in + delta)")
    typer.echo(
        f"Carry:    {rep.carry_out_hours:.2f} h (cap {cfg.month_carry_cap_hours:.0f}h/month)"
    )
    if rep.dropped_hours:
        typer.echo(f"Dropped:  {rep.dropped_hours:.2f} h (cap policy)")


@app.command("export-md")
def export_md(
    ctx: typer.Context,
    year: int = typer.Argument(..., help="Calendar year, e.g. 2026"),
    out: Path = typer.Option(Path("export.md"), help="Output markdown file"),  # noqa: B008
    csv_path: Path = typer.Option(None, help="Path to CSV (overrides config csv_path)"),  # noqa: B008
):
    """Export a full calendar year to a Markdown report."""
    cfg: AppConfig = ctx.obj
    if csv_path is not None:
        cfg = replace(cfg, csv_path=csv_path)

    write_year_markdown(cfg, year, out)
    typer.echo(f"Wrote {out}")


@app.command("log")
def log_today(
    ctx: typer.Context,
    parts: list[str] = typer.Argument(...),  # noqa: B008
    csv_path: Path = typer.Option(None, help="Path to CSV (overrides config csv_path)"),  # noqa: B008
):
    """
    Log today's working intervals in one line.

    Example:
    - time-tracker log 8-12 13-17 home
    """
    if len(parts) < 2:
        raise typer.BadParameter("Provide at least one time range and a location.")

    location_raw = parts[-1]
    ranges_raw = ", ".join(parts[:-1])

    loc = parse_location(location_raw)
    ranges = parse_time_ranges(ranges_raw)

    cfg: AppConfig = ctx.obj
    if csv_path is not None:
        cfg = replace(cfg, csv_path=csv_path)

    store = CsvStore(cfg.csv_path)
    store.ensure_exists()

    today = date.today()
    existing = [i for i in store.load_all() if i.day == today and i.kind == IntervalKind.WORK]

    new_intervals = [
        Interval(day=today, start=start, end=end, kind=IntervalKind.WORK, location=loc)
        for (start, end) in ranges
    ]

    store.upsert_day(today, existing + new_intervals)
    typer.echo(f"Logged {len(new_intervals)} interval(s) for {today.isoformat()} @ {loc.value}")


# Alias for muscle memory / short typing.
app.command("xzy")(log_today)
