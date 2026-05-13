from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path

from typer.testing import CliRunner

from time_tracker.cli import app
from time_tracker.csv_store import CsvStore
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.model import Interval, IntervalKind, WorkLocation


def test_holiday_cache_roundtrip(tmp_path: Path):
    cache_dir = tmp_path / ".cache"
    svc = NRWHolidayService(cache_dir=cache_dir, half_day_dates={"2026-12-24"})

    data = svc.get_year(2026)
    cache_file = cache_dir / "holidays_de_nw_2026.json"
    assert cache_file.exists()

    # Load again from cache and ensure we still get same keys.
    data2 = svc.get_year(2026)
    assert set(data2.keys()) == set(data.keys())


def test_cli_report_smoke(tmp_path: Path):
    csv_path = tmp_path / "time_log.csv"
    store = CsvStore(csv_path)
    store.save_all(
        [
            Interval(
                day=date(2026, 5, 8),
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
                note="",
            )
        ]
    )

    runner = CliRunner()
    result = runner.invoke(app, ["report", "2026-05", "--csv-path", str(csv_path)])
    assert result.exit_code == 0, result.output

    assert "2026-05" in result.output
    assert re.search(r"Worked:\s+\d+\.\d{2}\s+h", result.output)
    assert "Overtime:" in result.output


def test_cli_ui_smoke(monkeypatch, tmp_path: Path):
    csv_path = tmp_path / "time_log.csv"

    ran = {"called": False}

    class DummyApp:
        def __init__(self, store, config=None):
            self.store = store

        def run(self):
            ran["called"] = True

    monkeypatch.setattr("time_tracker.tui.app.TimeTrackerApp", DummyApp)

    runner = CliRunner()
    result = runner.invoke(app, ["ui", "--csv-path", str(csv_path)])
    assert result.exit_code == 0, result.output
    assert ran["called"] is True
    assert csv_path.exists()


def test_cli_log_today_writes_csv(tmp_path: Path):
    csv_path = tmp_path / "time_log.csv"
    runner = CliRunner()
    result = runner.invoke(app, ["log", "8-12", "13-17", "home", "--csv-path", str(csv_path)])
    assert result.exit_code == 0, result.output

    store = CsvStore(csv_path)
    intervals = store.load_all()
    assert len(intervals) == 2
