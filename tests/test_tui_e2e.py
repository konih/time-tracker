from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from time_tracker.csv_store import CsvStore
from time_tracker.tui.app import AddIntervalsScreen, TimeTrackerApp


@pytest.mark.asyncio
async def test_tui_add_opens_modal(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        # Ensure app booted
        assert app.selected_day == date.today()

        await pilot.click("#add")
        await pilot.pause()

        assert isinstance(app.screen, AddIntervalsScreen)


@pytest.mark.asyncio
async def test_tui_add_shows_error_on_empty_input(tmp_path: Path):
    store = CsvStore(tmp_path / "time_log.csv")
    store.ensure_exists()

    app = TimeTrackerApp(store=store)
    async with app.run_test() as pilot:
        await pilot.click("#add")
        await pilot.pause()

        # Click Add in modal with empty quick field
        await pilot.click("#save")
        await pilot.pause()

        assert isinstance(app.screen, AddIntervalsScreen)
        error_widget = app.screen.query_one("#error")
        assert "Error" in str(error_widget.render())
