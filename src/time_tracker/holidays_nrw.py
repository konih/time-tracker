from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import holidays


@dataclass(frozen=True)
class HolidayInfo:
    name: str
    is_half_day: bool = False


class NRWHolidayService:
    def __init__(self, cache_dir: Path, half_day_dates: set[str] | None = None):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.half_day_dates = half_day_dates or set()

    def _cache_path(self, year: int) -> Path:
        return self.cache_dir / f"holidays_de_nw_{year}.json"

    def get_year(self, year: int) -> dict[str, HolidayInfo]:
        cache_path = self._cache_path(year)
        if cache_path.exists():
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            return {k: HolidayInfo(**v) for k, v in raw.items()}

        de_nw = holidays.country_holidays("DE", subdiv="NW", years=[year])
        data: dict[str, HolidayInfo] = {}
        for d, name in de_nw.items():
            iso = d.isoformat()
            data[iso] = HolidayInfo(name=str(name), is_half_day=iso in self.half_day_dates)

        cache_path.write_text(
            json.dumps(
                {k: {"name": v.name, "is_half_day": v.is_half_day} for k, v in data.items()},
                indent=2,
            ),
            encoding="utf-8",
        )
        return data

    def is_holiday(self, day: date) -> HolidayInfo | None:
        info = self.get_year(day.year).get(day.isoformat())
        return info
