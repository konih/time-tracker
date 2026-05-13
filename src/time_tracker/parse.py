from __future__ import annotations

import re
from datetime import time

_TIME_RE = re.compile(
    r"^\s*(?P<h>\d{1,2})(?:[:.,](?P<m>\d{1,2}))?\s*$",
    re.IGNORECASE,
)


def parse_time_flexible(raw: str) -> time:
    """
    Parse a time from common human inputs:

    - "8" -> 08:00
    - "8:15" -> 08:15
    - "15,30" -> 15:30
    - "15.30" -> 15:30
    """
    m = _TIME_RE.match(raw)
    if not m:
        raise ValueError(f"Invalid time: {raw!r}")

    h = int(m.group("h"))
    mm_raw = m.group("m")
    mm = int(mm_raw) if mm_raw is not None else 0

    if not (0 <= h <= 23):
        raise ValueError(f"Hour out of range: {h}")
    if not (0 <= mm <= 59):
        raise ValueError(f"Minute out of range: {mm}")

    return time(hour=h, minute=mm)


_RANGE_RE = re.compile(
    r"""
    ^\s*
    (?P<a>.+?)
    \s*(?:-|to)\s*
    (?P<b>.+?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_time_range(raw: str) -> tuple[time, time]:
    """
    Parse a time range from common inputs:

    - "8 - 12"
    - "8:15 to 15,30"
    - "08:15-17:00"
    """
    m = _RANGE_RE.match(raw)
    if not m:
        raise ValueError(f"Invalid time range: {raw!r}")

    start = parse_time_flexible(m.group("a").strip())
    end = parse_time_flexible(m.group("b").strip())
    return start, end


def parse_time_ranges(raw: str) -> list[tuple[time, time]]:
    """
    Parse multiple time ranges separated by comma/semicolon.

    Examples:
    - "8-12, 13-17"
    - "08:15-12:00; 12:45-17:30"
    """
    parts = [p.strip() for p in re.split(r"[;,]", raw) if p.strip()]
    if not parts:
        raise ValueError(f"Invalid time range: {raw!r}")
    return [parse_time_range(p) for p in parts]
