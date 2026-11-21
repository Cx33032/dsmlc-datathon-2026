# Predict the Break, Protect the Barrel
### Failure early warning and lost-oil attribution for heavy-oil PCP wells

**DSMLC Datathon 2026 · Chirality Research × Canary Labs · dataset: Strathcona Resources**

**Team:** _<name 1>, <name 2>, <name 3>, <name 4>_  
**Video (5 min):** _<link>_ · **Slides:** _<link>_

---

## Research questions

1. **Where is oil being lost, and how much of it is avoidable?** Attribute every downtime day
   across 2,240 producing wells (2021 to Oct 2026) to a cause, and value it.
2. **Can we flag the wells that will fail in the next 14 days early enough to act?** Measure how
   many failures a daily 25-well watchlist catches on held-out 2025-26 data, and how many days of
   warning it gives.

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

## Solution

1. **Operator dashboard** (Streamlit, `app/dashboard.py`) with six tabs: Overview, Where oil is
   lost (loss Pareto, bad actors, failure frequency), Risk watchlist with SHAP reasons, Well
   drill-down, Model & value (with a value calculator), and Data quality.
2. **Canary Historian integration** (`canary/`). It exports about 25k tags, including model risk,
   watch/alarm level and estimated lost oil, with Canary quality codes. Carried-forward manual
   readings are marked *Uncertain*. A replay mode streams days into the CSV Collector for a live
   demo. See [canary/README.md](canary/README.md) for the tag model, the Views asset tree and the
   Axiom screens.

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
# put the three competition .parquet files in the repo root (not committed), or set DATA_DIR
.venv/Scripts/python.exe make_data_summary.py      # -> DATA_SUMMARY.md
.venv/Scripts/python.exe run_pipeline.py           # -> outputs/ (about 30 s)
.venv/Scripts/streamlit.exe run app/dashboard.py   # dashboard at http://localhost:8501
.venv/Scripts/python.exe canary/export_to_canary.py  # -> outputs/canary/*.csv for the CSV Collector
```

```
src/config.py          paths, split dates, netback assumption
src/data.py            loading, cleaning, downtime categories, failure events
src/features.py        past-only features + 14-day label
src/losses.py          lost-oil estimate, loss tables, per-event impact
src/model.py           LightGBM training, top-K evaluation, baselines, SHAP
run_pipeline.py        end-to-end run -> outputs/
make_data_summary.py   reproducible data profile -> DATA_SUMMARY.md
app/dashboard.py       Streamlit operator dashboard
canary/                Canary CSV Collector export, config and setup guide
```

## External resources

- Canary Labs, *How to Configure the CSV Collector (v26)*, help center article (collector config keys and quality codes)
- PetroWiki: progressing cavity pumps; Dataset Handbook terms (PCP, rod string, water cut)
- Libraries: pandas, pyarrow, LightGBM, scikit-learn, Streamlit, Plotly

## AI disclosure

This project was built with help from **Claude (Anthropic) via Claude Code**, which wrote most of
the code, the data profile, the dashboard and the documentation, working from the team's
direction. The team reviewed the methods and the numbers, and is responsible for every claim.
Specific checks: the time-split design, the label check against the failure log, and the lost-oil
check against reported values.

## Data

The competition dataset belongs to Strathcona Resources and is **not** included in this repository
(see `.gitignore`), in line with the competition terms. `outputs/` holds derived data and is also
excluded.
