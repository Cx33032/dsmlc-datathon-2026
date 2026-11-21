# Data quality findings

Source script: `python data/ideas/00_profiling/profile.py`.
Every number below comes from its output, `data/ideas/00_profiling/out/profile_results.txt`.
The script uses DuckDB over the Parquet files, so the 5.07M-row daily file is never loaded whole into memory.
Runtime is about 20 s.

## Headline issues a Strathcona analyst will ask about

| # | Issue | Evidence | How we handle it |
|---|---|---|---|
| 1 | The failure log only becomes complete in **June 2025**, not Dec 2021 | 1 record in 2021-12, 1 in 2022-08, 3 in Jan-Feb 2025, 27 in May 2025, then 128-197 per month from Jun 2025 to Oct 2026 | Any analysis that uses `production_failures` starts at 2025-06-01. For 2021-2026 history we use failure-type repair **jobs** as the label. 89% of Corod Rod Repair and 97% of Stick Rod Repair jobs since mid-Jun 2025 have a failure record within -14..+3 days, which validates them as a proxy. |
| 2 | Wells are already down **before** the logged failure date | Mean `hours_down` rises from 2.9 h at day -14 to 18.1 h at day -1. The share of days carrying a downtime code goes from 16% to 86% over the same window. | Any "leading indicator" in the last days before a failure is mostly the failure itself. The model in idea 2 only scores wells that were fully up on the 3 days up to the snapshot. |
| 3 | Rod Truck costs are missing for 2021-2022 | `field_est_total = 0` on 99.9% of 2021 Rod Truck jobs and 60.3% of 2022 jobs, but only 0.1-0.5% from 2023 on | Unit costs come from jobs with cost > 0 dated 2023 or later. |
| 4 | Job taxonomy changed in 2023 | The generic `Rod Repair` type has 1,052 jobs (2021) and 1,534 (2022), then is split into `Corod Rod Repair` and `Stick Rod Repair` from 2023 | Both are mapped to one "rod repair" class. |
| 5 | Two downtime-code taxonomies are mixed | 137 distinct `downtime_code_1` values and 72 distinct `downtime_code_2` values. Long names (e.g. `Downhole Equipment`) sit next to short legacy codes (`RODSPART`, `UNPLNDW`, `CODE3`, `UNECO10`...). | Idea 3 maps both taxonomies to 9 buckets. The unmapped remainder is small after 2021 (238-1,134 m3/yr lost oil, see idea 3). |
| 6 | Sensor tags are mostly flat-lined, not continuous | On consecutive producing days the value is identical 94.7% of the time for torque, 96.9% for current, 97.1% for RPM and 97.5% for tubing pressure. On average a value changes every 18.9 days (torque), 32.4 days (current) and 34.5 days (RPM). `pump_efficiency_pct` changes daily (only 0.6% identical) because it is derived from daily volumes. | These are periodic manual or forward-filled readings, not high-frequency historian data. Short-horizon sensor "trend" features carry little information, and the idea 2 results confirm this. |
| 7 | "Producing" wells that are actually shut in | 244,342 Producing rows (480 wells) carry `downtime_code_2 = 'Uneconomic'`, and their reported `lost_oil_m3` sums to 144,515 m3 | Uneconomic shut-ins are excluded from "recoverable" lost oil in every idea. |

## Shapes, keys and joins

| File | Rows | Distinct wells | Date range |
|---|---|---|---|
| daily_production | 5,075,590 | 2,905 | 2021-01-01 to 2026-10-27 |
| well_jobs | 15,610 | 1,903 | 2021-01-01 to 2026-10-27 |
| production_failures | 2,873 | 825 | 2021-12-14 to 2026-10-26 |

- There are 29 duplicate (`uwi`, `production_date`) keys in the daily file.
- `uwi` joins well across files: 1,834 of 1,903 job wells (96.37%) and 824 of 825 failure wells (99.88%) exist in the daily file.
- At row level, 93.36% of job start dates and 99.93% of failure dates have a daily row for the same well on the same day.
- `uwi` maps to exactly one `formatted_uwi` in both files.
- **Grain warning:** daily rows are well x day, while jobs and failures are events. Joining events directly to daily rows repeats each event across days. All joins in this project go event -> daily window (e.g. days -37..-8), never daily -> event.
- 98.1% of failures have a Rod Truck or Workover job on the same well between 3 days before and 14 days after the failure date.
- Within a well, `facility_name` changes for 93 wells and `pcp_pump_model` for 1,041 wells, so pump changes are recorded. Area and lat/long never change.
- There are 37 groups of duplicate jobs (same `uwi`, `start_date`, `job_type`), giving 39 extra rows, and 9 duplicate failures (same `uwi` and date). Idea 1 deduplicates jobs within 3 days.

## Null rates (selected; full table in the profile output)

| Column | Null % | Note |
|---|---|---|
| `lost_oil_m3` | 67.55 | Expected: only populated on down days |
| `downtime_code_1` | 64.28 | 27,605 rows have `hours_down > 0` but no code |
| `tubing_pressure_kpa` | 47.43 | |
| `casing_pressure_kpa` | 38.78 | |
| `pump_efficiency_pct` | 66.79 | |
| `pcp_pump_rpm` | 52.51 | 0% filled in Fenn Big Valley and CHO-Non-Op (see coverage) |
| `pcp_pump_rod_torque_ftlb` | 74.03 | |
| `pcp_pump_electric_current_a` | 82.19 | |
| `oil_produced_m3` | 23.06 | |
| `facility_name` | 17.18 | |
| `failure_end_date` | 99.97 | Failure duration cannot be taken from the failure log |
| `cause` | 5.43 | |
| `afe_cost_total` | 95.04 | Only `field_est_total` is usable (0% null) |
| `job_status_1/2`, `actual_final_job_cost` | ~100 | Empty |

## Value ranges, sentinels and placeholders (daily file)

| Column | Finding | Count |
|---|---|---|
| `tubing_pressure_kpa` | Exactly 999999 | 7 rows |
| `tubing_pressure_kpa` | Repeated 22598.3 (likely a unit or placeholder artefact) | 1,138 rows |
| `tubing_pressure_kpa` | > 20,000 kPa | 1,155 rows |
| `tubing_pressure_kpa` | Negative | 3,033 rows |
| `casing_pressure_kpa` | Repeated 85873.5 | 819 rows |
| `casing_pressure_kpa` | Negative (min -3,446) | 27,214 rows |
| `pcp_pump_rpm` | > 1,000 (max 44,180) | 6,820 rows |
| `pcp_pump_rod_torque_ftlb` | > 20,000 (max 331,460) | 516 rows |
| `pcp_pump_electric_current_a` | > 1,000 A (max 84,860) | 113 rows |
| `oil_produced_m3` | Negative (min -163.9, allocation corrections) | 3,720 rows |
| `water_produced_m3` | Negative | 10,284 rows |
| `injected_water_m3` | Min -39,786 | 71 negative rows |
| `hydraulic_pressure_psi` | Max 105,460 | |

Cleaning rules (`data/ideas/common.py`, dict `CLEAN`) set values to NULL outside these limits: torque 1-20,000 ft-lb, current 1-1,000 A, RPM 1-1,000, efficiency 0-3, tubing/casing pressure 0-20,000 kPa, and oil/water >= 0.

`hours_down + hours_on_prod = 24` on every one of the 5,075,590 rows, so the two hours columns are consistent.

## The `_pct` columns

- `pump_efficiency_pct` is a decimal as documented (median 0.691).
  However, 6.83% of non-null values are above 1 and 1.19% above 1.5, with a max of 91.4 and 2,001 negative values.
- `pump_efficiency_pct` is derived, not measured.
  For 68.4% of rows it equals (oil + water) / `pcp_pump_volume_throughput_m3d` to within 0.01.
  `pcp_pump_volume_throughput_m3d` equals displacement x RPM / 100 on 99.4% of rows.
  So pump efficiency inherits every error in RPM and in the allocated volumes.
- `choke_open_pct` is **not** a decimal, contrary to the handbook: 99.66% of non-null values are above 1, with a median of 100 and a max of 1,000.
  It is a 0-100 percentage with some 10x errors.

## Status and code distributions

- `well_daily_status`: Producing 52.02%, Suspended 23.87%, Injecting 22.59%, NULL 1.04%, Abandoned 0.33%, Issued 0.14%, SOLD and Drilling under 0.01%.
- `well_status` disagrees with `well_daily_status` on 39,608 rows.
- Oil is reported on 72 Suspended days (617 m3) and 557 NULL-status days (539 m3).
- Largest lost-oil codes over the whole file (`downtime_code_1`):
  - Uneconomic - Long Term Shut In: 162,412 m3
  - Downhole Equipment - Rods: 72,080 m3
  - ALL - Downhole - Rodstring Failure: 40,015 m3
  - Facility - Limited Capacity: 29,374 m3
  - Downhole Equipment - Pump: 24,205 m3
- `failure_type` has 5 clean values (Rods 2,186, Pump 381, Tubing 260, Surface Failure 7, Casing 3), 9 NULLs, and 26 free-text variants covering 27 rows ("Parted rod", "|Rod", "TUBING"...).
- Top rod failure causes: Fatigue 1,074, Corrosion 719, Load / Excess Stress 242, Erosion 87.
- `pcp_pump_make` has case and whitespace variants: PCM has 3 spellings, MANTL 3, WEATHERFORD 3 (one with a trailing space), EUROPUMP 2 and KUDU 2.

## Jobs anomalies

- There are 65 negative `job_duration_days` (min -111.5 days) and 17 rows with `end_date < start_date`.
  Most negatives are under 1 day on same-day jobs, which suggests the duration is computed from times that cross midnight.
  The 7 large ones (-35 to -111 days) look like swapped dates on Workover jobs.
- `end_date` is NULL on 497 jobs.
- 2,387 jobs have `field_est_total <= 0` (one is -41,395).
  18 jobs exceed $1M (max $2.26M), all drilling or completion scale.
- `job_category` has 29 values, of which about 20 are free-text equipment descriptions with one row each (e.g. "2-kudu Drivehead Oryx Seals").

## Coverage over time (Producing rows)

| Year | Wells | RPM fill % | Torque % | Current % | Efficiency % | Tubing % | Oil (thousand m3) |
|---|---|---|---|---|---|---|---|
| 2021 | 1,241 | 59.3 | 32.4 | 26.3 | 47.6 | 62.8 | 1,380.7 |
| 2022 | 1,305 | 77.5 | 47.8 | 28.8 | 62.8 | 80.4 | 1,390.8 |
| 2023 | 1,280 | 81.4 | 50.6 | 30.8 | 70.1 | 86.0 | 1,369.2 |
| 2024 | 1,340 | 82.0 | 50.1 | 32.4 | 69.2 | 77.3 | 1,407.1 |
| 2025 | 1,382 | 82.5 | 47.8 | 33.5 | 67.9 | 73.3 | 1,306.3 |
| 2026 (to Oct 27) | 1,380 | 80.9 | 47.3 | 34.0 | 64.2 | 72.3 | 963.1 |

- Failures and jobs are logged only in some areas.
  Fenn Big Valley (128 producing wells since 2022) and CHO-Non-Op (58) have **zero** failures, **zero** Rod Truck jobs and 0% RPM fill.
  These are probably non-operated or differently managed assets.
  A model trained on all wells would learn "no sensors means no failure", so these areas must be excluded or flagged.
- Plover Lake Conventional has 75 producing wells but only 8 failures.
- Rows per well: median 2,126 (the full window), 10th percentile 646, minimum 1.

## What this means for the ideas

1. Failure-prediction labels must come from jobs for 2021-2024 and can be checked against the failure log only from Jun 2025.
2. The 3-7 days of downtime before a logged failure are leakage, not a signal.
3. Cost analysis must exclude zero-cost 2021-2022 Rod Truck rows.
4. "Lost oil" KPIs must drop Uneconomic codes, which would otherwise add about 27,000 m3/yr (see idea 3).
5. Torque, current and RPM are slow-changing setpoint-like readings, so they describe *how* a well is run more than *when* it will fail.
