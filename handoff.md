# Handoff: UI polish of the Canary dashboard

Status: done and merged into `main`.
The goal of the brief: a first-time user can say, within 10 seconds of opening any page, what the page is for, what the main finding is, and what to do next.
Data, models and analysis results were not changed.

## What changed

- `app/ui.py` is the only place for colours, chart style and page CSS.
  It holds `header()` (question title, answer slot, one closed "How to use this page" expander with steps and terms), `summary()`, `filters(reset_keys=...)` with a Reset button, `empty()`, and the `TERMS` glossary.
  `money()` prints `C$`.
- Every page title is the page's question, with a one-sentence answer and the main action under it.
  Method and worked-out arithmetic sit in collapsed expanders below the answer.
- Colour rule used across charts: blue = act on this or this app's method, grey = the rest or the baseline, red = loss, alarm or negative.
- `.streamlit/config.toml` sets the theme primary colour to blue (red is kept for loss and alarm).
- Program page shows extra cost and savings next to net value (the two terms of the existing `well_net` formula).
- Facility page names the facility whose wells lost the most oil that a restart check could have recovered.
- Evidence page states where the numbers come from (from `docs/Dataset_Handbook.md`).
- Chart selections (queue, program, facility) also have a keyboard path: a select box or button next to the chart.
- Segmented controls use `required=True`, so one option always stays selected.
- Section headings are h2 under the h1 title.
- The audit is in `docs/ui-audit.md` (14 problems, ranked by user impact).

`main` was merged in before the merge back: its removal of the Field monitor page, its Evidence rewrite, the worked-out net value panels, the facility loss totals and cause chart are all kept.

## Checks (private data unless stated)

- No Python traceback and no browser console error on any of the 6 pages: light at 1280, 1440 and 1920 px, dark at 1280, 1440 and 1920 px, and synthetic demo mode at 1440 px.
- WCAG AA text contrast passes on every page in all of those runs (custom checker; axe-core injection was blocked by the auto-mode classifier).
- No clipped, off-screen or ellipsis-truncated labels at 1280 or 1920 px.
- Keyboard: every control Tab reaches shows a focus ring and has a name.
  Segmented-control options are one tab stop; arrow keys move between them and Space selects (checked by hand).
- The five click tasks each take 1 click or none: first well to act on, why a well ranks high, which facility to check first, what the program costs and saves, where the numbers come from.
- `build_artifacts.py` rebuilt into a separate folder: build exit 0, `recommendations: 1009 wells, 1373 chronic tickets` (same as before).
  All 17 parquet tables are identical to the pre-change build; 1,395 numbers in the JSON and CSV files agree to a relative 4.8e-13.
  `pytest`: 29 passed, 1 xfailed (same as before).

## Known issues not fixed (outside the allowed paths)

- `top_cause` in `ideas/1/chronic_wells.csv` can flip between runs on wells where two causes tie (for example 3 Corrosion vs 3 Fatigue).
  `data/ideas/1/rod_replace_analysis.py` uses DuckDB `mode()`, which breaks ties arbitrarily.
  A deterministic tie-break there would fix it.
- Filters are not kept in the URL, so a filtered view cannot be shared as a link (only the well card keeps `?uwi=`).

## Wording left unchanged or unverified

- "WCS" is not spelled out: the project docs never expand it.
- "Healthy rate" on the queue is not defined: the docs do not say how the queue computes it.
- The 95% CI definition is a general statistics definition, not from the project docs.
- Headings and buttons use sentence case, not Title Case: the humanizer rules ask for sentence case.
- Some copy from `main` uses "we" ("How we tested it"); it was kept.
