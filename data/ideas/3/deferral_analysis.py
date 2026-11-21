"""Idea 3 - Deferred-production command center: where does recoverable oil go, and is lost_oil_m3 trustworthy?

Run:  python data/ideas/3/deferral_analysis.py
Outputs: data/ideas/3/out/results.txt, charts in docs/ideas/3/assets/

Scope: Producing rows only. 'Uneconomic' codes are excluded from "recoverable" loss (the well is shut in on purpose).
Two code taxonomies are mixed in downtime_code_2 (long names vs short legacy codes such as RODSPART, UNPLNDW);
they are mapped to a common bucket here.
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
IDEA = "3"
con = cm.con()
cm.style()
D = cm.DAILY
lines = []


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


BUCKET = """case
 when downtime_code_2 ilike 'uneco%' or downtime_code_2 in ('Uneconomic','Long Term Shut-In','Long Term Shut In','LTSI:1','Uneconomic - Long Term') then 'Uneconomic / LTSI (excluded)'
 when downtime_code_2 in ('Downhole Equipment','Downhole','RODSPART','PUM','Down Hole Failure','Unplanned Well - Downhole','FFM') then 'Downhole failure'
 when downtime_code_2 in ('Facility','Facility Downtime','ESD','CAPC') or downtime_code_2 ilike '%Plant Facility%' or downtime_code_2 ilike '%Facility Constraint%' or downtime_code_2 ilike '%Pad/Multi-Well%' then 'Facility / battery'
 when downtime_code_2 in ('Power Source/Supply','Sask Power/Grid','ELFAIL') then 'Power'
 when downtime_code_2 in ('Surface Equipment','Surface Equipment Failure','WHSB','EQT','SEM','NEWEQ') or downtime_code_2 ilike '%Surface%' then 'Surface equipment'
 when downtime_code_2 in ('Pipeline','Flowline','TIE') then 'Pipeline / flowline'
 when downtime_code_2 in ('Scheduled','MNT1','WELLSTIM','PLNDOTGSP') or downtime_code_2 ilike 'Planned Well%' then 'Scheduled / turnaround'
 when downtime_code_2 in ('Development','SI:DRILL') or downtime_code_2 ilike 'Concurrent%' then 'Development (drill/frac)'
 else 'Other / unmapped legacy' end"""

base = f"""select uwi, production_date dt, year(production_date) y, facility_name fac, field_operating_area area,
  downtime_code_1 c1, downtime_code_2 c2, {BUCKET} bucket, hours_down hd, lost_oil_m3 lost
  from '{D}' where well_daily_status='Producing' and hours_down > 0"""
con.sql(f"create temp table dt as {base}")

yr_days = con.sql(f"select year(production_date) y, count(distinct production_date) nd from '{D}' group by 1").df().set_index("y").nd
by = con.sql("select y, bucket, sum(lost) lost from dt group by 1,2").df()
by["lost_per_yr"] = by.lost / by.y.map(yr_days) * 365.25
piv = by.pivot(index="y", columns="bucket", values="lost_per_yr").fillna(0)
emit("Lost oil m3/yr (annualised) by bucket and year, Producing rows", piv.round(0))
tot = con.sql("select bucket, sum(lost) lost, sum(hd) hrs, count(*) n_days, count(distinct uwi) wells from dt group by 1 order by lost desc").df()
span_yrs = (pd.Timestamp(cm.DATA_END) - pd.Timestamp("2021-01-01")).days / 365.25 + 1 / 365.25
tot["lost_m3_per_yr"] = tot.lost / span_yrs
tot["CAD_per_yr"] = tot.lost_m3_per_yr * cm.OIL_CAD_M3
emit(f"Totals 2021-2026 by bucket ({span_yrs:.2f} yr span), valued at {cm.OIL_CAD_M3:.0f} CAD/m3", tot.round(0))
rec = tot[~tot.bucket.str.startswith("Uneconomic")]
emit("Recoverable (non-uneconomic) loss", pd.Series({
    "m3_per_yr": rec.lost_m3_per_yr.sum(), "CAD_per_yr": rec.CAD_per_yr.sum(),
    "non_downhole_m3_per_yr": rec[rec.bucket != "Downhole failure"].lost_m3_per_yr.sum(),
    "non_downhole_CAD_per_yr": rec[rec.bucket != "Downhole failure"].CAD_per_yr.sum()}).round(0))
emit("Unmapped downtime_code_2 values (bucket = Other)", con.sql(
    "select c2, count(*) n, round(sum(lost)) lost from dt where bucket='Other / unmapped legacy' group by 1 order by lost desc nulls last limit 15").df())

# ------------------------------------------------------------------ facility Pareto (controllable non-downhole buckets)
fac = con.sql("""select fac, sum(lost) lost, count(distinct uwi) wells,
   sum(lost) filter (where c1='Facility - Limited Capacity') lost_capacity
   from dt where bucket in ('Facility / battery','Power','Surface equipment','Pipeline / flowline','Scheduled / turnaround')
   group by 1 order by lost desc""").df()
fac["share"] = fac.lost / fac.lost.sum()
fac["cum"] = fac.share.cumsum()
emit("Facility Pareto, non-downhole controllable loss (2021-2026)", fac.head(12).round(3))
emit("Facilities needed for 50% / 80% of that loss", f"{(fac.cum < 0.5).sum() + 1} / {(fac.cum < 0.8).sum() + 1} of {len(fac)}")

# ------------------------------------------------------------------ 12-32 battery capacity constraint
cap = con.sql("""select date_trunc('month', dt) m, sum(lost) lost, count(distinct uwi) wells
   from dt where c1='Facility - Limited Capacity' and fac='12-32 BTY Facility' group by 1 order by 1""").df()
cap_y = con.sql("""select y, sum(lost) lost from dt where c1='Facility - Limited Capacity' and fac='12-32 BTY Facility' group by 1 order by 1""").df()
emit("12-32 BTY 'Facility - Limited Capacity' lost oil by year (m3)", cap_y.round(0))
fac_tot = con.sql(f"select sum(oil_produced_m3) oil from '{D}' where facility_name='12-32 BTY Facility' and production_date>='2025-01-01'").df().oil.iloc[0]
emit("12-32 BTY context", pd.Series({"oil_2025_2026_m3": fac_tot,
                                     "capacity_loss_2025_2026_m3": cap_y[cap_y.y >= 2025].lost.sum(),
                                     "loss_pct_of_production": cap_y[cap_y.y >= 2025].lost.sum() / fac_tot}).round(4))

# ------------------------------------------------------------------ is lost_oil_m3 consistent? compare to hours_down x trailing rate
chk = con.sql(f"""
with d as (select uwi, production_date dt, hours_down hd, lost_oil_m3 lost, well_daily_status st, downtime_code_2 c2,
   avg(case when hours_down=0 then oil_produced_m3 end) over (partition by uwi order by production_date rows between 37 preceding and 8 preceding) rate30
   from '{D}' where flow_direction='production')
select *, hd/24*rate30 implied from d where st='Producing' and hd>0 and lost is not null and rate30 is not null and rate30>0""")
con.sql("create temp table chk as select * from chk")
stats = con.sql("""select count(*) n, median(lost/nullif(implied,0)) med_ratio, quantile_cont(lost/nullif(implied,0),0.1) p10,
  quantile_cont(lost/nullif(implied,0),0.9) p90, avg((lost=0)::int) share_zero_lost, corr(lost, implied) corr,
  sum(lost) sum_lost, sum(implied) sum_implied from chk where coalesce(c2,'') not ilike 'uneco%' and coalesce(c2,'')<>'Uneconomic'""").df()
emit("lost_oil_m3 vs implied (hours_down/24 x trailing 8-37 d up-day oil rate), recoverable codes", stats.T.round(3))
samp = con.sql("select lost, implied from chk where coalesce(c2,'')<>'Uneconomic' using sample 20000 rows (reservoir, 7)").df()
zero_by = con.sql("""select coalesce(c2,'<null>') c2, count(*) n, round(avg((lost=0)::int),3) share_zero, round(sum(implied)) implied_when_any
  from chk group by 1 order by n desc limit 8""").df()
emit("Share of down-days with lost_oil_m3 = 0 although the well had a positive trailing rate", zero_by)

# ------------------------------------------------------------------ episode durations by bucket
ep = con.sql("""
with x as (select *, case when lag(dt) over (partition by uwi order by dt) = dt - interval 1 day
                          and lag(bucket) over (partition by uwi order by dt) = bucket then 0 else 1 end newep from dt),
e as (select *, sum(newep) over (partition by uwi order by dt) eid from x)
select bucket, uwi, eid, count(*) ndays, sum(lost) lost from e group by 1,2,3""").df()
eps = ep.groupby("bucket").agg(episodes=("ndays", "size"), median_days=("ndays", "median"), p90_days=("ndays", lambda x: x.quantile(0.9)),
                               mean_lost=("lost", "mean"), share_loss_from_eps_over_7d=("lost", "mean"))
for b in eps.index:
    g = ep[ep.bucket == b]
    eps.loc[b, "share_loss_from_eps_over_7d"] = g[g.ndays > 7].lost.sum() / max(g.lost.sum(), 1e-9)
emit("Downtime episodes by bucket (consecutive down-days, same bucket)", eps.round(2))

# ------------------------------------------------------------------ charts
order = [c for c in ["Downhole failure", "Facility / battery", "Development (drill/frac)", "Surface equipment",
                     "Scheduled / turnaround", "Power", "Pipeline / flowline", "Other / unmapped legacy"] if c in piv.columns]
colors = [cm.C4, cm.C1, "#7a6fb0", cm.C2, cm.C3, "#e3b23c", "#5aa5c8", cm.GREY]
fig, ax = plt.subplots()
bottom = np.zeros(len(piv))
for c, col in zip(order, colors):
    ax.bar(piv.index.astype(str), piv[c] / 1e3, bottom=bottom / 1e3, color=col, label=c)
    bottom += piv[c].values
ax.set_xlabel("Year (2026 annualised from Jan-Oct)")
ax.set_ylabel("Recoverable lost oil (thousand m3 / year)")
ax.set_title("Recoverable deferral ~%.0fk m3/yr (~$%.0fM/yr): downhole failures and facility constraints lead" %
             (rec.lost_m3_per_yr.sum() / 1e3, rec.CAD_per_yr.sum() / 1e6))
ax.legend(frameon=False, fontsize=8.5, ncol=2, loc="upper left")
cm.save(fig, IDEA, "3a_deferral_by_bucket_year.png")

fig, ax = plt.subplots()
top = fac.head(15)
ax.bar(range(len(top)), top.lost / 1e3, color=cm.C1)
ax2 = ax.twinx()
ax2.plot(range(len(top)), top.cum * 100, color=cm.C4, marker="o")
ax2.set_ylim(0, 105)
ax2.set_ylabel("Cumulative share of facility-side loss (%)")
ax2.grid(False)
ax.set_xticks(range(len(top)), [f[:22] for f in top.fac], rotation=60, ha="right", fontsize=8)
ax.set_ylabel("Lost oil 2021-26, non-downhole buckets (thousand m3)")
ax.set_title("One battery (12-32 BTY) is %.0f%% of all facility/power/surface/pipeline loss" % (fac.share.iloc[0] * 100))
cm.save(fig, IDEA, "3b_facility_pareto.png")

fig, ax = plt.subplots()
ax.bar(pd.to_datetime(cap.m), cap.lost, width=25, color=cm.C1, label="lost oil (m3/month)")
ax2 = ax.twinx()
ax2.plot(pd.to_datetime(cap.m), cap.wells, color=cm.C2, lw=1.8, label="wells curtailed in month")
ax2.set_ylabel("Wells curtailed (count)")
ax2.grid(False)
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper left")
ax.set_xlabel("Month")
ax.set_ylabel("Lost oil, 'Facility - Limited Capacity' (m3/month)")
ax.set_title("12-32 battery capacity curtailment is growing: a debottleneck case worth ~$%.1fM/yr" %
             (cap_y[cap_y.y == 2025].lost.iloc[0] * cm.OIL_CAD_M3 / 1e6))
cm.save(fig, IDEA, "3c_1232_capacity_trend.png")

fig, ax = plt.subplots()
lim = np.nanpercentile(samp[["lost", "implied"]].values, 99)
ax.scatter(samp.implied, samp.lost, s=4, alpha=0.25, color=cm.C1)
ax.plot([0, lim], [0, lim], color=cm.C4, ls="--", lw=1.2, label="lost = hours_down/24 x trailing rate")
ax.set_xlim(0, lim)
ax.set_ylim(0, lim)
ax.set_xlabel("Implied lost oil = hours_down/24 x trailing 30-d oil rate (m3)")
ax.set_ylabel("Reported lost_oil_m3 (m3)")
ax.set_title("lost_oil_m3 matches a rate-based estimate in total (ratio %.2f) but scatters day to day (p10-p90 %.2f-%.2f)"
             % (stats.sum_lost.iloc[0] / stats.sum_implied.iloc[0], stats.p10.iloc[0], stats.p90.iloc[0]))
ax.legend(frameon=False)
cm.save(fig, IDEA, "3d_lost_oil_validation.png")

(OUT / "results.txt").write_text("".join(lines), encoding="utf-8")
