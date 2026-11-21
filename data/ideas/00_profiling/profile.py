"""Data-quality profile of the three Strathcona Parquet files.

Run:  python data/ideas/00_profiling/profile.py
Writes plain-text results to data/ideas/00_profiling/out/profile_results.txt
(every number in docs/ideas/00_data_quality.md comes from that file).
Uses DuckDB so the 5M-row daily file is never loaded whole into pandas.
"""
from pathlib import Path
import sys
import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
D = (DATA / "daily_production.parquet").as_posix()
J = (DATA / "well_jobs.parquet").as_posix()
F = (DATA / "production_failures.parquet").as_posix()

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 400)
con = duckdb.connect()
_lines = []


def emit(title, obj=""):
    s = f"\n### {title}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    _lines.append(s)


def q(sql):
    return con.sql(sql).df()


def null_rates(path, name):
    cols = q(f"describe select * from '{path}'")["column_name"].tolist()
    exprs = ", ".join(
        f"round(100.0*count(*) filter (where \"{c}\" is null)/count(*),2) as \"{c}\"" for c in cols
    )
    r = q(f"select {exprs} from '{path}'").T
    r.columns = ["null_pct"]
    emit(f"{name}: null % per column", r)


# ---------------------------------------------------------------- shapes
emit("Row counts / distinct wells", q(f"""
select 'daily' f, count(*) n, count(distinct uwi) wells, min(production_date) mn, max(production_date) mx from '{D}'
union all select 'jobs', count(*), count(distinct uwi), min(start_date), max(start_date) from '{J}'
union all select 'failures', count(*), count(distinct uwi), min(failure_start_date), max(failure_start_date) from '{F}'
"""))
emit("Duplicate (uwi, production_date) keys in daily", q(f"""
select count(*) dup_keys from (select uwi, production_date, count(*) c from '{D}' group by 1,2 having c>1)"""))

# ---------------------------------------------------------------- nulls
null_rates(D, "daily")
null_rates(J, "jobs")
null_rates(F, "failures")

# ---------------------------------------------------------------- numeric ranges + sentinels
num_cols = ["hours_down", "hours_on_prod", "lost_oil_m3", "tubing_pressure_kpa", "casing_pressure_kpa",
            "injection_pressure_kpa", "oil_produced_m3", "gas_produced_e3m3", "injection_volume_m3",
            "injected_water_m3", "injected_polymer_m3", "pump_efficiency_pct", "water_produced_m3",
            "hydraulic_pressure_psi", "choke_open_pct", "pcp_pump_displacement_m3d100rpm", "pcp_pump_rpm",
            "pcp_pump_electric_current_a", "pcp_pump_rod_torque_ftlb", "pcp_pump_volume_throughput_m3d"]
rows = []
for c in num_cols:
    r = q(f"""select '{c}' col, count("{c}") n, min("{c}")::double mn,
        quantile_cont("{c}"::double,0.01) p01, median("{c}"::double) p50, quantile_cont("{c}"::double,0.99) p99,
        max("{c}")::double mx,
        count(*) filter (where "{c}"<0) n_neg,
        count(*) filter (where "{c}"=0) n_zero,
        count(*) filter (where "{c}">=99999) n_ge_99999,
        count(*) filter (where "{c}"=999999) n_eq_999999
        from '{D}'""")
    rows.append(r)
emit("daily: numeric ranges, zeros, negatives, sentinels", pd.concat(rows).set_index("col").round(3))

emit("tubing_pressure_kpa: most common values >= 10000 kPa", q(f"""
select tubing_pressure_kpa v, count(*) n from '{D}' where tubing_pressure_kpa>=10000 group by 1 order by n desc limit 10"""))
emit("casing_pressure_kpa: most common values >= 10000 kPa", q(f"""
select casing_pressure_kpa v, count(*) n from '{D}' where casing_pressure_kpa>=10000 group by 1 order by n desc limit 10"""))

# ---------------------------------------------------------------- _pct columns
emit("_pct columns: share of non-null values > 1 (should be decimals 0-1)", q(f"""
select 'pump_efficiency_pct' col, count(pump_efficiency_pct) n,
  round(100.0*count(*) filter (where pump_efficiency_pct>1)/count(pump_efficiency_pct),2) pct_gt1,
  round(100.0*count(*) filter (where pump_efficiency_pct>1.5)/count(pump_efficiency_pct),2) pct_gt1_5,
  round(100.0*count(*) filter (where pump_efficiency_pct=0)/count(pump_efficiency_pct),2) pct_eq0
from '{D}'
union all
select 'choke_open_pct', count(choke_open_pct),
  round(100.0*count(*) filter (where choke_open_pct>1)/nullif(count(choke_open_pct),0),2),
  round(100.0*count(*) filter (where choke_open_pct>1.5)/nullif(count(choke_open_pct),0),2),
  round(100.0*count(*) filter (where choke_open_pct=0)/nullif(count(choke_open_pct),0),2)
from '{D}'"""))

emit("pump_efficiency_pct consistency: eff vs (oil+water)/throughput and throughput vs disp*rpm/100", q(f"""
with t as (select pump_efficiency_pct e, oil_produced_m3 o, water_produced_m3 w,
   pcp_pump_volume_throughput_m3d thr, pcp_pump_displacement_m3d100rpm disp, pcp_pump_rpm::double rpm
   from '{D}' where pump_efficiency_pct is not null and pcp_pump_volume_throughput_m3d>0 and disp>0 and rpm>0)
select count(*) n,
 median(abs(thr - disp*rpm/100)) med_abs_thr_minus_rated,
 round(100.0*avg(case when abs(thr - disp*rpm/100)<0.5 then 1 else 0 end),1) pct_thr_eq_rated,
 median(abs(e - (o+w)/thr)) med_abs_eff_minus_liquid_over_thr,
 round(100.0*avg(case when abs(e - (o+w)/thr)<0.01 then 1 else 0 end),1) pct_eff_eq_liquid_over_thr
from t"""))

# ---------------------------------------------------------------- hours consistency
emit("hours_down + hours_on_prod vs 24", q(f"""
select round(hours_down+hours_on_prod) tot, count(*) n from '{D}'
where hours_down is not null and hours_on_prod is not null group by 1 order by n desc limit 8"""))
emit("lost_oil_m3 vs hours_down", q(f"""
select (hours_down>0) down, (lost_oil_m3>0) lost, (downtime_code_1 is not null) coded, count(*) n
from '{D}' where well_daily_status='Producing' group by 1,2,3 order by n desc"""))

# ---------------------------------------------------------------- categorical distributions
emit("well_daily_status distribution", q(f"""
select well_daily_status, count(*) n, round(100.0*count(*)/sum(count(*)) over(),2) pct, count(distinct uwi) wells
from '{D}' group by 1 order by n desc"""))
emit("well_daily_status vs well_status mismatch", q(f"""
select count(*) filter (where well_daily_status<>well_status) n_mismatch, count(*) n from '{D}'"""))
emit("primary_fluid_type x flow_direction", q(f"""
select primary_fluid_type, flow_direction, count(*) n, count(distinct uwi) wells from '{D}' group by 1,2 order by n desc"""))
emit("Oil reported on non-Producing days", q(f"""
select well_daily_status, count(*) n_days_with_oil, round(sum(oil_produced_m3),0) oil_m3
from '{D}' where oil_produced_m3>0 group by 1 order by 2 desc"""))
emit("downtime_code_2 (broad) distribution: days, hours, lost oil (Producing + Suspended)", q(f"""
select downtime_code_2, count(*) n_days, round(sum(hours_down)) hrs, round(sum(lost_oil_m3)) lost_oil_m3, count(distinct uwi) wells
from '{D}' where downtime_code_1 is not null group by 1 order by lost_oil_m3 desc nulls last"""))
emit("downtime_code_1 top 30 by lost oil", q(f"""
select downtime_code_1, count(*) n_days, round(sum(lost_oil_m3)) lost_oil_m3, count(distinct uwi) wells
from '{D}' where downtime_code_1 is not null group by 1 order by lost_oil_m3 desc nulls last limit 30"""))
emit("Distinct downtime codes", q(f"""
select count(distinct downtime_code_1) c1, count(distinct downtime_code_2) c2, count(distinct downtime_code_3) c3 from '{D}'"""))
emit("Downtime code present while hours_down = 0", q(f"""
select count(*) filter (where downtime_code_1 is not null and coalesce(hours_down,0)=0) code_no_hours,
       count(*) filter (where downtime_code_1 is null and hours_down>0) hours_no_code from '{D}'"""))

emit("jobs: job_category distribution", q(f"""
select job_category, count(*) n, count(distinct uwi) wells, round(median(field_est_total)) med_cost,
  round(sum(field_est_total)/1e6,2) total_cost_MCAD from '{J}' group by 1 order by n desc"""))
emit("jobs: top 25 job_type", q(f"""
select job_category, job_type, count(*) n, round(median(field_est_total)) med_cost from '{J}' group by 1,2 order by n desc limit 25"""))
emit("failures: failure_type x cause", q(f"""
select failure_type, cause, count(*) n from '{F}' group by 1,2 order by n desc limit 25"""))
emit("failures: failure_type", q(f"""select failure_type, count(*) n from '{F}' group by 1 order by n desc"""))
emit("failures: failure_detail top 15", q(f"""select failure_detail, count(*) n from '{F}' group by 1 order by n desc limit 15"""))

# ---------------------------------------------------------------- jobs anomalies
emit("jobs: duration anomalies", q(f"""
select count(*) filter (where job_duration_days<0) neg_duration,
  min(job_duration_days) min_dur, max(job_duration_days) max_dur,
  count(*) filter (where end_date<start_date) end_before_start,
  count(*) filter (where end_date is null) null_end,
  count(*) filter (where abs(job_duration_days - date_diff('day',start_date,end_date))>1.5) dur_disagrees_with_dates,
  count(*) filter (where field_est_total<=0) cost_le0,
  count(*) filter (where field_est_total>1e6) cost_gt1M,
  max(field_est_total) max_cost
from '{J}'"""))
emit("jobs: negative-duration rows", q(f"""
select job_category, job_type, start_date, end_date, job_duration_days, field_est_total from '{J}' where job_duration_days<0 order by job_duration_days"""))
emit("jobs: exact duplicate (uwi,start_date,job_type) rows", q(f"""
select count(*) n_dup_groups, sum(c-1) extra_rows from (select uwi,start_date,job_type,count(*) c from '{J}' group by 1,2,3 having c>1)"""))
emit("failures: date anomalies", q(f"""
select count(*) n, count(*) filter (where failure_end_date is null) null_end,
 count(*) filter (where failure_end_date<failure_start_date) end_before_start,
 median(date_diff('day',failure_start_date,failure_end_date)) med_dur_days,
 count(*) filter (where failure_start_date<'2022-01-01') before_2022
from '{F}'"""))
emit("failures: exact duplicate (uwi, failure_start_date) rows", q(f"""
select count(*) n_dup_groups, sum(c-1) extra_rows from (select uwi,failure_start_date,count(*) c from '{F}' group by 1,2 having c>1)"""))

# ---------------------------------------------------------------- coverage over time
emit("Coverage by year: wells, rows, sensor fill % (Producing rows only)", q(f"""
select year(production_date) yr, count(distinct uwi) wells, count(*) n_rows,
 round(100.0*count(pcp_pump_rpm)/count(*),1) rpm_pct,
 round(100.0*count(pcp_pump_rod_torque_ftlb)/count(*),1) torque_pct,
 round(100.0*count(pcp_pump_electric_current_a)/count(*),1) current_pct,
 round(100.0*count(pump_efficiency_pct)/count(*),1) eff_pct,
 round(100.0*count(tubing_pressure_kpa)/count(*),1) tbg_pct,
 round(100.0*count(casing_pressure_kpa)/count(*),1) csg_pct,
 round(sum(oil_produced_m3)/1e3,1) oil_km3
from '{D}' where well_daily_status='Producing' group by 1 order by 1"""))
emit("Failures and jobs by year", q(f"""
select y, sum(f) failures, sum(j) jobs, sum(rt) rod_truck_jobs from (
 select year(failure_start_date) y, 1 f, 0 j, 0 rt from '{F}'
 union all select year(start_date), 0, 1, (job_category='Rod Truck')::int from '{J}') group by 1 order by 1"""))
emit("Rows per well: distribution of days per well", q(f"""
select min(n) mn, quantile_cont(n,0.1) p10, median(n) p50, max(n) mx from (select uwi, count(*) n from '{D}' group by 1)"""))

# ---------------------------------------------------------------- stuck / flatlined sensors
emit("Flatline check: % of consecutive-day pairs with identical value (Producing, both non-null)", q(f"""
with t as (select uwi, production_date, pcp_pump_rod_torque_ftlb tq, pcp_pump_electric_current_a cu,
   pcp_pump_rpm::double rpm, tubing_pressure_kpa tb, pump_efficiency_pct ef,
   lag(pcp_pump_rod_torque_ftlb) over w tq0, lag(pcp_pump_electric_current_a) over w cu0,
   lag(pcp_pump_rpm::double) over w rpm0, lag(tubing_pressure_kpa) over w tb0, lag(pump_efficiency_pct) over w ef0
   from '{D}' where well_daily_status='Producing' window w as (partition by uwi order by production_date))
select round(100.0*avg((tq=tq0)::int),1) torque_same, round(100.0*avg((cu=cu0)::int),1) current_same,
       round(100.0*avg((rpm=rpm0)::int),1) rpm_same, round(100.0*avg((tb=tb0)::int),1) tubing_same,
       round(100.0*avg((ef=ef0)::int),1) eff_same from t"""))

# ---------------------------------------------------------------- joins
emit("UWI join coverage (distinct wells in event file that exist in daily)", q(f"""
with d as (select distinct uwi from '{D}')
select 'jobs' f, count(distinct j.uwi) wells, count(distinct j.uwi) filter (where d.uwi is not null) matched,
  round(100.0*count(distinct j.uwi) filter (where d.uwi is not null)/count(distinct j.uwi),2) pct
from '{J}' j left join d using(uwi)
union all
select 'failures', count(distinct f.uwi), count(distinct f.uwi) filter (where d.uwi is not null),
  round(100.0*count(distinct f.uwi) filter (where d.uwi is not null)/count(distinct f.uwi),2)
from '{F}' f left join d using(uwi)"""))
emit("Row-level join: event rows that have a daily row for the same uwi on the event date", q(f"""
select 'jobs.start_date' k, count(*) n, count(d.uwi) matched, round(100.0*count(d.uwi)/count(*),2) pct
from '{J}' j left join (select uwi, production_date from '{D}') d on d.uwi=j.uwi and d.production_date=j.start_date
union all
select 'failures.failure_start_date', count(*), count(d.uwi), round(100.0*count(d.uwi)/count(*),2)
from '{F}' f left join (select uwi, production_date from '{D}') d on d.uwi=f.uwi and d.production_date=f.failure_start_date"""))
emit("formatted_uwi consistency: same uwi -> one formatted_uwi?", q(f"""
select (select count(*) from (select uwi from '{D}' group by 1 having count(distinct formatted_uwi)>1)) daily_multi,
       (select count(*) from (select uwi from '{J}' group by 1 having count(distinct formatted_uwi)>1)) jobs_multi"""))
emit("Static attributes that change within a well (daily)", q(f"""
select (select count(*) from (select uwi from '{D}' group by 1 having count(distinct facility_name)>1)) multi_facility,
       (select count(*) from (select uwi from '{D}' group by 1 having count(distinct field_operating_area)>1)) multi_area,
       (select count(*) from (select uwi from '{D}' group by 1 having count(distinct surface_latitude)>1)) multi_lat,
       (select count(*) from (select uwi from '{D}' group by 1 having count(distinct pcp_pump_model)>1)) multi_pump_model"""))
emit("Failure -> job linkage: failures with a Rod Truck/Workover job on same well within 0..14 days after", q(f"""
with fl as (select row_number() over () fid, * from '{F}')
select count(distinct fid) n_fail,
 count(distinct fid) filter (where j.uwi is not null) with_job,
 round(100.0*count(distinct fid) filter (where j.uwi is not null)/count(distinct fid),1) pct
from fl left join '{J}' j on j.uwi=fl.uwi and j.job_category in ('Rod Truck','Workover')
  and j.start_date between fl.failure_start_date - interval 3 day and fl.failure_start_date + interval 14 day"""))
emit("Leakage check: downtime_code_2 on the failure date (failures joined to daily)", q(f"""
select d.downtime_code_2, count(*) n from '{F}' f join '{D}' d on d.uwi=f.uwi and d.production_date=f.failure_start_date
group by 1 order by n desc limit 12"""))
emit("Leakage check: hours_down on the failure date", q(f"""
select round(avg(d.hours_down),2) mean_hours_down, round(100.0*avg((d.hours_down>0)::int),1) pct_down,
 round(100.0*avg((d.oil_produced_m3>0)::int),1) pct_oil_gt0
from '{F}' f join '{D}' d on d.uwi=f.uwi and d.production_date=f.failure_start_date"""))
emit("Failure areas vs daily areas (failures only logged in some areas?)", q(f"""
with fa as (select field_operating_area a, count(*) nf from '{F}' group by 1),
 da as (select field_operating_area a, count(distinct uwi) wells,
   count(distinct uwi) filter (where well_daily_status='Producing' and production_date>='2022-01-01') prod_wells_2022p
   from '{D}' group by 1),
 ja as (select field_operating_area a, count(*) filter (where job_category='Rod Truck' and start_date>='2022-01-01') rt from '{J}' group by 1)
select da.a, da.wells, da.prod_wells_2022p, coalesce(nf,0) failures, coalesce(rt,0) rodtruck_jobs_2022p
from da left join fa on fa.a=da.a left join ja on ja.a=da.a order by prod_wells_2022p desc"""))


# ---------------------------------------------------------------- extra checks used by the ideas
emit("Failure log records per month (completeness)", q(f"""
select strftime(failure_start_date,'%Y-%m') m, count(*) n from '{F}' group by 1 order by 1"""))
emit("Job taxonomy change: rod job types by year", q(f"""
select year(start_date) y, count(*) filter (where job_type='Rod Repair') rod_repair_generic,
  count(*) filter (where job_type='Corod Rod Repair') corod_repair, count(*) filter (where job_type='Stick Rod Repair') stick_repair,
  round(median(field_est_total) filter (where job_type='Rod Repair')) med_cost_generic
from '{J}' group by 1 order by 1"""))
emit("Share of Rod Truck jobs with field_est_total = 0, by year", q(f"""
select year(start_date) y, count(*) n, round(100.0*avg((field_est_total=0)::int),1) pct_zero_cost
from '{J}' where job_category='Rod Truck' group by 1 order by 1"""))
emit("Sensor update cadence: producing days per value change (non-null, consecutive days)", q(f"""
with t as (select uwi, pcp_pump_rod_torque_ftlb tq, lag(pcp_pump_rod_torque_ftlb) over w tq0,
  pcp_pump_electric_current_a cu, lag(pcp_pump_electric_current_a) over w cu0, pcp_pump_rpm rpm, lag(pcp_pump_rpm) over w rpm0
  from '{D}' where well_daily_status='Producing' window w as (partition by uwi order by production_date))
select round(count(tq0)/nullif(sum((tq<>tq0)::int),0),1) torque_days_per_change,
       round(count(cu0)/nullif(sum((cu<>cu0)::int),0),1) current_days_per_change,
       round(count(rpm0)/nullif(sum((rpm<>rpm0)::int),0),1) rpm_days_per_change from t"""))
emit("Downtime ramp before the logged failure date (all failure-log records, day k relative to failure_start_date)", q(f"""
with fl as (select distinct uwi, failure_start_date fd from '{F}')
select date_diff('day', fd, production_date) k, round(avg(hours_down),2) mean_hours_down,
  round(avg((downtime_code_1 is not null)::int),3) share_coded, round(avg(oil_produced_m3),2) mean_oil_m3
from fl join '{D}' d on d.uwi=fl.uwi and d.production_date between fd - interval 14 day and fd + interval 2 day group by 1 order by 1"""))
emit("Producing rows with an 'Uneconomic' downtime code (well flagged Producing but shut in)", q(f"""
select count(*) n_rows, count(distinct uwi) wells, round(sum(lost_oil_m3)) lost_oil_m3
from '{D}' where well_daily_status='Producing' and downtime_code_2='Uneconomic'"""))
emit("Sentinel/implausible value counts used by common.CLEAN", q(f"""
select count(*) filter (where pcp_pump_rod_torque_ftlb>20000) torque_gt20000,
 count(*) filter (where pcp_pump_rpm>1000) rpm_gt1000, count(*) filter (where pcp_pump_electric_current_a>1000) current_gt1000,
 count(*) filter (where tubing_pressure_kpa>20000) tubing_gt20000, count(*) filter (where tubing_pressure_kpa=22598.3) tubing_eq_22598_3,
 count(*) filter (where casing_pressure_kpa=85873.5) casing_eq_85873_5, count(*) filter (where pump_efficiency_pct>3) eff_gt3,
 count(*) filter (where pump_efficiency_pct<0) eff_lt0, count(*) filter (where oil_produced_m3<0) oil_lt0,
 count(*) filter (where water_produced_m3<0) water_lt0 from '{D}'"""))
emit("pcp_pump_make spelling variants", q(f"""
select upper(trim(pcp_pump_make)) mk, count(distinct pcp_pump_make) variants, string_agg(distinct pcp_pump_make, ' | ') spellings
from '{D}' where pcp_pump_make is not null group by 1 having count(distinct pcp_pump_make)>1"""))
emit("failure_type free-text variants (values with <10 rows)", q(f"""
select count(distinct failure_type) n_values, count(*) n_rows from (select failure_type, count(*) c from '{F}' group by 1 having c<10)"""))

(OUT / "profile_results.txt").write_text("".join(_lines), encoding="utf-8")
print(f"\nWrote {OUT / 'profile_results.txt'}", file=sys.stderr)
