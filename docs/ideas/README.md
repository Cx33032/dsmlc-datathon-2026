# Strathcona datathon: idea screening and recommendation

**Recommendation: build Idea 1, "Stop patching, start replacing", a rod-string replacement program for chronic-failure wells.**

The 145 wells currently failing 3 or more times a year should get a full new rod string at their next failure instead of another repair.
The adjusted hazard of the next rod repair falls by half (Cox HR 0.49, 95% CI 0.42-0.58).
The program is worth about $7.4M net over 2 years ($5.9M at the pessimistic confidence bound).

To stand out, present it as one story:
- **Decide** (Idea 1)
- **Target** with crew-narrative break depths (Idea 5): same-well breaks repeat within 50 m at 2.9x chance
- **Prove and monitor** with an nRF52832 fatigue odometer on a 3D-printed rig streaming into Canary (Idea 4).

## How to reproduce

Python 3.12 with pandas, pyarrow, duckdb, matplotlib, scikit-learn, lightgbm, statsmodels.
Run from the repository root:

```bash
python data/ideas/00_profiling/profile.py
```

```bash
python data/ideas/00_screening/screen.py
```

```bash
python data/ideas/1/rod_replace_analysis.py
```

```bash
python data/ideas/2/build_features.py
```

```bash
python data/ideas/2/train_eval.py
```

```bash
python data/ideas/3/deferral_analysis.py
```

```bash
python data/ideas/4/edge_gap_analysis.py
```

```bash
python data/ideas/4/fatigue_odometer.py
```

```bash
python data/ideas/1/rod_replace_analysis.py && python data/ideas/5/break_depth_mining.py
```

Idea 5 reads Idea 1's `chronic_wells.csv`, so run Idea 1 first.

- Shared paths, cleaning rules and the oil price assumption are in `data/ideas/common.py`.
- Each script writes its numbers to an `out/results.txt` next to it and its charts to `docs/ideas/N/assets/`.
- The whole set runs in about 3 minutes.
- Data-quality findings: [00_data_quality.md](00_data_quality.md).

## Comparison of developed ideas

| | [Idea 1: Rod-string replace vs repair](1/idea.md) | [Idea 2: 30-day failure watch-list](2/idea.md) | [Idea 3: Deferred-production command center](3/idea.md) |
|---|---|---|---|
| Solution form | Implementation plan + decision tool | AI/ML prototype | Analytical dashboard |
| Problem size | $250.1M all-in downhole failure cost 2021-26; 145 chronic wells cost $8.97M in the last year | 37,525 m3/yr downhole lost oil ($16.5M/yr) | 72,798 m3/yr recoverable deferral ($31.9M/yr) |
| Key evidence | Cox HR 0.485 (0.422-0.559); same direction in every prior-failure band | Test AUC 0.764 vs 0.716 for history rule; precision@50 0.387 vs 0.339 | 2 facilities = 59% of facility loss; 55% of downhole loss from episodes > 7 d |
| Impact (CAD) | **$7.43M net / 2 yr** (pessimistic $5.89M); positive under every single stress | about $1.2M/yr net, built on 3 unverified intervention assumptions | about $3.3M/yr (assumed 10-25% reductions) + $3.9M/yr gross 12-32 BTY debottleneck case |
| Weighted rubric (self) | **4.05** | 3.40 | 3.35 |
| Build risk by Sunday noon | Low: analysis done; only backtest and slides remain | Medium: model done; Canary integration is the risk | Low-medium: analysis done; dashboard build needed |
| Canary fit | Moderate (calc tag + event + Axiom list) | Strong (risk tag written back, events, watch-list) | Strongest (loss accounting, episode alarms, morning-call board) |
| Appeal to these judges | **High.** Strathcona analyst: uses their own job data, handles the cost and taxonomy artefacts. Vermilion ops EIT: a decision they make every week. Chirality BI: clean causal method. Cenovus: clear $ case. | Medium. Expected entry; ops judge will say "we already watch repeat failers", and the data shows that rule gets most of the way. | Medium. Ops and BI judges like it, but it looks like many other entries unless the 12-32 and data-trust findings lead. |

### Complementary ideas (added to strengthen Idea 1)

Idea 4 has a beginner [build guide](4/guide.md) with diagrams, a Canary explainer, printable STL files ([4/cad/](4/cad/)) and a four-person plan.

| | [Idea 4: Rod-string fatigue odometer (edge AI + rig + Canary)](4/idea.md) | [Idea 5: Where strings break (crew-narrative mining)](5/idea.md) |
|---|---|---|
| Solution form | AI/ML prototype on an nRF52832 + 3D-printed rig | Implementation plan, extending Idea 1's decision tool |
| Key evidence | Torque tag held a day-weighted median of 59 days. Pre-failure loss is 9.38 m3 of *rod-coded* downtime per failure, with no hidden under-production on running days, so the lever is planned pulls. Streaming rainflow equals batch exactly and uses 3.8% of RAM. | 983 rod breaks located from text (45%). Same-well breaks repeat within 50 m 48.6% of the time vs 16.7% by chance (2.9x, p = 0.001). 54 program wells break within a band of 150 m or less. |
| Impact (CAD) | about $1.0M one-off plus $4,113 per converted failure (assumptions; pilot needed) | about $0.30M (section replacement, 40% cost-cut assumption) + remedy targeting on 31 wells |
| Weighted rubric (self) | 3.90 | 3.95 |
| Build risk | **High** (hardware + firmware + BLE + Canary in about 20 h) | Low (done; hand-labelling remains) |
| Canary fit | Strongest of all five | Weak |
| Appeal to these judges | Ops EIT and Chirality BI: physical demo, real-time alarms. Strathcona: only if it is tied back to the data gap (chart 4a). Risk: "you would put an Arduino on a wellsite?" (answer in Idea 4 section h). | Strathcona analyst: someone read their crew text. Ops EIT: it says which joints to pull. |

### Weighted rubric detail

Weights: Research 25%, Technical 25%, Impact 20%, Presentation 15%, Creativity 15%.

| Idea | Research | Technical | Impact | Presentation | Creativity | Weighted |
|---|---|---|---|---|---|---|
| 1 | 4 | 4 | 5 | 4 | 3 | **4.05** |
| 2 | 3 | 4 | 3 | 4 | 3 | 3.40 |
| 3 | 3 | 3 | 4 | 5 | 2 | 3.35 |
| 4 | 4 | 4 | 2 | 5 | 5 | 3.90 |
| 5 | 4 | 4 | 3 | 4 | 5 | 3.95 |
| **1 + 5 + 4 as one story** | 5 | 4 | 5 | 5 | 5 | **4.75** (target if built; Technical stays 4 because Idea 4's classifier is still synthetic) |

## How to differentiate: one story, three layers

Rod repairs are an obvious topic, and many teams will find "some wells fail a lot".
The differentiators are depth (*why* and *where* they fail), a decision rule with money attached, and a physical, live demo of what the data is missing.

| Layer | Question | Idea | Demo moment |
|---|---|---|---|
| Decide | Which wells get a new string, and is it worth it? | 1 | Chart 1b + break-even: "replace at the next pull on any well failing 3 or more times a year" |
| Target | Where on the string, and which remedy? | 5 | Chart 5d: "the crews already wrote down where it breaks" |
| Prove and monitor | When has a string used up its life? | 4 | Live rig: brake on -> stick-slip alarm in Canary; pull the coupling -> parted-rod event; damage index climbing |

### Recommended tech stack

| Tier | Choice | Why |
|---|---|---|
| Analytics | The Python scripts here (DuckDB + pandas + statsmodels/LightGBM) | Already reproducible, so judges can rerun them |
| Backend | **FastAPI** (Python), a few endpoints: `/wells/chronic`, `/wells/{uwi}` (economics + break strip), `/rig/live` | Reuses the analysis code directly. Small, typed and fast to build. |
| Operator UI | **Canary Axiom** board (live rig tags, events table, chronic list) | Earns the Canary award and is how operators actually work |
| Engineer UI | **Streamlit** decision console: well map (lat/long), well card (repairs, cost, break-depth strip, replace-vs-repair calculator with sliders for price, cost, HR and horizon) | Lowest build risk in about 20 h. Use React only if a teammate is already fluent. |
| Edge | **nRF52832**: SAADC current sampling, streaming rainflow + Miner + depth-4 tree in C, BLE notify. **Arduino UNO**: drive control, servo brake, LCD. | Each board does what it is good at. The Uno has 2 KB RAM, too small for the odometer histogram. |
| Gateway | Python `bleak` -> Canary Write API (Store and Forward) | One process bridges BLE to the historian |
| Fabrication | Your 3D printer + UCalgary Lab NEXT / Schulich Makerspace (orientation and quiz needed for access; check open hours today) | Coupling, paddle rotor, brake pad, enclosure |

### Time reality (Saturday to Sunday 12:00)

- **Idea 5** needs about 3 h (hand-labelling + well card).
- **The Streamlit console** needs about 4 h.
- **Canary with Idea 4 tags** needs about 3 h.
- **The rig plus firmware** needs about 8-10 h and is the risk.
- With 3-4 people this fits if one person owns hardware end to end.
- If the rig is not working by Sunday 06:00, fall back to Idea 4's cut-down: stream the reference algorithm's output on recorded or synthetic signals into Canary. The story survives without the hardware.

## Ideas killed during screening, and why

Evidence for these is in `data/ideas/00_screening/out/screen_results.txt` (section labels S1-S11).

| Candidate | What the data said | Verdict |
|---|---|---|
| **PCP speed (RPM) operating window**: "slow pumps down to cut rod failures" | The raw signal looked strong: 0.36 rod failures per well-year below 100 RPM vs 2.75 at 400+ RPM (S5). Within the same wells, observed/expected failures by RPM band are 0.75, 0.92, 1.06, 1.10, 0.97, which is flat and non-monotonic (S5c). RPM correlates 0.56 with liquid rate. In the idea 1 Cox model, RPM's HR is 0.97. | **Killed.** High-RPM wells are the high-rate wells. Slowing a pump would cut oil without a proven failure benefit. |
| **Pump-efficiency window** | Failure rate *rises* with efficiency: 0.74 per well-year below 0.3, 1.58 at 1.1 or above (S5). Efficiency is derived from allocated volumes / (displacement x RPM), not measured (profile). | **Killed.** Not a wear indicator in this data. |
| **Maintenance effectiveness, measured as oil before vs after a job** | Rod jobs show *lower* oil afterwards (Corod Rod Repair median -0.18 m3/d) and pump/PCP jobs +0.13 to +0.45 m3/d (S4). Both are dominated by natural decline and selection. | **Reframed** into Idea 1. Run-life to the next failure is a cleaner effectiveness measure than oil rate. |
| **Repair dispatch / response time** | From the logged failure date, rod failures are back on production in a median 1 day (p90 4) (S6). Days down has no correlation with the well's oil rate (-0.03). | **Killed as stated.** But episodes start before the failure date, and 55% of downhole loss comes from episodes over 7 days. That part moved into Idea 3. |
| **Suspended-well reactivation** | 309 suspended oil wells; only 154 produced since 2021, at a median 0.64 m3/d and 99.1% water cut; 52 above 1 m3/d (S7). Past reactivations cost a median $44,911 and made 1.41 m3/d in months 1-6. | **Killed.** Small pool. Water-handling opex at 99% water cut is not in the data, and these wells were suspended for economic reasons. |
| **Polymer injection vs offset producer response** | 386 polymer injectors, with a median 10 producers within 500 m each (S8). Response lags are months to years, and surface lat/long is not the bottom-hole location for deviated or horizontal wells [domain reasoning]. | **Killed.** Attribution needs a reservoir or capacitance model that cannot be validated in 3 days. A Strathcona judge would challenge any number. |
| **Facility curtailment: shut in the highest-water-cut wells first** | Operators already do this. On constrained days, curtailed wells have a pooled oil cut of 0.63% vs 2.21% for wells left running (S11). | **Killed.** Became the 12-32 BTY debottleneck case in Idea 3. |

## Why Idea 1 is the strongest

1. **The effect is large and robust.**
   The hazard is halved after adjusting for history, rate, RPM and area x year.
   It holds in every prior-failure band (chart 1b), in the Kaplan-Meier curves, and in chronic-only and all-well models.
2. **It turns into a specific action.**
   "At the next pull on any well with 3 or more rod repairs in 12 months, run a new string, specified by dominant cause."
   Field crews can execute that, and the decision happens at a moment the rig is already on the well.
3. **The money is defensible.**
   Every input comes from Strathcona's own job costs and lost-oil records, priced at a cited WCS price.
   The program stays positive under every single stress.
   It only fails when all pessimistic assumptions are stacked, and even then the worst 14 wells still pay.
4. **It uses the data-quality work.**
   It handles the zero-cost 2021-22 jobs, the 2023 taxonomy change, the failure log starting in 2025, and censoring at suspension.
   This is what the Strathcona data analyst will probe.
5. **It is low build risk.**
   The analysis exists. The remaining work is the backtest, the sensitivity slide and the pitch.

**How to strengthen it for the finals (updated).**
- Pitch Idea 1 as the core, with Idea 5 as its "where and which remedy" layer and Idea 4 as the "prove and monitor" layer (see "How to differentiate").
- Idea 5 is nearly free and directly lowers Idea 1's cost: 54 program wells may need only a section.
- Idea 4 is the Canary showcase and the creativity score, but treat it as optional on build risk.
- Idea 2's watch-list remains a fallback monitoring layer if the hardware slips.

## The 3 judge questions most likely to sink Idea 1, with prepared answers

**Q1 (Strathcona analyst / ops EIT): "Strings get replaced when something else changes too: new pump, new design, an engineer's RCFA. Isn't your 0.49 just selection bias?"**
- The effect survives adjustment for prior failures (HR 1.41 per log unit), liquid rate and RPM, stratified by area x year.
- It appears in every prior-failure band, including wells with 3-4 and 5+ prior repairs where both actions are common (1,170 vs 63 and 1,420 vs 71 events).
- We do not claim the string alone does it. The HR is the effect of "the replacement job as practised", co-interventions included, which is what the program would repeat.
- Even at the upper 95% bound (HR 0.577) the program nets $5.89M.
- The definitive test is cheap: randomize 70 of the 145 wells to replace-at-next-failure for 6 months and compare run-life.
  We propose that as phase 1.

**Q2 (Strathcona analyst): "Your replacement cost of $22.7k is too low; rod material is booked separately. And 2021-22 rod jobs show $0 cost."**
- We saw the $0 rows: 99.9% of 2021 and 60.3% of 2022 Rod Truck jobs.
  So repair cost uses only 2023+ jobs with cost > 0 (mean $8,672), and replacement uses jobs with cost > 0 (mean $22,683).
- If material is extra, the break-even scales linearly.
  Doubling the incremental cost moves break-even from 1.0 to 2.0 failures/yr and the program still nets $5.40M.
  Every program well fails 3 or more times a year.
- We would like Strathcona's actual all-in string cost to plug in. The tool takes it as a parameter.

**Q3 (ops EIT / Strathcona): "Lost oil of 11.7 m3 per rod failure is too high. The well is back on production a day after the failure date."**
- From the logged failure date, yes: median 1 day (S6).
- But downtime starts earlier.
  Mean hours down climbs from 2.9 h at day -14 to 18.1 h at day -1, with 86% of day -1 rows already coded.
  Our window (7 days before to 1 day after the job, downhole codes only) captures that.
- If the judge prefers the median (7.33 m3), the program nets $6.11M.
- Ignoring lost oil entirely, it still nets $3.91M from job costs alone, with break-even at 1.6 failures/yr.
