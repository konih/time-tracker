from __future__ import annotations

from time_tracker.model import WorkLocation

_ALIASES: dict[str, WorkLocation] = {
    # Homeoffice
    "homeoffice": WorkLocation.HOMEOFFICE,
    "home": WorkLocation.HOMEOFFICE,
    "h": WorkLocation.HOMEOFFICE,
    "ho": WorkLocation.HOMEOFFICE,
    # Remote
    "remote": WorkLocation.REMOTE,
    "r": WorkLocation.REMOTE,
    # Office (generic)
    "office": WorkLocation.OFFICE,
    "o": WorkLocation.OFFICE,
    # Sites
    "porz": WorkLocation.PORZ,
    "p": WorkLocation.PORZ,
    "karlswerk": WorkLocation.KARLSWERK,
    "kw": WorkLocation.KARLSWERK,
    "kiel": WorkLocation.KIEL,
    "ki": WorkLocation.KIEL,
    # Business travel
    "business_travel": WorkLocation.BUSINESS_TRAVEL,
    "travel": WorkLocation.BUSINESS_TRAVEL,
    "bt": WorkLocation.BUSINESS_TRAVEL,
}


def parse_location(raw: str) -> WorkLocation:
    key = raw.strip().lower().replace(" ", "_")
    if key in _ALIASES:
        return _ALIASES[key]
    raise ValueError(
        f"Unknown location: {raw!r}. Try one of: " + ", ".join(sorted(set(_ALIASES.keys())))
    )
