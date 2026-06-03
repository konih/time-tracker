from __future__ import annotations

import json
from pathlib import Path

import pytest

from time_tracker.config import AppConfig, discover_config_path, load_app_config


def test_load_app_config_merges_paths_relative_to_file(tmp_path: Path):
    sub = tmp_path / "proj"
    sub.mkdir()
    cfg_path = sub / "my.json"
    cfg_path.write_text(
        json.dumps(
            {
                "csv_path": "logs/time.csv",
                "cache_dir": "state/cache",
                "export_dir": "out/md",
            }
        ),
        encoding="utf-8",
    )

    cfg = load_app_config(cfg_path)
    assert cfg.csv_path == sub / "logs" / "time.csv"
    assert cfg.cache_dir == sub / "state" / "cache"
    assert cfg.export_dir == sub / "out" / "md"


def test_load_app_config_half_days(tmp_path: Path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"half_day_holidays": ["2026-12-24", "2026-12-31"]}),
        encoding="utf-8",
    )
    cfg = load_app_config(p)
    assert cfg.half_day_holidays == frozenset({"2026-12-24", "2026-12-31"})


def test_load_app_config_rejects_non_object(tmp_path: Path):
    p = tmp_path / "bad.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_app_config(p)


def test_load_app_config_numeric_fields(tmp_path: Path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"weekly_hours": 39.0, "month_carry_cap_hours": 40.0}),
        encoding="utf-8",
    )
    cfg = load_app_config(p)
    assert cfg.weekly_hours == 39.0
    assert cfg.month_carry_cap_hours == 40.0


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.csv_path == Path("data/time_log.csv")
    assert cfg.half_day_holidays == frozenset()


def test_discover_prefers_time_tracker_config_over_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time-tracker.config.json").write_text(
        json.dumps({"csv_path": "from_json.csv"}),
        encoding="utf-8",
    )
    (tmp_path / "time-tracker.config").write_text(
        json.dumps({"csv_path": "from_noext.csv"}),
        encoding="utf-8",
    )
    assert discover_config_path() == (tmp_path / "time-tracker.config").resolve()
    cfg = load_app_config()
    assert cfg.csv_path == tmp_path / "from_noext.csv"
