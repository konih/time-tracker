from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
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


def _today() -> date:
    return datetime.now().date()


def _parse_time(s: str) -> time:
    return datetime.strptime(s.strip(), "%H:%M").time()


def _fmt_time(t: time) -> str:
    return t.strftime("%H:%M")


def _quarter_hour_options() -> list[tuple[str, str]]:
    opts: list[tuple[str, str]] = []
    for h in range(24):
        for m in (0, 15, 30, 45):
            s = f"{h:02d}:{m:02d}"
            opts.append((s, s))
    return opts


class AddIntervalsScreen(ModalScreen[list[Interval] | None]):
    def __init__(self, day: date):
        super().__init__()
        self.day = day

    def compose(self) -> ComposeResult:
        yield Static("Add intervals", id="title")
        with Vertical(id="form"):
            yield Label(f"Date: {self.day.isoformat()}")
            yield Static("", id="error")
            yield Select(
                [(loc_opt.value, loc_opt.value) for loc_opt in WorkLocation],
                value=WorkLocation.HOMEOFFICE.value,
                id="location",
                prompt="Location",
            )
            yield Input(
                value="",
                id="quick",
                placeholder="Times (e.g. 8-12, 13-17 or 8:15 to 15,30)",
            )
            yield Input(value="", id="note", placeholder="Optional note (applies to all)")
            with Horizontal():
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Add", variant="primary", id="save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "save":
            try:
                loc = WorkLocation(self.query_one("#location", Select).value)
                raw = self.query_one("#quick", Input).value.strip()
                if not raw:
                    raise ValueError("Please enter at least one time range (e.g. 8-12, 13-17).")
                note = self.query_one("#note", Input).value.strip()
                ranges = parse_time_ranges(raw)
                intervals = [
                    Interval(
                        day=self.day,
                        start=start,
                        end=end,
                        kind=IntervalKind.WORK,
                        location=loc,
                        note=note,
                    )
                    for (start, end) in ranges
                ]
                self.dismiss(intervals)
            except ValueError as e:
                self.query_one("#error", Static).update(f"[b red]Error:[/b red] {e}")


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
                [(loc_opt.value, loc_opt.value) for loc_opt in WorkLocation],
                value=loc.value,
                id="location",
                prompt="Location",
            )
            yield Select(
                _quarter_hour_options(),
                value=_fmt_time(self.existing.start) if self.existing else "09:00",
                id="start",
                prompt="Start",
            )
            yield Select(
                _quarter_hour_options(),
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
    DataTable { height: 1fr; }
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit", "Quit"),
        ("a", "add_interval", "Add"),
        ("e", "edit_interval", "Edit"),
        ("d", "delete_interval", "Delete"),
    ]

    def __init__(self, store: CsvStore, config: AppConfig | None = None):
        super().__init__()
        self.store = store
        self._cfg = config if config is not None else AppConfig()
        self.selected_day: date = _today()
        self.intervals: list[Interval] = []
        self._clipboard: list[Interval] | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Label("Select day (YYYY-MM-DD)")
                yield Input(self.selected_day.isoformat(), id="day_input")
                with Horizontal():
                    yield Button("Load", id="load")
                    yield Button("Today", id="today")
                yield Label("Intervals (click row to select)")
                yield DataTable(id="table")
                with Horizontal():
                    yield Button("Add", id="add", variant="primary")
                    yield Button("Edit", id="edit")
                    yield Button("Delete", id="delete", variant="error")
                    yield Button("Save day", id="save_day")
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
                yield Label("Net worked today")
                yield Static("", id="net")
                yield Label("Month summary")
                yield Static("", id="month_summary")
                yield Label("Tips")
                yield Static(
                    "Keys a/e/d or buttons. Enter in the date field loads that day.",
                    id="tips",
                )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("Start", "End", "Location", "Note")
        self._load_day(self.selected_day)

    def _load_day(self, day: date) -> None:
        self.selected_day = day
        all_items = self.store.load_all()
        self.intervals = [i for i in all_items if i.day == day]
        self._render()

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
        self.query_one("#net", Static).update(self._net_string())
        self.query_one("#month_summary", Static).update(self._month_summary_string())

    def _month_summary_string(self) -> str:
        cfg = self._cfg
        holidays = NRWHolidayService(cache_dir=cfg.cache_dir, half_day_dates=cfg.half_day_holidays)
        calc = Calculator(cfg, holidays)

        all_items = self.store.load_all()
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

    def _net_minutes(self) -> int:
        mins = 0
        for it in self.intervals:
            mins += it.minutes()
        return mins

    def _net_string(self) -> str:
        mins = self._net_minutes()
        sign = "-" if mins < 0 else ""
        mins = abs(mins)
        return f"{sign}{mins // 60:02d}:{mins % 60:02d} (hh:mm)"

    def _selected_row_index(self) -> int | None:
        table = self.query_one("#table", DataTable)
        if table.cursor_row is None:
            return None
        if table.row_count == 0:
            return None
        return table.cursor_row

    def action_add_interval(self) -> None:
        def _on_dismissed(result: list[Interval] | None) -> None:
            if not result:
                return
            self.intervals.extend(result)
            self._render()

        self.push_screen(AddIntervalsScreen(self.selected_day), _on_dismissed)

    def action_edit_interval(self) -> None:
        idx = self._selected_row_index()
        if idx is None:
            return

        existing = self.intervals[idx]

        def _on_dismissed(result: Interval | None) -> None:
            if result is None:
                return
            self.intervals[idx] = result
            self._render()

        self.push_screen(EditIntervalScreen(self.selected_day, existing=existing), _on_dismissed)

    def action_delete_interval(self) -> None:
        idx = self._selected_row_index()
        if idx is None:
            return
        self.intervals.pop(idx)
        self._render()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "day_input":
            return
        raw = event.input.value.strip()
        try:
            self._load_day(datetime.strptime(raw, "%Y-%m-%d").date())
        except ValueError:
            self.notify("Invalid date (use YYYY-MM-DD)", timeout=2.0)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "today":
            self._load_day(_today())
        elif event.button.id == "load":
            value = self.query_one("#day_input", Input).value.strip()
            self._load_day(datetime.strptime(value, "%Y-%m-%d").date())
        elif event.button.id == "add":
            self.action_add_interval()
        elif event.button.id == "edit":
            self.action_edit_interval()
        elif event.button.id == "delete":
            self.action_delete_interval()
        elif event.button.id == "save_day":
            self.store.upsert_day(self.selected_day, self.intervals)
            self.notify("Saved", timeout=1.0)
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
