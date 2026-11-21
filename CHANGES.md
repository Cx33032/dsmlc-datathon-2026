# Changes: one platform, three decisions

Branch `feature/three-horizons`. Run `python build_artifacts.py --data-dir <folder with the parquets>`, then
`streamlit run app/app.py`.

## What was added

| Horizon | Page | Question it answers | Source |
|---|---|---|---|
| Today | **Today's queue** | Which newly reported equipment outage do we review first? Chronic rod wells carry a CHRONIC badge, their rod-repair count and the at-the-pull recommendation, and link to their Well Card. Decision mode hides outcomes; replay mode shows them, labelled retrospective | Dispatch (rebuilt from spec) + decision rule |
| Today | **Facility restarts** (new idea) | When a battery trips, which wells are still down after their peers came back? The queue also shows a live "restart check needed" box | `src/facility.py` |
| At the pull | **Well card** | For this well: full string, section band, corrosion remedy, each with its evidence count; rod-job timeline; break-depth strip; crew quotes (private only); per-well economics at the slider price; 90-day oil/RPM/torque | Ideas 1 + 5, `src/rules.py` |
| At the pull | **Replacement program** | Which chronic wells get a new string, and does it survive pessimism? Sliders for price, HR, cost ×1/×2, horizon, lost oil; sensitivity table; the worst-14 first wave | Idea 1 |
| Between failures | **Field monitor** | The existing lost-oil and 14-day early-warning dashboard, now reading the shared price and mode | unchanged analysis |
| Proof | **Evidence** | Dispatch replay vs oracle at K = 1/2/3/5, Cox tables, KM curve, chart 1b, repeat-depth permutation (5b), narrative vs coded cause (5c), the Whiplash result, traps we avoided | all |
| Proof | **Assumptions & limits** | Observational HR (pilot: randomise 70 of 145), 45% depth coverage, 40% section saving, 15% haircut, revenue not margin, posting lag, daily granularity | all |

Also:
- **One central price.** WCS Hardisty (WTI 83.45 − 26.20 USD) × 1.4325, less a 15% field-gate haircut, gives C$69.71/bbl (C$438.5/m³). It drives every $ figure on every page through the sidebar slider. The monitor's old C$50/bbl default is gone, so its $ tiles read higher at the default price.
- **Synthetic demo mode** (`src/demo.py`). The sidebar toggle defaults to ON when no private artifacts exist. A clean clone builds the demo artifacts on first launch (about 30 s). Demo data has fake wells, areas, outages, rod jobs, located breaks, facility trips and crew-style notes, with the same schemas.
- **Precomputed artifacts only** (`build_artifacts.py`). The app never reads the raw parquets.
- **Pinned requirements**, `pytest.ini`, and 30 tests.

## Verification (pytest: 29 passed, 1 expected fail)

| Check | Source result | App default | Status |
|---|---|---|---|
| Idea 1 program | 145 wells, 678 repairs | 145, 678 | ✅ |
| Cox new-string HR | 0.485 (0.422–0.559); chronic 0.495 | 0.485 (0.422–0.559); 0.495 | ✅ |
| Break-even | ≈1.0 failure/yr | 1.00 | ✅ |
| Program net, 2 yr | $7.43M; $5.89M at upper CI | $7.43M; $5.89M | ✅ |
| Worst-case first wave | 14 wells | 14 | ✅ |
| Idea 5 | 983 located; 48.6% vs 16.7%; 54 wells ≤150 m | 983; 48.6% vs 16.7%; 54 | ✅ (decision rule also gives exactly 54 section bands among the 145) |
| Dispatch K=2, exposure | 52.7% vs 43.9% | **52.0% vs 42.7%** | ⚠️ margin 9.3 vs 8.8 pts matches; levels 0.7–1.2 pts lower |
| Dispatch K=2, recorded loss | 50.6% vs 48.8% | **48.4% vs 46.6%** | ⚠️ margin 1.8 vs 1.8 pts matches; levels 2.2 pts lower |

**Why Dispatch differs:** the original Dispatch code is not in this repo or on this machine, so the queue was rebuilt from the brief's spec. Details the spec leaves open include:
- what counts as a "newly reported equipment outage" (here: downtime on D, none on D−1, downhole or surface-equipment cause);
- the healthy-rate window (here: 30-day mean of ≥22 h days, up to D−1);
- the reason field (here: `downtime_code_1`).

The expected values were not changed. The level test is marked `xfail` with that reason, and a separate test checks the margins.

**Leakage tests:**
- Dispatch decision features don't change when every row after day D is scrambled, and the model is fitted on training rows only.
- The Shock Index on day D is unchanged when rows from D onward are altered.
- The Whiplash hazard window ends 7 days before the failure, and the Cox covariate is lagged the same way.
- Cox prior history counts only repairs strictly before the job.

**Decision-rule unit tests** cover 0 and 1 located breaks, a band of exactly 150 m vs 150.5 m, NaN depths, mixed causes, a recent new string, and the as-of cutoff.

**Click-through:** every page loads with no exceptions in both private and demo mode.

## Whiplash verdict: tested and rejected

The expected direction (higher shock in the 30 days ending 7 days before a rod failure) and the keep rule were written into the script before the first run.

- **Case-crossover** (1,788 rod failures on 553 wells, Jun 2025 on, 3 controls each):
  - OR 1.09 per SD (1.02–1.17), p = 0.013; sign-flip permutation p = 0.025.
  - But hazard windows were higher in only 50.6% of failures (Wilcoxon p = 0.51): a few tails, not a shift.
- **Cox (Idea 1 spec, 6,413 rod jobs):**
  - Shock Index HR 0.98 per SD (0.95–1.01).
  - The new-string HR barely moves: 0.466 → 0.467.
- **Contrast:** within a well, RPM level was higher before failures (OR 1.26 per 100 rpm, p = 0.002), but Idea 1 found no adjusted RPM effect across wells (HR 0.97).
- **Conclusion:** it fails the keep rule, so the index stays out of every ranking and appears under Evidence as a rejected idea. The likely reason is the data: RPM, torque and current are manual readings that repeat most days, so daily changes are rare and can't see seconds-long shocks.
- **Coverage:** the index exists on 61% of producing well-days. Fenn Big Valley, CHO-Non-Op and several small areas have none, and pump current is under 10% in most areas outside Court, Druid and Winter.

## Facility restarts (new)

The definitions were fixed in the code before the first run and not tuned afterwards:
- **Sync day:** ≥5 wells and ≥25% of the facility's running wells go down the same day.
- **Incident:** sync days ≤3 days apart are merged.
- **Laggard:** back ≥3 days after 75% of affected peers.

| | Brief | This build |
|---|---|---|
| Synchronized outage days | 83 | 82 |
| Facilities | 10 | 14 |
| Lost oil on onset days | 15,708 m³ | 14,524 m³ |
| Laggard well-outage cases | 98 | 73 (71 wells) |
| Oil lost while lagging | n/a | 2,377 m³ ≈ C$1.04M at the default price |

The counts differ because the brief's exact definitions weren't available.

## Open risks

1. **Real data is already public on GitHub.** `data/ideas/1/out/chronic_wells.csv` (well IDs) and `data/ideas/5/out/located_breaks.csv` (verbatim crew text) were committed on `main` in 2cdfede, along with copies of the competition documents. The new code no longer needs those `out/` folders, and they are now gitignored, but they are still tracked and in history. **Team decision:** remove them, and consider making the repo private until it's cleaned.
2. **Dispatch is a reconstruction.** Swap in the original code if it turns up; the page reads only `dispatch_tickets.parquet` and `dispatch_replay.csv`.
3. **The section-band rule needs ALL located breaks within 150 m.** That matches Idea 5's "54 wells" metric. A looser cluster rule would flag more wells.
4. **The depth parser** has only a 15-row spot check. Hand-label 100 rows before pitching depth bands as reliable.
5. **The demo data has built-in effects** (new string, weak depth zone, facility trips) so the pages have something to show. Its numbers are not results.

## Slide-ready figures (private data, default price C$69.71/bbl)

- **Program:** 145 chronic wells, 678 rod repairs last year, C$8.97M all-in.
- **New string:** HR 0.49 (0.42–0.58); break-even 1.0 failure/yr.
- **Value:** C$7.43M net over 2 yr (C$5.89M at the pessimistic CI). 14 wells pay back even when every pessimistic case is stacked.
- **Break depths:** 983 rod breaks located from crew text. Same-well breaks repeat within 50 m 48.6% of the time vs 16.7% by chance (2.9×, p = 0.001). 54 program wells break inside one ≤150 m band.
- **Dispatch:** reviewing the top 2 outages a day captures 52% of next-3-day exposure vs 43% when ranking by day-1 loss.
- **Facility restarts:** 76 incidents, 73 restart laggards, 2,377 m³ lost while lagging.
- **Whiplash:** daily volatility does not predict rod failures once history is controlled for (HR 0.98).
- **Screenshots:** `docs/screenshots/` (synthetic, safe to publish); private shots in `outputs/screenshots/` (gitignored).
