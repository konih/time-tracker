# Time Tracker (CSV + Textual TUI)

Track daily work start/end, break start/end, and location (homeoffice/remote/office/Porz/Karlswerk/Kiel/business travel) in a **CSV file**, with a **clickable** terminal UI.

## Features (current)

- Add/edit **1–3 work intervals per day** (and explicit break intervals)
- Persist to CSV (human-readable, scriptable)
- Monthly totals: hours worked, expected hours (37.5h/week baseline), overtime and carry-over
- NRW (Germany) public holidays via [`holidays`](https://pypi.org/project/holidays/), cached per year
- Configurable half-day public holidays

## Roadmap (already accounted for in design)

- PTO / half days off
- Überstundenabbau (overtime reduction days/half-days)
- Year carry-over cap (25h)

## Quick start

### System prereqs (Ubuntu)

To run this project with a local virtualenv, install venv support:

```bash
sudo apt update
sudo apt install -y python3-venv
```

### Install (recommended: `uv`)

```bash
cd time-tracker
uv venv
uv pip install -e ".[dev]"
```

If you don't use `uv`, a normal venv + pip works too:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

### Run the UI

```bash
time-tracker ui
```

### Monthly report

```bash
time-tracker report 2026-05
```

## Data format

CSV default path: `data/time_log.csv`

One row per interval:

```csv
date,start,end,kind,location,note
2026-05-08,09:10,12:10,work,homeoffice,Onboarding
2026-05-08,12:10,12:40,break,homeoffice,lunch
2026-05-08,12:40,17:35,work,homeoffice,Onboarding
```

## Tasks

This repo includes a `Taskfile.yml` (works with `go-task`).

```bash
task test
task lint
task fmt
task cov
```

