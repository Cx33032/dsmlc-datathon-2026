# Plan: merge the ideas into the app

Written after the Step 0 reconnaissance, on branch `feature/three-horizons` (git worktree `../dsmlc_merge`). The
running instance on port 8501 serves the `main` checkout and is not touched.

## What the reconnaissance found (and where it contradicts the brief)

| Brief says | Repo actually has | What we do |
|---|---|---|
| A "Dispatch by the Barrel" app runs on 8501 (DuckDB over three parquets) | 8501 runs our **Well Reliability & Loss Monitor** (`app/dashboard.py`: lost oil, 14-day failure early warning). No Dispatch code anywhere on disk | Rebuild the Dispatch queue from the written spec (`src/dispatch.py`), keep the monitor as a page, report the reproduction gap honestly |
| Parquets live in `data/` | They sit in the repo root; `data/ideas/common.py` pointed at `data/` | `common.py` now honours `DATA_DIR`, falling back to `data/` then the repo root |
| Idea outputs in `data/ideas/N/out/` | Present, but committed: `chronic_wells.csv` (well IDs) and `located_breaks.csv` (crew text) | Scripts now write to a private `<out-dir>/ideas/` via `IDEAS_OUT`; the old `out/` folders are flagged for removal (team decision) |
| HR 0.485 drives the program | Program value uses the **chronic-well** HR 0.495; 0.485 is the all-jobs HR | Both shown; tests check both |
| Idea 1 top-cause counts 50 / 74 | DuckDB `mode()` breaks ties arbitrarily: a rerun gives 48 / 76 | Documented; headline numbers do not depend on it |

## Files

- `src/config.py`: one central price (WCS-based C$69.71/bbl = C$438.5/m³), 6.28981 bbl/m³, unit-cost assumptions, Dispatch split
- `src/dispatch.py` (new): ticket build, shrunk reason × hours-bin estimate, replay vs first-day-loss and oracle
- `src/facility.py` (new): synchronized facility outages → incidents → restart laggards
- `src/rules.py` (new): the at-the-pull decision rule + leakage-safe evidence builder
- `src/economics.py` (new): replace-vs-repair economics recomputed from the price slider
- `src/shock.py` (new): Mechanical Shock Index (past-only)
- `src/demo.py` (new): synthetic data with the same schemas
- `data/ideas/whiplash/shock_index.py` (new), small additions to Ideas 1 and 5 (machine-readable artifacts)
- `build_artifacts.py` (new), `run_pipeline.py` (dispatch + facility steps, pump tags in the slim table)
- `app/app.py` (new entry, `st.navigation`), `app/ui.py`, `app/views/*.py`; `app/dashboard.py` becomes the "Field monitor" page
- `tests/`: decision rule, leakage, reproduction

## Artifacts (`outputs/` private, `outputs_demo/` synthetic; both gitignored)

`dispatch_tickets.parquet`, `dispatch_replay.csv`, `facility_*.parquet`, `recommendations.parquet`,
`ideas/1/{rod_events.parquet, chronic_wells.csv, cox_*.csv, km_chronic.csv, rate_by_history.csv, sensitivity.csv, economics.json}`,
`ideas/5/{located_breaks.csv, metrics.json, perm_share.csv, keywords_by_cause.csv, ...}`,
`ideas/whiplash/{verdict.json, results_table.csv, case_crossover_pairs.csv, perm_null.csv, well_shock.parquet}`,
plus the existing monitor outputs.
