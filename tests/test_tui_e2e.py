from __future__ import annotations

from datetime import date, time, timedelta
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Select

from time_tracker.config import AppConfig
from time_tracker.csv_store import CsvStore
from time_tracker.model import Interval, IntervalKind, WorkLocation
from time_tracker.tui.app import ConfirmQuitScreen, TimeTrackerApp


@pytest.mark.asyncio
async def test_tui_mount_loads_today_from_csv(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    today = date.today()
    store.upsert_day(
        today,
        [
            Interval(
                day=today,
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            )
        ],
    )

    app = TimeTrackerApp(store=store)
    async with app.run_test():
        assert len(app.intervals) == 1
        assert app.intervals[0].location == WorkLocation.PORZ


@pytest.mark.asyncio
async def test_tui_save_survives_reload_from_disk(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    today = date.today()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        app.intervals = [
            Interval(
                day=today,
                start=time(8, 0),
                end=time(16, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.KARLSWERK,
            )
        ]
        app._render()
        app._save_all()
        await pilot.pause()

    app2 = TimeTrackerApp(store=store)
    async with app2.run_test():
        assert len(app2.intervals) == 1
        assert app2.intervals[0].location == WorkLocation.KARLSWERK


@pytest.mark.asyncio
async def test_tui_add_shows_inline_panel(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        assert app.selected_day == date.today()
        assert not app.query_one("#add_panel").display

        await pilot.click("#add")
        await pilot.pause()

        assert app.query_one("#add_panel").display


@pytest.mark.asyncio
async def test_tui_add_uses_time_selectors_when_quick_empty(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        app._show_add_panel()
        app.query_one("#add_start", Select).value = "09:00"
        app.query_one("#add_end", Select).value = "12:00"
        app._submit_add_panel()
        await pilot.pause()

        assert len(app.intervals) == 1
        assert app.intervals[0].start == time(9, 0)


@pytest.mark.asyncio
async def test_tui_add_shows_error_on_invalid_quick(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        app._show_add_panel()
        app.query_one("#add_quick", Input).value = "not-a-time"
        app._submit_add_panel()
        await pilot.pause()

        error_widget = app.query_one("#add_error")
        assert "Error" in str(error_widget.render())


@pytest.mark.asyncio
async def test_tui_add_remembers_last_location(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        app._show_add_panel()
        app.query_one("#add_location", Select).value = WorkLocation.PORZ.value
        app.query_one("#add_start", Select).value = "09:00"
        app.query_one("#add_end", Select).value = "12:00"
        app._submit_add_panel()
        await pilot.pause()

        assert app.intervals[0].location == WorkLocation.PORZ
        assert app._last_location == WorkLocation.PORZ

        app._show_add_panel()
        assert app.query_one("#add_location", Select).value == WorkLocation.PORZ.value


@pytest.mark.asyncio
async def test_tui_keeps_unsaved_changes_when_switching_days(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        app.intervals = [
            Interval(
                day=app.selected_day,
                start=time(9, 0),
                end=time(12, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            )
        ]
        app._render()

        start_day = app.selected_day
        await pilot.press("right")
        await pilot.pause()

        assert app.selected_day == start_day + timedelta(days=1)
        assert app.intervals == []

        await pilot.click("#prev_day")
        await pilot.pause()

        assert len(app.intervals) == 1
        assert app.intervals[0].location == WorkLocation.PORZ
        assert app._has_unsaved_changes()


@pytest.mark.asyncio
async def test_tui_shift_week(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        start = app.selected_day
        await pilot.press("]")
        await pilot.pause()

        assert app.selected_day == start + timedelta(days=7)

        await pilot.press("[")
        await pilot.pause()

        assert app.selected_day == start


@pytest.mark.asyncio
async def test_tui_nav_buttons_use_ascii_arrows(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test():
        assert app.query_one("#next_day", Button).label == ">"
        assert app.query_one("#prev_week", Button).label == "<<"


@pytest.mark.asyncio
async def test_tui_quit_prompts_when_unsaved(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        app.intervals = [
            Interval(
                day=app.selected_day,
                start=time(9, 0),
                end=time(17, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.HOMEOFFICE,
            )
        ]
        app._render()

        await pilot.press("q")
        await pilot.pause()

        assert isinstance(app.screen, ConfirmQuitScreen)


@pytest.mark.asyncio
async def test_tui_week_target_banner(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()
    cfg = AppConfig(weekly_hours=37.5)

    app = TimeTrackerApp(store=store, config=cfg)
    async with app.run_test() as pilot:
        monday = app.selected_day - timedelta(days=app.selected_day.weekday())
        app.intervals = [
            Interval(
                day=monday,
                start=time(8, 0),
                end=time(16, 0),
                kind=IntervalKind.WORK,
                location=WorkLocation.PORZ,
            )
        ]
        app._render()
        await pilot.pause()

        banner = str(app.query_one("#week_target").render())
        assert "37:30" in banner or "37.5" in banner.lower() or "37:" in banner
