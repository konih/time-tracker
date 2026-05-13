from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum


class IntervalKind(StrEnum):
    WORK = "work"
    BREAK = "break"


class WorkLocation(StrEnum):
    HOMEOFFICE = "homeoffice"
    REMOTE = "remote"
    OFFICE = "office"
    PORZ = "porz"
    KARLSWERK = "karlswerk"
    KIEL = "kiel"
    BUSINESS_TRAVEL = "business_travel"


@dataclass(frozen=True, slots=True)
class Interval:
    day: date
    start: time
    end: time
    kind: IntervalKind
    location: WorkLocation
    note: str = ""

    def minutes(self) -> int:
        start_dt = datetime.combine(self.day, self.start)
        end_dt = datetime.combine(self.day, self.end)
        if end_dt <= start_dt:
            raise ValueError("Interval end must be after start (same day).")
        delta = end_dt - start_dt
        return int(delta.total_seconds() // 60)
