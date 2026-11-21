# DSMLC F26 Dataset Handbook

**Chirality Research & Canary Labs Datathon**
Data Science and Machine Learning Club, November 2026

This dataset covers nearly six years (Jan 2021 – Oct 2026) of daily operating records for 2,905 heavy oil wells in Western Canada, with the jobs and equipment failures logged against them.

## Overview

Three Parquet files describe the same wells: one daily time series and two event logs.

| File | Type | Rows | Wells | Columns | Date range | Size |
|---|---|---|---|---|---|---|
| `daily_production.parquet` | Daily time series | 5,075,590 | 2,905 | 41 | 2021-01-01 to 2026-10-27 | 202 MB |
| `well_jobs.parquet` | Event log (one row per job) | 15,610 | 1,903 | 19 | 2021-01-01 to 2026-10-27 | 3.5 MB |
| `production_failures.parquet` | Event log (one row per failure) | 2,873 | 825 | 18 | 2021-12-14 to 2026-10-26 | 91 KB |

## Key Terms

| Term | Meaning | Where it appears |
|---|---|---|
| Heavy oil | Thick, viscous oil that will not flow to the surface on its own, so every producing well needs a pump. It comes up with a lot of water. | All production columns |
| UWI | Unique Well Identifier, the Canadian standard well label. It is built from the well's legal land location, so nearby wells have similar UWIs. | `uwi`, `formatted_uwi` |
| Producing well | A well lifting oil, water and gas to the surface. | `well_daily_status` = Producing |
| Injection well | A well that pumps water and polymer into the reservoir to push oil toward nearby producers. About a quarter of the wells. | `well_daily_status` = Injecting, `injected_*` columns |
| Polymer flood | Polymer thickens the injected water so it sweeps oil more evenly instead of channeling past it. | `injected_polymer_m3`, `injected_water_m3` |
| Suspended / abandoned | A suspended well is shut in for now and may return to service. An abandoned well is permanently plugged. | `well_daily_status` |
| Water cut | The share of produced liquid that is water: water / (oil + water). Not a column, but easy to calculate, and usually high in heavy oil. | `oil_produced_m3`, `water_produced_m3` |
| Downtime | Hours a well was not running, with coded reasons. Lost oil is an estimate of what it would have produced in that time. | `hours_down`, `downtime_code_1` to `3`, `lost_oil_m3` |
| Facility | The battery or plant a well's production flows to and is measured at. | `facility_name` |
| Field operating area | An operating region grouping nearby wells. There are 26. | `field_operating_area` |
| PCP (progressing cavity pump) | A downhole pump with a spiral rotor turning inside a rubber-lined stator. A drive head at surface spins it through a string of rods. | `pcp_pump_name`, `pcp_pump_make`, `pcp_pump_model` |
| Rod string | The steel rods connecting the surface drive head to the pump. Rods fail more often than anything else. | `failure_type` = Rods |
| Tubing | Pipe inside the well that carries produced fluid to surface. | `tubing_pressure_kpa` |
| Casing | The outer steel pipe lining the wellbore. Casing pressure is read in the space between casing and tubing. | `casing_pressure_kpa` |
| RPM | Pump speed. Faster moves more fluid but causes more wear. | `pcp_pump_rpm` |
| Rod torque | The twisting load on the rods. Rising torque can point to a pump or rod problem. | `pcp_pump_rod_torque_ftlb` |
| Displacement | The pump's rated volume per day at 100 RPM. Rated throughput is displacement × RPM / 100. | `pcp_pump_displacement_m3d100rpm` |
| Pump efficiency | Fluid actually moved compared with the pump's rated volume, stored as a decimal. A drop often means wear. | `pump_efficiency_pct`, `pcp_pump_volume_throughput_m3d` |
| Motor current | Current drawn by the drive motor, which tracks how hard the pump is working. | `pcp_pump_electric_current_a` |
| Choke | A valve that restricts flow at the surface. | `choke_open_pct` |
| Rod truck job | A smaller service job that pulls the rods and pump to repair or replace them. The most common job (9,359). | `job_category` = Rod Truck |
| Workover | A larger job using a service rig, such as replacing tubing or downhole equipment. | `job_category` = Workover |
| Completion | Work that gets a newly drilled well ready to produce or inject. | `job_category` = Completion |
| Spud / TD | Spud is the start of drilling. TD (total depth) is the bottom of the hole. | `duration_time_log_spud_td_hrs` |
| AFE | Authorization for Expenditure, the approved budget for a larger job, plus any supplements. | `afe_cost_total`, `afe_and_supp_cost_total` |
| Field estimate | The cost estimate recorded in the field, available for every job. | `field_est_total` |
| Fatigue | Metal cracking from repeated loading. | `cause` = Fatigue |
| Corrosion | Metal loss from chemical attack by produced fluids. | `cause` = Corrosion |
| Time series | Rows recorded at regular intervals where order matters, since today's value depends on yesterday's. | `daily_production.parquet` |
| Event record | One row each time something happened, with a date. A well may have many or none. | `well_jobs.parquet`, `production_failures.parquet` |
| Data historian | An industrial database that stores sensor readings continuously over time. Canary Historian is one example. | Source of the pressure and pump readings, summarised to one value per day |
| Historian tag | One named sensor stream in a historian. Each reading has a time, a value and a quality flag. | Each pressure or pump column is one tag per well |
| Grain | What one row represents. Joining files with different grain repeats rows. | Daily is well × day; jobs and failures are one event per row |

## Data Files

### `daily_production.parquet`

| Column | Type | Description |
|---|---|---|
| `uwi` | Text | Well identifier without punctuation; the join key |
| `formatted_uwi` | Text | Same identifier with slashes, e.g. `100/14-23-037-01W4/00` |
| `well_name` | Text | Operator's well name, often the formatted UWI plus a suffix such as INJ |
| `field_operating_area` | Text | One of 26 operating areas, e.g. Cactus Lake, Court, Winter |
| `province` | Text | SK, AB or BC |
| `surface_latitude` | Number | Latitude of the wellhead, decimal degrees |
| `surface_longitude` | Number | Longitude of the wellhead, decimal degrees |
| `on_production_date` | Date | Date the well first produced or injected (1951 to 2026) |
| `facility_name` | Text | Battery or plant the well reports to (282 facilities) |
| `well_daily_status` | Text | Status that day: Producing, Suspended, Injecting, Abandoned, Issued, Drilling or SOLD |
| `primary_fluid_type` | Text | Main fluid handled, e.g. Heavy Oil, Polymer, Water Injection, Gas |
| `flow_direction` | Text | production or injection |
| `production_date` | Date | The day the row describes |
| `hours_down` | Number | Hours not running that day (0–24) |
| `hours_on_prod` | Number | Hours running that day (0–24) |
| `lost_oil_m3` | Number | Estimated oil missed while down |
| `downtime_code_1` | Text | Full downtime reason, e.g. Uneconomic - Long Term Shut In |
| `downtime_code_2` | Text | Downtime reason, broad category, e.g. Uneconomic |
| `downtime_code_3` | Text | Downtime reason, detail, e.g. Long Term Shut In |
| `tubing_pressure_kpa` | Number | Daily tubing pressure; contains placeholder values such as 999999 |
| `casing_pressure_kpa` | Number | Daily casing pressure |
| `injection_pressure_kpa` | Number | Injection pressure on injection wells |
| `well_status` | Text | Overall well status; same values as `well_daily_status` |
| `oil_produced_m3` | Number | Oil produced that day |
| `gas_produced_e3m3` | Number | Gas produced that day |
| `injection_volume_m3` | Number | Total fluid injected that day |
| `injected_water_m3` | Number | Water injected that day |
| `injected_polymer_m3` | Number | Polymer solution injected that day |
| `pump_efficiency_pct` | Number | Actual vs rated pump volume, as a decimal (median 0.69) |
| `water_produced_m3` | Number | Water produced that day |
| `hydraulic_pressure_psi` | Number | Hydraulic drive pressure, some equipment only |
| `choke_open_pct` | Number | How far the surface choke is open |
| `pcp_pump_name` | Text | Pump label, usually well location plus PCP Pump |
| `pcp_pump_make` | Text | Manufacturer, e.g. Weatherford, PCM |
| `pcp_pump_model` | Text | Pump model, e.g. 6M-1800 |
| `pcp_pump_displacement_m3d100rpm` | Number | Rated volume per day at 100 RPM |
| `pcp_pump_rpm` | Number | Pump speed (median 200) |
| `pcp_pump_comment` | Text | Free-text pump note, often a date |
| `pcp_pump_electric_current_a` | Number | Motor current drawn |
| `pcp_pump_rod_torque_ftlb` | Number | Torque on the rod string |
| `pcp_pump_volume_throughput_m3d` | Number | Volume the pump moved that day |

### `well_jobs.parquet`

| Column | Type | Description |
|---|---|---|
| `uwi` | Text | Well identifier without punctuation; the join key |
| `formatted_uwi` | Text | Same identifier with slashes |
| `well_name` | Text | Well name as recorded on the job, often including the original operator |
| `field_operating_area` | Text | Operating area (25 appear in this file) |
| `job_category` | Text | Broad job class, e.g. Rod Truck, Workover, Drilling, Completion, Abandon |
| `job_type` | Text | More specific job type (89 values), e.g. Reactivation, Coil Job |
| `job_subtype` | Text | Specific issue or task, e.g. Sand clean out, Rods - Routine - Upset |
| `start_date` | Date | Job start |
| `end_date` | Date | Job end |
| `job_duration_days` | Number | Job length in days (median 0.4); a few negative values |
| `job_status_1` | Text | Empty |
| `job_status_2` | Text | Empty |
| `objective` | Text | What the crew was sent to do |
| `summary` | Text | Crew's account of the work, often hundreds of words |
| `actual_final_job_cost` | Number | Empty |
| `afe_cost_total` | Number | Approved budget (AFE) for larger jobs, about 5% of rows |
| `afe_and_supp_cost_total` | Number | AFE plus any supplementary approvals |
| `field_est_total` | Number | Field cost estimate (median about $6,400) |
| `duration_time_log_spud_td_hrs` | Number | Drilling jobs only: time from spud to total depth |

### `production_failures.parquet`

| Column | Type | Description |
|---|---|---|
| `uwi` | Text | Well identifier without punctuation; the join key |
| `formatted_uwi` | Text | Well identifier with slashes |
| `well_name` | Text | Well name as recorded on the failure |
| `field_operating_area` | Text | Operating area (17 appear in this file) |
| `failure_start_date` | Date | Date the failure occurred (Dec 2021 to Oct 2026) |
| `failure_end_date` | Date | Date the failure ended at |
| `cause` | Text | Engineering cause, e.g. Fatigue, Corrosion, Load / Excess Stress, Erosion |
| `cause_detail` | Text | Component or detail behind the cause, e.g. Rods |
| `cause_category` | None | Empty |
| `action_taken` | Text | Response to the failure |
| `failure_detail` | Text | Specific failure mode, e.g. Rods Routine - Upset, Rods Routine - Broken Corod body |
| `failure_description` | Text | Short description, rarely filled, e.g. Pump Failure, Polish Rod Break |
| `failure_system` | Text | System affected, rarely filled, e.g. PCP System |
| `failure_system_category` | None | Type of failure the system experienced |
| `failure_comments` | Text | Free-text notes, often the failure depth, e.g. Broken corod @ 268m |
| `failure_type_category` | None | Indicates the failure |
| `cause_comments` | Text | Suspected or confirmed causes for the failure |
| `failure_type` | Text | Component that failed: Rods, Pump, Tubing, Surface Failure, Casing |

## Units

| Suffix / Unit | Unit | Used for |
|---|---|---|
| `_m3` | Cubic metres | Liquid volumes (1 m³ ≈ 6.3 barrels) |
| `_e3m3` | Thousand cubic metres | Gas volumes |
| `_kpa` | Kilopascals | Pressure |
| `_psi` | Pounds per square inch | Hydraulic pressure, some equipment only |
| `_ftlb` | Foot-pounds | Rod torque |
| `_a` | Amps | Motor current |
| `_pct` | Proportion | Stored as a decimal (0–1), not 0–100 |

## Resources

| Resource | Topic | What it covers |
|---|---|---|
| [Unique Well Identifiers (Alberta Energy Regulator)](https://static.aer.ca/prd/documents/applications/UWI-Description.pdf) | UWI | How the UWI is structured from legal land location, including event sequences and special cases |
| [Progressing cavity pump (PCP) systems (PetroWiki)](https://petrowiki.spe.org/Progressing_cavity_pump_(PCP)_systems) | Pumps | How surface-driven PCPs work, and their strengths and limits with viscous fluids |
| [The Defining Series: Progressing Cavity Pumps (SLB Oilfield Review)](https://www.slb.com/resource-library/oilfield-review/defining-series/defining-pcp) | Pumps | Short illustrated primer on rotor, stator and how a PCP moves fluid |
| [Polymer waterflooding (PetroWiki)](https://petrowiki.spe.org/Polymer_waterflooding) | Injection | Why polymer is added to injected water and how it improves sweep |
| [Canary Historian Storage Methodology (Canary Labs)](https://helpcenter.canarylabs.com/t/h7ypl9d/canary-historian-storage-methodology-version-26) | Historians | How a historian stores tags, timestamps, values and quality codes |
| [Apache Parquet overview](https://parquet.apache.org/docs/overview/) | Parquet | The column-based file format used for all three files |
