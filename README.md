# Predict the Break, Protect the Barrel
### Failure early warning and lost-oil attribution for heavy-oil PCP wells

**DSMLC Datathon 2026 · Chirality Research × Canary Labs · dataset: Strathcona Resources**

**Team:** _<name 1>, <name 2>, <name 3>, <name 4>_  
**Video (5 min):** _<link>_ · **Slides:** _<link>_

---

## Research questions

One platform, three decisions on three time horizons, each feeding the next:

1. **Today: which outage do we look at first?** Rank newly reported equipment outages by the oil they will lose
   over the next 3 days. When a whole battery trips, flag the wells that stay down after their peers restart.
2. **At the pull: what do we do once the crew is there?** On a chronic rod well: a full new string, a section at
   a known depth, and/or inhibitor plus a corrosion-resistant grade.
3. **Between failures: which wells are heading for trouble?** The 14-day failure early-warning model and lost-oil
   attribution, plus a test of whether volatile operation ("mechanical whiplash") precedes rod failures.

## Motivation

Heavy-oil wells need a progressing-cavity pump driven through a rod string, and rods are the
part that fails most. Every failure brings an outage, a service job (median about $5.9k) and a
production decline in the days before it. Field oil output is
**12.7% lower over the last 12 months than the 12 before**, while water cut keeps rising (96.4% → 96.9%).
Avoidable downtime is a lever that doesn't need new wells.

## Summary of findings

| | |
|---|---|
| **Avoidable lost oil, 2021 to Oct 2026** | **2.69 M bbl** (428k m³), about 485k bbl/yr; ≈ $24M/yr at an assumed $50/bbl netback |
| **Share from equipment failures** (rods, pump, tubing) | **45%** (1.21 M bbl). Rods alone are the #1 cause at 27% |
| **Failure events** | 10,408 repair events on producers; **Winter** has the highest failure rate (≈5.4 per running well-year, vs ≈2 for the next areas) |
| **Hidden loss** | Oil already drops in the 1-2 weeks *before* a failure (median 4.5 m³ per event), on top of the outage itself (median 6.4 m³). The reported lost oil doesn't count this |
| **Early-warning model, test 2025-26** | Of the 25 wells on each day's watchlist, **29% start a failure outage within 14 days**, 4.8× the 6% base rate |
| | Catches **25% of 3,258 failures** with a **median 8 days' warning**, at about **3.3 new alerts per day** |
| | **37 failures caught per 100 alerts**, vs 5 for a random list. A failure-history rule is about as precise per alert but catches only half as many failures (12%) |
| **Conservative value** | About 18k bbl/yr protected, **≈ $0.55M/yr net** of inspection costs. This assumes 30% of outage loss and 25% of pre-failure decline avoided per caught failure, $50/bbl and $300 per check. It excludes repair-cost savings. Every assumption is adjustable in the dashboard |
| **Data quality** | Pressure, torque, motor-current and RPM tags repeat the previous day's value 95-98% of the time (carried-forward manual readings). We recommend automating them; today they add little early warning |
| **Today: outage queue** (2026 holdout) | Reviewing the top 2 new outages a day captures **52%** of next-3-day oil exposure vs **43%** when ranking by day-1 reported loss (oracle 62%) |
| **Today: facility restarts** | 82 synchronized outage days at 14 facilities (76 incidents). **73 wells stayed down 3+ days after 75% of their peers restarted**, losing about 2,400 m³ while they lagged |
| **At the pull: new string** | 145 chronic wells (≥3 rod repairs in a year) cost C$8.97M all-in last year. A new string halves the hazard of the next repair (Cox **HR 0.49**, 0.42-0.58); break-even is about 1 failure/yr. **C$7.43M net over 2 years** (C$5.89M at the pessimistic CI); 14 wells pay back even when every pessimistic case is stacked |
| **At the pull: where it breaks** | 983 rod breaks located from crew text (45%). Same-well breaks repeat within 50 m **48.6%** of the time vs 16.7% by chance (2.9×, p = 0.001); 54 program wells break inside one ≤150 m band |
| **Between failures: whiplash** (tested, rejected) | Day-to-day volatility in RPM, torque, current and run hours does not predict rod failures once history is controlled for (Cox HR 0.98 per SD, 0.95-1.01). The case-crossover edge (OR 1.09) comes from a few tails. Daily manual readings can't see real shocks |

## Solution

A Streamlit app (`app/app.py`) with one page per decision. It reads only precomputed artifacts.

| Page | Answers |
|---|---|
| **Today's queue** | Which new outage to review first. Chronic rod wells show their at-the-pull recommendation and link to the Well Card. Decision mode hides outcomes; replay mode shows them, labelled retrospective |
| **Facility restarts** | Synchronized outages grouped into facility incidents; wells still down 3+ days after 75% of peers are back |
| **Well card** | For one well: the recommendation with its evidence counts, rod-job timeline, break-depth strip, crew notes (private mode only), per-well economics, 90-day trends |
| **Replacement program** | The 145 chronic wells, the break-even chart with sliders, the sensitivity table, and the worst-14 first wave |
| **Field monitor** | Lost oil by cause and the 14-day failure early-warning watchlist |
| **Evidence** | Dispatch replay vs oracle, Cox and Kaplan-Meier, the repeat-depth permutation, crew text vs coded cause, the Whiplash test, the traps we avoided |
| **Assumptions & limits** | What to doubt, and how we would check it |

There is one oil-price slider (default WCS Hardisty less a 15% field-gate haircut = C$69.7/bbl), and every $
figure recomputes from it. The same decision rule (`src/rules.py`) feeds the queue and the Well Card.

**Canary Historian integration** (`canary/`) exports about 25k tags, including model risk, watch/alarm level and
estimated lost oil, with Canary quality codes. See [canary/README.md](canary/README.md).

## Methods

**Cleaning** (`src/data.py`): implausible values are set to NaN (999,999 kPa placeholders, negative
volumes, pump efficiency > 300%, etc.), 27 duplicate well-days are removed, and 32 pump-make
spellings are normalised to 8. The 137 raw downtime codes are grouped into 14 cause categories by
keyword rules. Details: [DATA_SUMMARY.md](DATA_SUMMARY.md).

**Failure events.** The failure log only covers 2025-26, so a failure event is defined as a
rod/pump/tubing *repair job*, which gives one consistent definition across all six years. Jobs on
the same well within 7 days are merged. Outage onset is the first non-running day before the job.
*Check against the failure log:* 91% of logged failures match a repair event within ±14 days.

**Lost oil (topic 2)** (`src/losses.py`): per downtime day, lost oil = the well's trailing 30-day
median oil rate (fully running days, past only) × hours down / 24. *Check:* this matches the
operator-reported lost oil on 233k downtime days (totals within 1%, Spearman 0.94). Economic
long-term shut-ins are counted separately because they're a business decision, not avoidable loss.

**Early-warning model (topic 1)** (`src/features.py`, `src/model.py`): one row per running well-day.
Label = a failure outage starts in the next 1-14 days. There are 34 features, all computed from past
data only: oil, fluid and water-cut trends against the well's own baseline, pump-efficiency
change, fluid vs rated pump volume (displacement × RPM / 100), downtime history, failure history
(count in the last year, days since, last component), pump make, area and well age. The model is
LightGBM with a **strict time split**: train Apr 2021 to 2023, choose the tree count on 2024, refit
on everything before 2025, test on 2025 to Oct 2026. Thresholds: *watch* = top 5% and *alarm* =
top 2% of 2024 validation scores. Explanations use LightGBM's native TreeSHAP.

**Why these metrics:** a field team can visit a fixed number of wells a day, so we report
precision of the daily top-K list, the share of failures flagged ahead of time, the warning time,
and the alert workload (new wells entering the list per day). A random list "catches" many
failures only because it flags about 7× more wells.

## Limitations and next steps

- **History dominates the score.** The most important features are failure history and pump
  setup, and production trends add a smaller lift. With hourly torque and current from automated
  tags, decline-based detection should improve, which is the data-quality recommendation.
- **The label is a proxy.** 67% of 2025-26 repair events appear in the failure log, which is less
  complete than the job records.
- **Value depends on assumptions.** The value case relies on assumed avoidable shares and netback,
  so we show it as a calculator, not a promise. A pilot on one area (e.g. Winter) would measure the
  real reduction.
- **Raw rate comparisons are confounded.** Pump-make and area failure rates aren't controlled for
  depth, fluid or well age. Next step: survival analysis (Cox model) of run-life by
  pump/rod configuration.
- **The model isn't retrained over time.** It's trained once on data up to 2024. In production it
  would be retrained monthly from Canary through Historian ODBC.

## How to run

```powershell
uv venv --python 3.12 .venv; uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

**From a clean clone (synthetic demo data, no competition data needed):**

```powershell
.venv/Scripts/streamlit.exe run app/app.py
```

The first launch generates fake wells, outages, rod jobs and crew-style notes with the competition schemas and
builds the demo artifacts (about 30 s). You can also build them yourself with
`python build_artifacts.py --demo`.

**With the competition data (private mode):**

```powershell
.venv/Scripts/python.exe build_artifacts.py --data-dir <folder with the 3 parquets> --out-dir outputs
.venv/Scripts/streamlit.exe run app/app.py
.venv/Scripts/python.exe -m pytest
```

`build_artifacts.py` runs, in about 1.5 minutes:
- the pipeline (cleaning, lost oil, early-warning model, dispatch queue, facility restarts);
- Idea 1 (replace vs repair) and Idea 5 (break depths);
- the Whiplash test;
- the decision rule for every well and every queue ticket.

The tests check that the app's default numbers reproduce the source results, run the leakage checks, and cover the
decision rule's edge cases.

```
app/app.py, app/ui.py, app/views/   Streamlit pages; app/dashboard.py = Field monitor page
build_artifacts.py                  builds every artifact the app reads
src/dispatch.py                     outage queue + 2026 replay
src/facility.py                     facility incidents + restart laggards
src/rules.py                        at-the-pull decision rule (unit-tested)
src/economics.py                    replace-vs-repair economics at any price
src/shock.py                        Mechanical Shock Index (past-only)
src/demo.py                         synthetic data with the competition schemas
src/data.py, features.py, losses.py, model.py   cleaning, features, lost oil, early-warning model
data/ideas/1, 5, whiplash           replace-vs-repair, break-depth mining, whiplash test
tests/                              reproduction, leakage, decision rule
canary/                             Canary CSV Collector export, config and setup guide
```

## External resources

- Canary Labs, *How to Configure the CSV Collector (v26)*, help center article (collector config keys and quality codes)
- PetroWiki: progressing cavity pumps; Dataset Handbook terms (PCP, rod string, water cut)
- Price inputs (cited in `data/ideas/common.py`): WTI from OilPriceAPI (2026-11-19), the WCS Hardisty differential
  from CalRock via Reuters (2026-11-13), USD/CAD from the Bank of Canada (2026-11-20)
- Methods: Cox proportional hazards and Kaplan-Meier (statsmodels), case-crossover design with conditional
  logistic regression, permutation tests
- Libraries: pandas, pyarrow, DuckDB, LightGBM, scikit-learn, statsmodels, SciPy, Streamlit, Plotly

## AI disclosure

This project was built with help from **Claude (Anthropic) via Claude Code**, working from the team's direction.
Claude wrote most of:
- the pipeline, the data profile and the documentation;
- the merged Streamlit app, the dispatch and facility modules, the decision rule and the synthetic-data generator;
- the Whiplash test and the test suite.

Team members wrote the idea analyses in `data/ideas/` with AI assistance. The team reviewed the methods and the
numbers, and is responsible for every claim.

Specific checks:
- the time splits;
- the label check against the failure log and the lost-oil check against reported values;
- the reproduction tests;
- the leakage tests.

No crew text or well data was sent to any external AI service by the app. The optional text extraction is a
regex parser that runs locally.

## Data

The competition dataset belongs to Strathcona Resources and is **not** included in this repository (see
`.gitignore`), in line with the competition terms. `outputs/` holds derived private artifacts and is excluded.
Screenshots in `docs/screenshots/` come from the synthetic demo mode.
