# AGENTS.md

## Overview

Personal working-time tracker: log daily intervals to CSV, review hours in a Textual TUI, and export human-readable Markdown reports. Data lives in a CSV file (often synced with Obsidian); NRW public holidays and carry-over caps are applied in calculations.

## Purpose

Track work start/end, breaks, and location (home office, office sites, remote, business travel). The app answers:

- How many hours did I work vs. what was expected this month/year?
- What is my overtime balance after monthly/yearly caps?
- Did I meet the on-site rule (3 of 5 workdays off-site, scaled down for short weeks)?

## File structure

| Path | Role |
|---|---|
| `src/time_tracker/cli.py` | Typer CLI (`ui`, `report`, `export-md`, `log`) |
| `src/time_tracker/tui/` | Textual terminal UI |
| `src/time_tracker/csv_store.py` | CSV read/write |
| `src/time_tracker/calc.py` | Expected hours, monthly ledger, carry caps |
| `src/time_tracker/export_markdown.py` | Year/month/week Markdown export |
| `src/time_tracker/holidays_nrw.py` | NRW holiday cache via `holidays` |
| `src/time_tracker/config.py` | JSON config discovery and defaults |
| `tests/` | Pytest suite |
| `Taskfile.yml` | `task test`, `lint`, `fmt`, `cov`, `export`, … |
| `time-tracker.config` | Local config (paths, caps; not committed by default) |

## Domain notes

- **Expected hours:** `weekly_hours / 5` per weekday; 0 on weekends; full holidays 0; half-day holidays configurable via `half_day_holidays`.
- **Overtime ledger:** `carry_in + (worked - expected)` per month; capped by `month_carry_cap_hours`; year cap on January carry-in via `year_carry_cap_hours`.
- **On-site rule (export):** at least `floor(3 × workdays / 5)` days per week with logged work outside `homeoffice`. Weeks with no logged work are omitted from detail sections; on-site stats count only weeks with logged work.
- **Config discovery:** `TIME_TRACKER_CONFIG`, then `time-tracker.config`, `time-tracker.config.json`, XDG paths. Paths in config resolve relative to the config file directory.

## Python

### Style and scope

- Python **3.11+**, line length **100** (`ruff`).
- Match existing patterns: dataclasses, small modules, minimal abstraction.
- Prefer focused diffs; do not refactor unrelated code in the same change.
- Comments only for non-obvious business rules (holidays, caps, on-site scaling).

### Linting and formatting

- **Ruff** for lint and format (`task lint`, `task fmt`).
- CI/local quality gate: `task test` and `task lint` should pass before committing.
- Coverage target: **85%** on `time_tracker` (TUI omitted from coverage config).

### Tests

- Pytest under `tests/`; name files `test_*.py`.
- Add tests for real behaviour (calc edge cases, export layout, config loading)—not trivial one-liners.
- TUI: `tests/test_tui_e2e.py` for async Textual flows.

### Dependencies

- Runtime: `textual`, `typer`, `rich`, `holidays`.
- Dev: `pytest`, `pytest-cov`, `pytest-asyncio`, `ruff`.
- Install editable: `task install` or `uv pip install -e ".[dev]"`.

---

## Working on changes

### Atomic commits

- **One logical change per commit** — each commit should stand alone for review and `git bisect`.
- **Do not squash by default** — preserve distinct intents on a branch.
- **Squash selectively** — only when a later commit undoes or heavily rewrites an earlier commit on the **same concern**.
- **Fixups** — use `git commit --fixup=<target>` plus `git rebase -i --autosquash` to amend the immediately previous intent, not unrelated work.

### Boy Scout principle

When you touch an area, leave it slightly better (clearer naming, small fixes) without changing behaviour.

- **Scope:** Only in files or areas you touch for the current task.
- **Separate commit:** Put boy-scout improvements in their own commit (e.g. `refactor: clarify carry cap comment`). Do not mix into feature/fix commits unless trivial and agreed in review.

### Shipped repo vs agent docs

- `AGENTS.md` is for agent-oriented workflow and context; keep `README.md` user-facing and neutral.
- Do not add agent/Cursor-specific wording to user docs unless explicitly requested.

---

## Commit message guidelines

Follow [Conventional Commits](https://www.conventionalcommits.org/). **No ticket ID required.**

### Subject format

```
<type>[optional scope]: <short summary>

[optional body]
```

Optional gitmoji after the colon (inspired by [Gitmoji](https://gitmoji.dev/)):

```
feat(export): :sparkles: add week-by-week on-site bar
fix(calc): :bug: treat half-day holiday as scheduled workday
```

### Types

| Type | Use for |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no logic change |
| `refactor` | Restructure without behaviour change |
| `test` | Tests only |
| `chore` | Tooling, deps, config maintenance |

### Best practices

- Keep the subject under **72 characters** (aim for ~50).
- Use the body for **why**, not a repeat of **what**.
- Blank line between subject and body.

### Examples

```
feat(cli): add export-md year argument validation

fix(export): scale on-site requirement with floor for short weeks

test(calc): cover monthly carry cap at 60h

chore: bump ruff and fix import order
```

---

## Common commands

```bash
task install          # venv + editable install
task test             # pytest
task lint             # ruff check
task fmt              # ruff format
task cov              # pytest with coverage
task ui               # Textual TUI
task report MONTH=2026-05
task export YEAR=2026 OUT=exports/2026.md
time-tracker log 8-12 13-17 porz   # quick log today
```

Set `TIME_TRACKER_CONFIG=time-tracker.config` when the config file is not in the default search path.

---

## References

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Gitmoji](https://gitmoji.dev/)
- [Textual](https://textual.textualize.io/)
- [Typer](https://typer.tiangolo.com/)
- [Ruff](https://docs.astral.sh/ruff/)
