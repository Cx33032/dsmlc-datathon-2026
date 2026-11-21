"""Idea 2 - step 1: weekly well snapshots + leakage-safe features + 30-day failure labels.

Run:  python data/ideas/2/build_features.py      (writes data/ideas/2/out/snapshots.parquet)

Snapshot = (well, Monday t). Kept only if the well is Producing and fully UP on t-2, t-1, t
(hours_down = 0 and oil > 0), so the model can never "predict" a failure that has already
taken the well down (the profile showed wells are ~18 h down the day before the logged failure date).
All features use rows with production_date <= t only. Downtime CODES are not used as features
except counts of past downhole-coded days ending at t (those are history, not the upcoming event).
Labels:
  y_job  = a failure-type repair job (rod/pump/tubing repair) starts in (t, t+30]   -> available 2021-2026
  y_flog = a failure-log record (Rods/Pump/Tubing) starts in (t, t+30]             -> complete Jun 2025+
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
con = cm.con()
D, J, F, C = cm.DAILY, cm.JOBS, cm.FAILS, cm.CLEAN
FAIL_JOBS = ["Rod Repair", "Corod Rod Repair", "Stick Rod Repair", "Rod Break - Corod", "Pump Repair/Replacement",
             "Pump Repair", "PCP Replacement", "Tubing Repair"]
REPLACE = ["Corod Rod  Replacement - New String", "Stick Rod Replacement - New String"]
DH = "('Downhole Equipment','Downhole','RODSPART','Down Hole Failure','Unplanned Well - Downhole')"

w = lambda n: f"over (partition by uwi order by dt rows between {n - 1} preceding and current row)"
snap = con.sql(f"""
with d as (
  select uwi, production_date dt, well_daily_status st, hours_down hd, {C['oil']} oil, {C['wat']} wat, {C['eff']} eff,
    {C['rpm']} rpm, {C['tq']} tq, {C['cur']} cur, {C['tbg']} tbg, {C['csg']} csg,
    pcp_pump_displacement_m3d100rpm disp, field_operating_area area, pcp_pump_make make, on_production_date opd,
    (downtime_code_2 in {DH})::int dh, (downtime_code_1 ilike '%torqued%')::int torq,
    (hours_down>0)::int down
  from '{D}' where flow_direction='production'),
f as (
  select *,
    max(hd) {w(3)} hd3, min(oil) {w(3)} oil_min3,
    avg(oil) {w(7)} oil7, avg(oil) {w(30)} oil30, avg(oil) {w(90)} oil90,
    avg(oil+wat) {w(7)} liq7, avg(oil+wat) {w(30)} liq30, avg(oil+wat) {w(90)} liq90,
    sum(wat) {w(30)} wat30s, sum(oil+wat) {w(30)} liq30s,
    avg(eff) {w(7)} eff7, avg(eff) {w(30)} eff30, avg(eff) {w(90)} eff90,
    avg(rpm) {w(7)} rpm7, avg(rpm) {w(90)} rpm90,
    avg(tq) {w(7)} tq7, avg(tq) {w(90)} tq90, max(tq) {w(30)} tqmax30,
    avg(cur) {w(7)} cur7, avg(cur) {w(90)} cur90,
    avg(tbg) {w(7)} tbg7, avg(tbg) {w(90)} tbg90, avg(csg) {w(7)} csg7,
    sum(down) {w(30)} down_days30, sum(down) {w(90)} down_days90, sum(hd) {w(30)} hd30,
    sum(dh) {w(90)} dh_days90, sum(dh) {w(365)} dh_days365, sum(torq) {w(90)} torq_days90,
    regr_slope(oil, epoch(dt)/86400) {w(30)} oil_slope30
  from d)
select uwi, dt t, area, make, disp, date_diff('day', opd, dt)/365.25 well_age_yrs,
  oil7, oil30, oil90, liq7, liq30, liq90, wat30s/nullif(liq30s,0) wc30,
  oil7/nullif(oil30,0) r_oil_7_30, oil30/nullif(oil90,0) r_oil_30_90, liq7/nullif(liq30,0) r_liq_7_30, oil_slope30,
  eff7, eff30, eff7/nullif(eff90,0) r_eff_7_90, rpm7, rpm7-rpm90 d_rpm_7_90,
  tq7, tq7/nullif(tq90,0) r_tq_7_90, tqmax30/nullif(tq90,0) r_tqmax_90, cur7, cur7/nullif(cur90,0) r_cur_7_90,
  tbg7, tbg7-tbg90 d_tbg_7_90, csg7, tq7/nullif(rpm7,0) tq_per_rpm, liq7/nullif(disp*rpm7/100,0) vol_eff7,
  down_days30, down_days90, hd30, dh_days90, dh_days365, torq_days90
from f
where dayofweek(dt)=1 and dt >= '2021-04-05' and dt <= date '{cm.DATA_END}' - interval 30 day
  and st='Producing' and hd3=0 and oil_min3>0
""").df()
print("snapshots:", len(snap))

# ------------------------------------------------------------------ job-history features + labels (numpy per well)
jobs = con.sql(f"""select uwi, start_date::date s, job_type in ({",".join("'" + x + "'" for x in REPLACE)}) is_rpl
   from '{J}' where job_type in ({",".join("'" + x + "'" for x in FAIL_JOBS + REPLACE)}) order by uwi, s""").df()
flog = con.sql(f"""select uwi, failure_start_date::date s from '{F}' where failure_type in ('Rods','Pump','Tubing') order by uwi, s""").df()
fj = {u: g.s.values.astype("datetime64[D]") for u, g in jobs[~jobs.is_rpl].groupby("uwi")}
rj = {u: g.s.values.astype("datetime64[D]") for u, g in jobs[jobs.is_rpl].groupby("uwi")}
fl = {u: g.s.values.astype("datetime64[D]") for u, g in flog.groupby("uwi")}
E = np.array([], dtype="datetime64[D]")

snap["t"] = pd.to_datetime(snap.t)
snap = snap.sort_values(["uwi", "t"]).reset_index(drop=True)
cols = {k: np.full(len(snap), np.nan) for k in
        ["n_fail_90", "n_fail_365", "n_fail_730", "days_since_fail", "days_since_replace", "y_job", "y_flog", "days_to_fail"]}
for u, idx in snap.groupby("uwi").indices.items():
    t = snap.t.values[idx].astype("datetime64[D]")
    a, r, f_ = fj.get(u, E), rj.get(u, E), fl.get(u, E)
    for k, lag in [("n_fail_90", 90), ("n_fail_365", 365), ("n_fail_730", 730)]:
        cols[k][idx] = np.searchsorted(a, t, side="right") - np.searchsorted(a, t - lag, side="right")
    i = np.searchsorted(a, t, side="right") - 1
    cols["days_since_fail"][idx] = np.where(i >= 0, (t - a[np.clip(i, 0, None)]).astype(float) if len(a) else np.nan, np.nan)
    i = np.searchsorted(r, t, side="right") - 1
    cols["days_since_replace"][idx] = np.where(i >= 0, (t - r[np.clip(i, 0, None)]).astype(float) if len(r) else np.nan, np.nan)
    nxt = np.searchsorted(a, t, side="right")
    has = nxt < len(a)
    dnext = np.where(has, (a[np.clip(nxt, 0, len(a) - 1)] - t).astype(float) if len(a) else np.nan, np.nan)
    cols["days_to_fail"][idx] = dnext
    cols["y_job"][idx] = (dnext <= 30).astype(float)
    nf = np.searchsorted(f_, t, side="right")
    dfl = np.where(nf < len(f_), (f_[np.clip(nf, 0, len(f_) - 1)] - t).astype(float) if len(f_) else np.nan, np.nan)
    cols["y_flog"][idx] = (dfl <= 30).astype(float)
for k, v in cols.items():
    snap[k] = v
snap["y_job"] = snap.y_job.fillna(0).astype(int)
snap["y_flog"] = snap.y_flog.fillna(0).astype(int)
snap["area"] = snap.area.astype("category")
snap["make"] = snap.make.str.upper().str.strip().astype("category")
snap.to_parquet(OUT / "snapshots.parquet", index=False)
print(snap.groupby(snap.t.dt.year).agg(n=("uwi", "size"), wells=("uwi", "nunique"), y_job=("y_job", "mean"), y_flog=("y_flog", "mean")).round(4))
