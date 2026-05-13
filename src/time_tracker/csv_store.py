from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict
from datetime import date, datetime, time
from pathlib import Path

from time_tracker.model import Interval, IntervalKind, WorkLocation

CSV_HEADER = ["date", "start", "end", "kind", "location", "note"]


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_time(s: str) -> time:
    return datetime.strptime(s, "%H:%M").time()


def _fmt_date(d: date) -> str:
    return d.isoformat()


def _fmt_time(t: time) -> str:
    return t.strftime("%H:%M")


class CsvStore:
    def __init__(self, path: Path):
        self.path = path

    def ensure_exists(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
                writer.writeheader()

    def load_all(self) -> list[Interval]:
        if not self.path.exists():
            return []
        with self.path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            items: list[Interval] = []
            for row in reader:
                if not row:
                    continue
                kind_raw = (row.get("kind") or IntervalKind.WORK.value).strip()
                items.append(
                    Interval(
                        day=_parse_date(row["date"]),
                        start=_parse_time(row["start"]),
                        end=_parse_time(row["end"]),
                        kind=IntervalKind(kind_raw),
                        location=WorkLocation(row["location"]),
                        note=row.get("note", "") or "",
                    )
                )
            return items

    def save_all(self, intervals: Iterable[Interval]) -> None:
        self.ensure_exists()
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            writer.writeheader()
            for it in sorted(intervals, key=lambda x: (x.day, x.start, x.kind)):
                d = asdict(it)
                writer.writerow(
                    {
                        "date": _fmt_date(d["day"]),
                        "start": _fmt_time(d["start"]),
                        "end": _fmt_time(d["end"]),
                        "kind": d["kind"],
                        "location": d["location"],
                        "note": d["note"] or "",
                    }
                )

    def upsert_day(self, day: date, intervals: list[Interval]) -> None:
        all_items = [i for i in self.load_all() if i.day != day]
        all_items.extend(intervals)
        self.save_all(all_items)
