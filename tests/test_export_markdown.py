from __future__ import annotations

from datetime import date, time
from pathlib import Path

from time_tracker.config import AppConfig
from time_tracker.csv_store import CsvStore
from time_tracker.export_markdown import write_month_markdown
from time_tracker.model import Interval, IntervalKind, WorkLocation


def test_write_month_markdown_creates_file(tmp_path: Path):
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
    write_month_markdown(cfg, "2026-05", out)

    text = out.read_text(encoding="utf-8")
    assert "2026-05-08" in text
    assert "porz" in text
    assert "Time report" in text
    assert "Required per week" in text
    assert "Nominal workday" in text
    assert "Public holidays (NRW" in text
    assert "Weekends (Saturday & Sunday)" in text
    assert "Fri" in text
    assert "Workday" in text
