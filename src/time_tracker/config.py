from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path = Path("data")
    csv_path: Path = Path("data/time_log.csv")
    cache_dir: Path = Path(".cache")
    export_dir: Path = Path("exports")
    country: str = "DE"
    subdivision: str = "NW"  # NRW
    weekly_hours: float = 37.5
    month_carry_cap_hours: float = 60.0
    year_carry_cap_hours: float = 25.0
    half_day_holidays: frozenset[str] = field(default_factory=frozenset)


def _resolve_against_root(root: Path, raw: str | Path, default: Path) -> Path:
    p = default if raw is None or raw == "" else Path(raw)
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def config_path_candidates() -> list[Path]:
    env = os.environ.get("TIME_TRACKER_CONFIG")
    if env:
        return [Path(env).expanduser()]
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return [
        Path("time-tracker.config"),
        Path("time-tracker.config.json"),
        xdg / "time-tracker" / "config",
        xdg / "time-tracker" / "config.json",
    ]


def discover_config_path(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        p = explicit.expanduser()
        return p if p.is_file() else None
    for candidate in config_path_candidates():
        p = candidate.expanduser()
        if p.is_file():
            return p.resolve()
    return None


def load_app_config(config_file: Path | None = None) -> AppConfig:
    """Load defaults merged with JSON from the first config file found.

    Search order (unless ``TIME_TRACKER_CONFIG`` or ``--config`` is set): ``time-tracker.config``,
    ``time-tracker.config.json``, then ``~/.config/time-tracker/config`` and ``config.json``.
    """
    base = AppConfig()
    path = discover_config_path(config_file)
    if path is None:
        return base

    root = path.parent.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a JSON object: {path}")

    kwargs: dict = {}
    if "data_dir" in data:
        kwargs["data_dir"] = _resolve_against_root(root, data["data_dir"], base.data_dir)
    if "csv_path" in data:
        kwargs["csv_path"] = _resolve_against_root(root, data["csv_path"], base.csv_path)
    if "cache_dir" in data:
        kwargs["cache_dir"] = _resolve_against_root(root, data["cache_dir"], base.cache_dir)
    if "export_dir" in data:
        kwargs["export_dir"] = _resolve_against_root(root, data["export_dir"], base.export_dir)
    if "country" in data:
        kwargs["country"] = str(data["country"])
    if "subdivision" in data:
        kwargs["subdivision"] = str(data["subdivision"])
    if "weekly_hours" in data:
        kwargs["weekly_hours"] = float(data["weekly_hours"])
    if "month_carry_cap_hours" in data:
        kwargs["month_carry_cap_hours"] = float(data["month_carry_cap_hours"])
    if "year_carry_cap_hours" in data:
        kwargs["year_carry_cap_hours"] = float(data["year_carry_cap_hours"])
    if "half_day_holidays" in data:
        raw_hd = data["half_day_holidays"]
        if not isinstance(raw_hd, list):
            raise ValueError("half_day_holidays must be a list of date strings")
        kwargs["half_day_holidays"] = frozenset(str(x) for x in raw_hd)

    return replace(base, **kwargs)
