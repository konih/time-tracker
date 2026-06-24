from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import holidays


@dataclass(frozen=True)
class HolidayInfo:
    name: str
    is_half_day: bool = False


class NRWHolidayService:
    def __init__(
        self,
        cache_dir: Path,
        half_day_dates: Iterable[str] | None = None,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.half_day_dates = frozenset(half_day_dates or ())

    def _cache_path(self, year: int) -> Path:
        return self.cache_dir / f"holidays_de_nw_{year}.json"

    def _fetch_fresh(self, year: int) -> dict[str, HolidayInfo]:
        de_nw = holidays.country_holidays("DE", subdiv="NW", years=[year])
        return {
            d.isoformat(): HolidayInfo(
                name=str(name),
                is_half_day=d.isoformat() in self.half_day_dates,
            )
            for d, name in sorted(de_nw.items())
        }

    @staticmethod
    def _write_cache(cache_path: Path, data: dict[str, HolidayInfo]) -> None:
        cache_path.write_text(
            json.dumps(
                {k: {"name": v.name, "is_half_day": v.is_half_day} for k, v in data.items()},
                indent=2,
            ),
            encoding="utf-8",
        )

    def get_year(self, year: int) -> dict[str, HolidayInfo]:
        cache_path = self._cache_path(year)
        cached: dict[str, HolidayInfo] = {}
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            cached = {k: HolidayInfo(**v) for k, v in raw.items()}

        fresh = self._fetch_fresh(year)
        if fresh != cached:
            self._write_cache(cache_path, fresh)
        return fresh

    def is_holiday(self, day: date) -> HolidayInfo | None:
        return self.get_year(day.year).get(day.isoformat())

    @staticmethod
    def day_off_note(day: date, holiday: HolidayInfo | None) -> str | None:
        if day.weekday() >= 5:
            return "Weekend"
        if holiday is None:
            return None
        suffix = " (½ day)" if holiday.is_half_day else ""
        return f"Holiday — {holiday.name}{suffix}"
