"""Idea 4 - evidence for an edge "rod-string fatigue odometer": what the current data cannot see.

Run:  python data/ideas/4/edge_gap_analysis.py
Outputs: data/ideas/4/out/gap_results.txt, charts 4a-4c in docs/ideas/4/assets/

Questions tested:
  1. How stale are the load tags (torque, current, RPM) that a fatigue model would need?
  2. Is there an invisible "limp" before rod failures (well running but under-producing) that a fast
     detector could catch?  Compared against control windows on the same wells.
  3. Is the pre-failure loss a DETECTION problem (nobody knows the rod broke) or a REPAIR-QUEUE problem
     (the rod is known broken and the well waits)?
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
IDEA = "4"
con = cm.con()
cm.style()
D, F, J, C = cm.DAILY, cm.FAILS, cm.JOBS, cm.CLEAN
lines = []


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


# ------------------------------------------------------------------ 1. tag staleness: run lengths of identical consecutive values
runs = {}
for name, expr in [("torque", C["tq"]), ("current", C["cur"]), ("rpm", C["rpm"]), ("tubing_pressure", C["tbg"]), ("oil", C["oil"])]:
    r = con.sql(f"""
    with t as (select uwi, production_date dt, {expr} v from '{D}' where well_daily_status='Producing'),
    t2 as (select *, case when v is distinct from lag(v) over (partition by uwi order by dt)
                           or lag(dt) over (partition by uwi order by dt) <> dt - interval 1 day then 1 else 0 end brk from t where v is not null),
    t3 as (select *, sum(brk) over (partition by uwi order by dt) rid from t2)
    select count(*) run_len from t3 group by uwi, rid""").df()
    runs[name] = r.run_len.values
st = pd.DataFrame({k: {"runs": len(v), "median_run_days": np.median(v),
                       "day_weighted_median_run": np.median(np.repeat(v, v)) if len(v) < 3e6 else np.nan,
                       "share_of_days_in_runs_ge_7d": v[v >= 7].sum() / v.sum(),
                       "share_of_days_in_runs_ge_30d": v[v >= 30].sum() / v.sum()} for k, v in runs.items()}).T
emit("Run length of identical consecutive daily values (Producing rows, non-null)", st.round(3))

# ------------------------------------------------------------------ 2+3. failure windows vs control windows
fails = con.sql(f"""select distinct uwi, failure_start_date::date fd from '{F}'
   where failure_type='Rods' and failure_start_date >= date '{cm.FAIL_LOG_START}' + interval 60 day""").df()
allf = con.sql(f"select uwi, failure_start_date::date fd from '{F}'").df()
# deterministic controls: each failed well's dates 90 and 150 days before/after its failures,
# kept only if no failure of any type within +-60 days and inside the complete failure-log window
cand = pd.concat([fails.assign(fd=pd.to_datetime(fails.fd) + pd.Timedelta(days=o)) for o in (-150, -90, 90, 150)])
cand = cand[(cand.fd >= pd.Timestamp(cm.FAIL_LOG_START) + pd.Timedelta(days=60)) & (cand.fd <= pd.Timestamp(cm.DATA_END) - pd.Timedelta(days=3))]
fm = {u: pd.to_datetime(g.fd).values for u, g in allf.groupby("uwi")}
keep = [np.all(np.abs((fm[u] - np.datetime64(d)) / np.timedelta64(1, "D")) > 60) for u, d in zip(cand.uwi, cand.fd)]
ctrl = cand[keep].drop_duplicates()
ev = pd.concat([fails.assign(kind="rod failure"), ctrl.assign(fd=ctrl.fd.dt.date, kind="control")])
ev["eid"] = np.arange(len(ev))
con.register("ev", ev)
emit("Windows", ev.kind.value_counts())

tl = con.sql(f"""
select ev.kind, date_diff('day', ev.fd, d.production_date) k, avg(d.hours_down) hours_down,
  avg(coalesce(d.downtime_code_1 in ('Downhole Equipment - Rods','ALL - Downhole - Rodstring Failure'), false)::int) share_rod_coded,
  avg((d.hours_down>0)::int) share_down
from ev join '{D}' d on d.uwi=ev.uwi and d.production_date between ev.fd - interval 14 day and ev.fd + interval 2 day
group by 1,2 order by 1,2""").df()
emit("Daily timeline around rod failures vs control windows", tl.pivot(index="k", columns="kind").round(3))

dec = con.sql(f"""
with x as (select ev.eid, ev.kind, date_diff('day', ev.fd, d.production_date) k, d.hours_down hd, {C['oil']} oil, d.lost_oil_m3 lost,
     d.downtime_code_1 c1
   from ev join '{D}' d on d.uwi=ev.uwi and d.production_date between ev.fd - interval 60 day and ev.fd - interval 1 day),
b as (select eid, avg(oil) filter (where k between -60 and -31 and hd=0) base from x group by 1),
w as (select x.eid, any_value(kind) kind,
   sum(greatest(base-oil,0)) filter (where k>=-14) deficit_all,
   coalesce(sum(greatest(base-oil,0)) filter (where k>=-14 and hd=0),0) deficit_up_days,
   sum(coalesce(lost,0)) filter (where k>=-14) reported_lost,
   coalesce(sum(coalesce(lost,0)) filter (where k>=-14 and c1 in ('Downhole Equipment - Rods','ALL - Downhole - Rodstring Failure')),0) reported_lost_rod_coded,
   count(*) filter (where k>=-14 and c1 in ('Downhole Equipment - Rods','ALL - Downhole - Rodstring Failure')) rod_coded_days
 from x join b using(eid) where base > 0.5 group by 1)
select kind, count(*) n, avg(deficit_all) deficit_all_m3, avg(deficit_up_days) deficit_on_running_days_m3,
  avg(reported_lost) reported_lost_m3, avg(reported_lost_rod_coded) reported_lost_rod_coded_m3, avg(rod_coded_days) rod_coded_days
from w group by 1 order by 1""").df().set_index("kind")
emit("Production deficit vs own day -60..-31 baseline, days -14..-1 (mean per window)", dec.round(2))
exc = dec.loc["rod failure"] - dec.loc["control"]
emit("Excess over control, per rod failure", exc.round(2))
first_down = con.sql(f"""
select ev.kind, median(k) med_first_down_day, avg(any_down) share_with_any_down
from (select ev.eid, any_value(ev.kind) kind, min(date_diff('day', ev.fd, d.production_date)) filter (where d.hours_down>0) k,
        max((d.hours_down>0)::int) any_down
      from ev join '{D}' d on d.uwi=ev.uwi and d.production_date between ev.fd - interval 14 day and ev.fd - interval 1 day group by ev.eid) t
join ev using(eid) group by 1""").df()
emit("First down-day in the 14 days before the window date", first_down.round(3))

# ------------------------------------------------------------------ chronic well example
U = "109101004225W300"
wd = con.sql(f"""select production_date dt, {C['oil']} oil, {C['tq']} tq, {C['cur']} cur, hours_down
   from '{D}' where uwi='{U}' and production_date >= '2025-06-01' order by 1""").df()
wf = con.sql(f"select failure_start_date dt, cause from '{F}' where uwi='{U}' and failure_start_date >= '2025-06-01'").df()
tq_changes = int((wd.tq.diff().fillna(0) != 0).sum())
emit(f"Example well {U} (Jun 2025 - Oct 2026)", pd.Series({"days": len(wd), "rod_failures_logged": len(wf),
     "torque_non_null_days": int(wd.tq.notna().sum()), "torque_value_changes": tq_changes,
     "distinct_torque_values": int(wd.tq.nunique())}))

# ------------------------------------------------------------------ charts
fig, ax = plt.subplots()
for (name, v), col in zip(runs.items(), [cm.C4, cm.C2, cm.C1, cm.C3, cm.GREY]):
    x = np.sort(np.repeat(v, v))       # day-weighted: for a random producing day, how long has the value been held?
    x = x[:: max(1, len(x) // 20000)]
    ax.plot(x, np.linspace(0, 1, len(x)), color=col, lw=2.2 if name != "oil" else 1.5, ls="-" if name != "oil" else "--", label=name)
ax.set_xscale("log")
ax.set_xlabel("Length of the run of identical daily values the day belongs to (days, log scale)")
ax.set_ylabel("Cumulative share of producing well-days")
ax.set_title("Load tags are held for weeks; daily oil changes every day: the historian cannot see load cycles")
ax.legend(frameon=False, loc="lower right")
cm.save(fig, IDEA, "4a_tag_staleness.png")

fig, ax = plt.subplots()
p = tl.pivot(index="k", columns="kind")
ax.plot(p.index, p["hours_down"]["rod failure"], color=cm.C4, lw=2.4, marker="o", label="hours down - rod failure windows")
ax.plot(p.index, p["hours_down"]["control"], color=cm.GREY, lw=1.8, marker="o", label="hours down - control windows")
ax2 = ax.twinx()
ax2.plot(p.index, p["share_rod_coded"]["rod failure"] * 100, color=cm.C1, lw=2, ls="--", label="% of wells already coded 'Rods' downtime")
ax2.set_ylabel("Wells with a rod downtime code that day (%)")
ax2.grid(False)
ax.axvline(0, color="black", lw=0.8)
ax.set_xlabel("Days relative to the logged rod failure date")
ax.set_ylabel("Mean hours down per day")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left", fontsize=9)
ax.set_title("Before the failure is logged the well is already down AND coded 'Rods':\nthe loss is a repair queue, not a detection gap")
cm.save(fig, IDEA, "4b_prefailure_timeline.png")

fig, ax = plt.subplots()
ax.plot(pd.to_datetime(wd.dt), wd.oil, color=cm.C3, lw=1, label="oil (m3/d)")
ax.set_ylabel("Oil (m3/day)")
ax2 = ax.twinx()
ax2.step(pd.to_datetime(wd.dt), wd.tq, where="post", color=cm.C1, lw=2, label="rod torque tag (ft-lb)")
ax2.set_ylabel("Rod torque tag (ft-lb)")
ax2.grid(False)
for dt in pd.to_datetime(wf.dt):
    ax.axvline(dt, color=cm.C4, lw=1, alpha=0.7)
ax.set_xlabel("Date")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2 + [plt.Line2D([], [], color=cm.C4)], l1 + l2 + ["logged rod failure"], frameon=False, loc="upper right", fontsize=9)
ax.set_title(f"Worst chronic well: {len(wf)} rod failures, torque tag changed {tq_changes} times in {len(wd)} days")
cm.save(fig, IDEA, "4c_chronic_well_blind_spot.png")

(OUT / "gap_results.txt").write_text("".join(lines), encoding="utf-8")
