# Handoff: UI polish of the Canary dashboard

Branch `ui-polish-handoff` = branch `ui-polish` plus this file.
Work stopped on request partway through Step 6 (fix and re-test) of the UI polish brief.
The goal of the brief: a first-time user can say, within 10 seconds of opening any page, what the page is for, what the main finding is, and what to do next.
Data, models and analysis results must not change.

## Commits on this branch (after `main`)

1. `625576f` Add uv project file and a launch entry for the full app.
   `pyproject.toml` and `uv.lock` hold the same pinned packages as `requirements.txt` (the user asked for uv).
   `.claude/launch.json` gets an `app` entry (port 8502) that runs `app/app.py`; the old `dashboard` entry only runs the Field monitor page.
2. `a235ad0` Put each page's answer first and use one design system.
3. `aafeb9f` Fix clipped labels at 1280 px and primary button contrast in dark mode.

Files outside `app/**` and `docs/ui-audit.md` were changed only with the user's approval: `.claude/launch.json`, `.streamlit/config.toml` (theme primary colour), `pyproject.toml`, `uv.lock`, and this file.

## What changed

- `app/ui.py` is the only place for colours, chart style and page CSS.
  It adds `header()` (question title, answer slot, one closed "How to use this page" expander with steps and terms), `summary()`, `filters(reset_keys=...)` with a Reset button, `empty()`, and the `TERMS` glossary.
  `intro()` was removed after every caller moved to `header()`.
  `money()` now prints `C$`.
- Every page title is now the page's question, with a one-sentence answer and the main action under it.
- `app/dashboard.py` no longer has its own `style`, `show` or palette; it imports them from `ui`.
- Colour rule used across charts: blue = act on this or this app's method, grey = the rest or the baseline, red = loss, alarm or negative.
- Program page shows extra cost and savings next to net value.
  Both are the two terms of the existing `well_net` formula (net = avoided x failure cost - extra string cost), so no new model numbers.
- Evidence page states where the numbers come from (from `docs/Dataset_Handbook.md`).

The audit is in `docs/ui-audit.md` (14 problems, ranked by user impact).

## Checks done so far (all on private data, `outputs/`)

- No Python traceback and no browser console error on any of the 7 pages, at 1280, 1440 and 1920 px.
- Text contrast passes WCAG AA on every page in light mode at 1280, 1440 and 1920 px, and in dark mode at 1440 px.
  Checked with a custom script, not axe-core (the auto-mode classifier blocked injecting the downloaded axe script).
- No clipped or truncated metric, label, button or tab text at 1280 or 1920 px after the last commit.
- Keyboard: every control reached by Tab shows a visible focus ring and has a name.

## Open items, in order

1. Keyboard reach of segmented controls.
   Tab does not reach the unselected options of `st.segmented_control` on four pages: queue ("Add what happened next (replay)"), well card ("All wells"), evidence ("recorded loss"), assumptions (the four decision options).
   Check whether arrow keys move between options (standard radio-group behaviour).
   If they do not, replace those controls with `st.radio(horizontal=True)` or `st.pills`.
2. Five click tasks from the brief, done by hand in the browser, each in 3 clicks or fewer: first well to act on, why a well ranks high, which facility to restart first, what the program costs and saves, where the numbers come from.
   The page content now answers each one at the top, but the clicks were not repeated after the fixes.
3. Run the web-design-guidelines review (fetch `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`) on every changed file in `app/`.
4. Number check: run `uv run python build_artifacts.py --data-dir data --out-dir outputs` and `uv run pytest`, then compare.
   Before the changes: build exit 0, `[build] recommendations: 1009 wells, 1373 chronic tickets`, pytest 29 passed and 1 xfailed.
   The UI changes do not touch `src/`, `data/` or `build_artifacts.py`, so the outputs should match; this is not yet confirmed.
5. Dark mode at 1280 and 1920 px was not checked (only 1440).
6. Synthetic demo mode (`?demo=1`) was not opened after the changes.
7. Field monitor still uses bbl while other pages use m³.
   Units were left as they are, because converting would change the displayed numbers; both terms are in the glossary.

## Wording left unchanged or unverified

- "WCS" is not spelled out: the project docs never expand it, so the brief's rule (state only what the docs support) keeps it as is.
- "Healthy rate" on the queue is not defined: the docs do not say how the queue computes it.
- The 95% CI definition in `ui.TERMS` is a general statistics definition, not from the project docs.
- The app name "Predict the Break, Protect the Barrel" stays in the browser tab but was removed from the sidebar.

## How the checks were run

The check scripts live in the session scratchpad, not in the repo, and may be gone.
They drove headless Chrome over the DevTools protocol (Node 22+, no new dependency):

- `shoot.mjs <outdir> <width> <light|dark> [pages]`: waits until Streamlit stops running, takes a full-page screenshot, reports tracebacks, console errors, off-screen or ellipsis-truncated text, and runs `contrast.js`.
- `contrast.js`: for each visible text node, blends its colour and opacity over the nearest opaque background and compares the WCAG ratio with 4.5:1 (3:1 for large text).
  It skips slider min and max labels (hidden until hover) and the slider thumb value, which was checked by hand (4.73:1 light, 5.44:1 dark).
- `kbd.mjs [pages]`: presses Tab through each page and lists controls that Tab never reaches, have no visible focus ring, or have no name.

Page URLs: `/` (queue), `/facility`, `/well_card`, `/program`, `/dashboard`, `/evidence`, `/assumptions`.
