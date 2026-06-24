from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select, Static

from time_tracker.calc import Calculator
from time_tracker.config import AppConfig
from time_tracker.csv_store import CsvStore
from time_tracker.export_markdown import write_year_markdown
from time_tracker.holidays_nrw import NRWHolidayService
from time_tracker.model import Interval, IntervalKind, WorkLocation
from time_tracker.parse import parse_time_range, parse_time_ranges
from time_tracker.tui.day_stats import (
    day_warnings,
    format_hours_minutes,
    format_week_target_banner,
    week_expected_minutes,
    week_overview_lines,
    week_total_worked,
    work_minutes,
)

_TIME_OPTIONS = tuple(
    (f"{h:02d}:{m:02d}", f"{h:02d}:{m:02d}")
    for h in range(24)
    for m in (0, 15, 30, 45)
)
_LOCATION_OPTIONS = tuple((loc.value, loc.value) for loc in WorkLocation)


def _today() -> date:
    return datetime.now().date()


def _parse_time(s: str) -> time:
    return datetime.strptime(s.strip(), "%H:%M").time()


def _fmt_time(t: time) -> str:
    return t.strftime("%H:%M")


def _interval_snapshot(intervals: list[Interval]) -> tuple:
    return tuple(
        sorted(
            (i.day, i.start, i.end, i.kind, i.location, i.note)
            for i in intervals
        )
    )


class ConfirmQuitScreen(ModalScreen[bool]):
    def compose(self) -> ComposeResult:
        yield Static("Unsaved changes will be lost.", id="title")
        yield Static("Quit without saving?", id="message")
        with Horizontal():
            yield Button("Keep editing", variant="default", id="cancel")
            yield Button("Quit", variant="error", id="quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(False)
        elif event.button.id == "quit":
            self.dismiss(True)


class EditIntervalScreen(ModalScreen[Interval | None]):
    def __init__(self, day: date, existing: Interval | None = None):
        super().__init__()
        self.day = day
        self.existing = existing

    def compose(self) -> ComposeResult:
        yield Static("Edit interval", id="title")
        with Vertical(id="form"):
            loc = self.existing.location if self.existing else WorkLocation.HOMEOFFICE
            yield Label(f"Date: {self.day.isoformat()}")
            yield Static("", id="error")
            yield Input(
                value="",
                id="quick",
                placeholder="Quick entry (e.g. 8 - 12, 8:15 to 15,30)",
            )
            yield Select(
                list(_LOCATION_OPTIONS),
                value=loc.value,
                id="location",
                prompt="Location",
            )
            yield Select(
                list(_TIME_OPTIONS),
                value=_fmt_time(self.existing.start) if self.existing else "09:00",
                id="start",
                prompt="Start",
            )
            yield Select(
                list(_TIME_OPTIONS),
                value=_fmt_time(self.existing.end) if self.existing else "17:00",
                id="end",
                prompt="End",
            )
            yield Input(
                value=self.existing.note if self.existing else "",
                id="note",
                placeholder="Optional note",
            )
            with Horizontal():
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Save", variant="primary", id="save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "save":
            try:
                loc = WorkLocation(self.query_one("#location", Select).value)
                quick = self.query_one("#quick", Input).value.strip()
                if quick:
                    start, end = parse_time_range(quick)
                else:
                    start = _parse_time(self.query_one("#start", Select).value)
                    end = _parse_time(self.query_one("#end", Select).value)
                note = self.query_one("#note", Input).value.strip()
                self.dismiss(
                    Interval(
                        day=self.day,
                        start=start,
                        end=end,
                        kind=IntervalKind.WORK,
                        location=loc,
                        note=note,
                    )
                )
            except ValueError as e:
                self.query_one("#error", Static).update(f"[b red]Error:[/b red] {e}")


@dataclass(frozen=True)
class DaySelected(Message):
    day: date


class TimeTrackerApp(App):
    CSS = """
    #title { padding: 1 2; text-style: bold; }
    #form { padding: 1 2; height: auto; }
    #day_hours { padding: 0 1; }
    #day_warnings { padding: 0 1; color: $warning; }
    #week_target {
        padding: 1;
        margin: 0 1 1 1;
        text-align: center;
        border: heavy $accent;
    }
    #week_summary { padding: 0 1; }
    #add_panel {
        height: auto;
        border: tall $accent;
        padding: 1;
        margin: 0 0 1 0;
        background: $surface;
    }
    #add_panel Select { width: 1fr; }
    #add_times { height: auto; }
    #day_nav Button {
        min-width: 5;
    }
    #day_nav Input {
        width: 1fr;
    }
    DataTable { height: 1fr; }
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
        ("a", "add_interval", "Add"),
        ("e", "edit_interval", "Edit"),
        ("d", "delete_interval", "Delete"),
        ("left", "prev_day", "Prev day"),
        ("right", "next_day", "Next day"),
        ("shift+left", "prev_week", "Prev week"),
        ("shift+right", "next_week", "Next week"),
        ("[", "prev_week", "Prev week"),
        ("]", "next_week", "Next week"),
        ("s", "save_all", "Save"),
        ("escape", "close_add_panel", "Close add"),
    ]

    def __init__(self, store: CsvStore, config: AppConfig | None = None):
        super().__init__()
        self.store = store
        self._cfg = config if config is not None else AppConfig()
        self.selected_day: date = _today()
        self.intervals: list[Interval] = []
        self._clipboard: list[Interval] | None = None
        self._working: dict[date, list[Interval]] = {}
        self._baseline: dict[date, tuple] = {}
        self._last_location: WorkLocation = WorkLocation.HOMEOFFICE
        self._holiday_svc: NRWHolidayService | None = None

    def _holiday_service(self) -> NRWHolidayService:
        if self._holiday_svc is None:
            self._holiday_svc = NRWHolidayService(
                cache_dir=self._cfg.cache_dir,
                half_day_dates=self._cfg.half_day_holidays,
            )
        return self._holiday_svc

    def _calculator(self) -> Calculator:
        return Calculator(self._cfg, self._holiday_service())

    def _day_off_note(self, day: date) -> str | None:
        svc = self._holiday_service()
        return NRWHolidayService.day_off_note(day, svc.is_holiday(day))

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Label("Day")
                with Horizontal(id="day_nav"):
                    yield Button("<<", id="prev_week", variant="default")
                    yield Button("<", id="prev_day", variant="default")
                    yield Input(self.selected_day.isoformat(), id="day_input")
                    yield Button(">", id="next_day", variant="default")
                    yield Button(">>", id="next_week", variant="default")
                yield Static("", id="day_hours")
                yield Static("", id="day_warnings")
                with Horizontal():
                    yield Button("Load", id="load")
                    yield Button("Today", id="today")
                with Vertical(id="add_panel"):
                    yield Static("Add interval", id="add_title")
                    yield Static("", id="add_error")
                    yield Select(
                        list(_LOCATION_OPTIONS),
                        value=self._last_location.value,
                        id="add_location",
                        prompt="Location",
                    )
                    yield Input(
                        value="",
                        id="add_quick",
                        placeholder="Quick: 8-12, 13-17 or 8:15 to 15,30",
                    )
                    yield Label("Or pick times (scroll lists)")
                    with Horizontal(id="add_times"):
                        yield Select(
                            list(_TIME_OPTIONS),
                            value="09:00",
                            id="add_start",
                            prompt="Start",
                        )
                        yield Select(
                            list(_TIME_OPTIONS),
                            value="17:00",
                            id="add_end",
                            prompt="End",
                        )
                    yield Input(value="", id="add_note", placeholder="Optional note")
                    with Horizontal():
                        yield Button("Add interval", id="add_submit", variant="primary")
                        yield Button("Clear", id="add_clear")
                        yield Button("Close", id="add_close")
                yield Label("Intervals (click row to select)")
                yield DataTable(id="table")
                with Horizontal():
                    yield Button("Add", id="add", variant="primary")
                    yield Button("Edit", id="edit")
                    yield Button("Delete", id="delete", variant="error")
                    yield Button("Save", id="save_all", variant="primary")
                with Horizontal():
                    yield Button("Copy day", id="copy_day")
                    yield Button("Paste day", id="paste_day")
                yield Label("Export year (Markdown)")
                yield Input(
                    id="export_year",
                    placeholder="YYYY",
                )
                yield Input(
                    id="export_path",
                    placeholder="Output .md file",
                )
                yield Button("Export Markdown", id="export_md", variant="primary")
            with Vertical():
                yield Label("This week")
                yield Static("", id="week_target")
                yield Static("", id="week_summary")
                yield Label("Month summary")
                yield Static("", id="month_summary")
                yield Label("Tips")
                yield Static(
                    "<< / >> week · < / > day · a add · Esc close · s save · q quit",
                    id="tips",
                )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("Start", "End", "Location", "Note")
        self.query_one("#add_panel").display = False
        self._load_day(self.selected_day)

    def _load_from_store(self, day: date) -> list[Interval]:
        return [i for i in self.store.load_all() if i.day == day]

    def _ensure_day_cached(self, day: date) -> None:
        if day in self._working:
            return
        loaded = self._load_from_store(day)
        self._working[day] = loaded
        self._baseline[day] = _interval_snapshot(loaded)

    def _commit_current_day(self) -> None:
        self._working[self.selected_day] = list(self.intervals)

    def _dirty_days(self) -> list[date]:
        self._commit_current_day()
        dirty: list[date] = []
        for day, intervals in self._working.items():
            if _interval_snapshot(intervals) != self._baseline.get(day, ()):
                dirty.append(day)
        return sorted(dirty)

    def _has_unsaved_changes(self) -> bool:
        return bool(self._dirty_days())

    def _intervals_for_day(self, day: date) -> list[Interval]:
        if day == self.selected_day:
            return self.intervals
        self._ensure_day_cached(day)
        return self._working[day]

    def _load_day(self, day: date) -> None:
        self._commit_current_day()
        self._hide_add_panel()
        self.selected_day = day
        self._ensure_day_cached(day)
        self.intervals = [
            Interval(
                day=i.day,
                start=i.start,
                end=i.end,
                kind=i.kind,
                location=i.location,
                note=i.note,
            )
            for i in self._working[day]
        ]
        self._render()

    def _shift_day(self, delta: int) -> None:
        self._load_day(self.selected_day + timedelta(days=delta))

    def _shift_week(self, delta: int) -> None:
        self._load_day(self.selected_day + timedelta(days=7 * delta))

    def _add_panel_visible(self) -> bool:
        return self.query_one("#add_panel").display

    def _suggest_next_times(self) -> tuple[str, str]:
        work = sorted(
            (i for i in self.intervals if i.kind == IntervalKind.WORK),
            key=lambda i: i.start,
        )
        if not work:
            return "09:00", "17:00"
        last = work[-1]
        start = _fmt_time(last.end)
        end_dt = datetime.combine(self.selected_day, last.end) + timedelta(hours=1)
        return start, end_dt.strftime("%H:%M")

    def _show_add_panel(self) -> None:
        panel = self.query_one("#add_panel")
        panel.display = True
        self.query_one("#add_title", Static).update(
            f"Add interval · {self.selected_day.isoformat()}"
        )
        self.query_one("#add_location", Select).value = self._last_location.value
        start_default, end_default = self._suggest_next_times()
        self.query_one("#add_start", Select).value = start_default
        self.query_one("#add_end", Select).value = end_default
        self.query_one("#add_quick", Input).value = ""
        self.query_one("#add_note", Input).value = ""
        self.query_one("#add_error", Static).update("")

    def _hide_add_panel(self) -> None:
        self.query_one("#add_panel").display = False
        self.query_one("#add_error", Static).update("")

    def _submit_add_panel(self) -> None:
        try:
            loc = WorkLocation(self.query_one("#add_location", Select).value)
            raw = self.query_one("#add_quick", Input).value.strip()
            note = self.query_one("#add_note", Input).value.strip()
            if raw:
                ranges = parse_time_ranges(raw)
            else:
                start = _parse_time(self.query_one("#add_start", Select).value)
                end = _parse_time(self.query_one("#add_end", Select).value)
                ranges = [(start, end)]
            if not ranges:
                raise ValueError("Enter times or pick start/end.")
            new_intervals = [
                Interval(
                    day=self.selected_day,
                    start=start,
                    end=end,
                    kind=IntervalKind.WORK,
                    location=loc,
                    note=note,
                )
                for (start, end) in ranges
            ]
            self._last_location = loc
            self.intervals.extend(new_intervals)
            self._render()
            self.notify(
                f"Added {len(new_intervals)} interval{'s' if len(new_intervals) != 1 else ''}",
                timeout=1.5,
            )
            start_default, end_default = self._suggest_next_times()
            self.query_one("#add_start", Select).value = start_default
            self.query_one("#add_end", Select).value = end_default
            self.query_one("#add_quick", Input).value = ""
            self.query_one("#add_error", Static).update("")
        except ValueError as e:
            self.query_one("#add_error", Static).update(f"[b red]Error:[/b red] {e}")

    def _render(self) -> None:
        self.query_one("#day_input", Input).value = self.selected_day.isoformat()
        y = f"{self.selected_day.year:04d}"
        self.query_one("#export_year", Input).value = y
        self.query_one("#export_path", Input).value = str(self._cfg.export_dir / f"{y}.md")
        table = self.query_one("#table", DataTable)
        table.clear()
        for it in sorted(self.intervals, key=lambda x: x.start):
            table.add_row(
                _fmt_time(it.start),
                _fmt_time(it.end),
                it.location.value,
                it.note,
            )
        worked = work_minutes(self.intervals)
        hours_widget = self.query_one("#day_hours", Static)
        off_note = self._day_off_note(self.selected_day)
        holiday = self._holiday_service().is_holiday(self.selected_day)
        calc = self._calculator()
        expected_today = calc.expected_minutes_for_day(self.selected_day)
        if holiday and holiday.is_half_day:
            hours_widget.update(
                f"[bold cyan]½ day — {holiday.name}[/bold cyan] · "
                f"worked {format_hours_minutes(worked)} · "
                f"expected {format_hours_minutes(expected_today)}"
            )
        elif off_note and expected_today == 0:
            hours_widget.update(
                f"[bold cyan]🎉 {off_note}[/bold cyan] · "
                f"worked {format_hours_minutes(worked)}"
            )
        else:
            hours_widget.update(
                f"Worked today: [bold]{format_hours_minutes(worked)}[/bold]"
            )
        warnings = list(day_warnings(self.intervals))
        if off_note and worked and expected_today == 0:
            warnings.insert(0, f"Work logged on {off_note.lower()}")
        warn_widget = self.query_one("#day_warnings", Static)
        if warnings:
            warn_widget.update("\n".join(f"⚠ {w}" for w in warnings))
        else:
            warn_widget.update("")
        total_week = week_total_worked(self.selected_day, self._intervals_for_day)
        week_target = week_expected_minutes(
            self.selected_day, calc.expected_minutes_for_day
        )
        self.query_one("#week_target", Static).update(
            format_week_target_banner(total_week, week_target)
        )
        self.query_one("#week_summary", Static).update(self._week_summary_string())
        self.query_one("#month_summary", Static).update(self._month_summary_string())
        self._update_save_button()

    def _update_save_button(self) -> None:
        btn = self.query_one("#save_all", Button)
        if self._has_unsaved_changes():
            btn.label = "Save *"
            btn.variant = "warning"
        else:
            btn.label = "Save"
            btn.variant = "primary"

    def _week_summary_string(self) -> str:
        calc = self._calculator()
        svc = self._holiday_service()
        return week_overview_lines(
            self.selected_day,
            self.selected_day,
            self._intervals_for_day,
            calc.expected_minutes_for_day,
            svc.is_holiday,
            self._cfg.weekly_hours,
        )

    def _month_summary_string(self) -> str:
        calc = self._calculator()

        all_items = self.store.load_all()
        for day in self._dirty_days():
            all_items = [i for i in all_items if i.day != day]
            all_items.extend(self._working[day])

        reps = calc.monthly_reports(
            all_items,
            start=None,
            end_inclusive=(self.selected_day.year, self.selected_day.month),
            initial_carry_hours=0.0,
        )
        rep = (
            reps[-1]
            if reps
            else calc.monthly_report(all_items, self.selected_day.year, self.selected_day.month)
        )

        lines = [
            f"📅 {rep.year:04d}-{rep.month:02d}",
            f"✅ worked: {rep.worked_hours:.2f} h",
            f"🎯 expected: {rep.expected_hours:.2f} h",
            f"+ delta: {rep.delta_hours:.2f} h",
            f"🧾 overtime: {rep.overtime_hours:.2f} h",
            f"📦 carry: {rep.carry_out_hours:.2f} h",
        ]
        if rep.dropped_hours:
            lines.append(f"🗑️ dropped: {rep.dropped_hours:.2f} h")
        return "\n".join(lines)

    def _selected_row_index(self) -> int | None:
        table = self.query_one("#table", DataTable)
        if table.cursor_row is None:
            return None
        if table.row_count == 0:
            return None
        return table.cursor_row

    def action_add_interval(self) -> None:
        if self._add_panel_visible():
            self._hide_add_panel()
        else:
            self._show_add_panel()

    def action_close_add_panel(self) -> None:
        if self._add_panel_visible():
            self._hide_add_panel()

    def action_edit_interval(self) -> None:
        idx = self._selected_row_index()
        if idx is None:
            return

        existing = sorted(self.intervals, key=lambda x: x.start)[idx]

        def _on_dismissed(result: Interval | None) -> None:
            if result is None:
                return
            ordered = sorted(self.intervals, key=lambda x: x.start)
            ordered[idx] = result
            self.intervals = ordered
            self._last_location = result.location
            self._render()

        self.push_screen(EditIntervalScreen(self.selected_day, existing=existing), _on_dismissed)

    def action_delete_interval(self) -> None:
        idx = self._selected_row_index()
        if idx is None:
            return
        ordered = sorted(self.intervals, key=lambda x: x.start)
        ordered.pop(idx)
        self.intervals = ordered
        self._render()

    def action_prev_day(self) -> None:
        self._shift_day(-1)

    def action_next_day(self) -> None:
        self._shift_day(1)

    def action_prev_week(self) -> None:
        self._shift_week(-1)

    def action_next_week(self) -> None:
        self._shift_week(1)

    def action_save_all(self) -> None:
        self._save_all()

    def _save_all(self) -> None:
        dirty = self._dirty_days()
        if not dirty:
            self.notify("Nothing to save", timeout=1.0)
            return
        for day in dirty:
            self.store.upsert_day(day, self._working[day])
            self._baseline[day] = _interval_snapshot(self._working[day])
        count = len(dirty)
        self.notify(f"Saved {count} day{'s' if count != 1 else ''}", timeout=1.5)
        self._render()

    def action_quit(self) -> None:
        if not self._has_unsaved_changes():
            self.exit()
            return

        def _on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                self.exit()

        self.push_screen(ConfirmQuitScreen(), _on_confirm)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "day_input":
            raw = event.input.value.strip()
            try:
                self._load_day(datetime.strptime(raw, "%Y-%m-%d").date())
            except ValueError:
                self.notify("Invalid date (use YYYY-MM-DD)", timeout=2.0)
            return
        if event.input.id == "add_quick" and self._add_panel_visible():
            self._submit_add_panel()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev_week":
            self.action_prev_week()
        elif event.button.id == "prev_day":
            self.action_prev_day()
        elif event.button.id == "next_day":
            self.action_next_day()
        elif event.button.id == "next_week":
            self.action_next_week()
        elif event.button.id == "today":
            self._load_day(_today())
        elif event.button.id == "load":
            value = self.query_one("#day_input", Input).value.strip()
            try:
                self._load_day(datetime.strptime(value, "%Y-%m-%d").date())
            except ValueError:
                self.notify("Invalid date (use YYYY-MM-DD)", timeout=2.0)
        elif event.button.id == "add":
            self.action_add_interval()
        elif event.button.id == "add_submit":
            self._submit_add_panel()
        elif event.button.id == "add_clear":
            self.query_one("#add_quick", Input).value = ""
            self.query_one("#add_note", Input).value = ""
            self.query_one("#add_error", Static).update("")
        elif event.button.id == "add_close":
            self._hide_add_panel()
        elif event.button.id == "edit":
            self.action_edit_interval()
        elif event.button.id == "delete":
            self.action_delete_interval()
        elif event.button.id == "save_all":
            self._save_all()
        elif event.button.id == "copy_day":
            self._clipboard = [
                Interval(
                    day=self.selected_day,
                    start=i.start,
                    end=i.end,
                    kind=IntervalKind.WORK,
                    location=i.location,
                    note=i.note,
                )
                for i in self.intervals
            ]
            self.notify("Copied day", timeout=1.0)
        elif event.button.id == "paste_day":
            if not self._clipboard:
                self.notify("Clipboard empty", timeout=1.0)
                return
            self.intervals = [
                Interval(
                    day=self.selected_day,
                    start=i.start,
                    end=i.end,
                    kind=IntervalKind.WORK,
                    location=i.location,
                    note=i.note,
                )
                for i in self._clipboard
            ]
            self._render()
            self.notify("Pasted day (not saved yet)", timeout=1.0)
        elif event.button.id == "export_md":
            y_raw = self.query_one("#export_year", Input).value.strip()
            out_raw = self.query_one("#export_path", Input).value.strip()
            try:
                y = int(y_raw, 10)
                if y < 1900 or y > 2200:
                    raise ValueError
            except ValueError:
                self.notify("Export year must be YYYY (e.g. 2026)", timeout=2.0)
                return
            if not out_raw:
                self.notify("Set an output path", timeout=2.0)
                return
            out = Path(out_raw).expanduser()
            try:
                write_year_markdown(self._cfg, y, out)
            except OSError as e:
                self.notify(f"Export failed: {e}", timeout=3.0)
                return
            except ValueError as e:
                self.notify(f"Export failed: {e}", timeout=3.0)
                return
            self.notify(f"Wrote {out}", timeout=2.0)
