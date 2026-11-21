"""Idea 1 - Rod string: repair or replace?  Chronic-failure well program.

Run:  python data/ideas/1/rod_replace_analysis.py
Outputs: data/ideas/1/out/results.txt, data/ideas/1/out/chronic_wells.csv, charts in docs/ideas/1/assets/

Unit of analysis = one downhole rod job (deduplicated within 3 days per well).
  repair  = Rod Repair / Corod Rod Repair / Stick Rod Repair / Rod Break - Corod
  replace = Corod / Stick Rod Replacement - New String
Outcome  = number of rod REPAIR jobs on the same well in the following 365 days, per producing year,
           and time-to-next-rod-repair (Kaplan-Meier + Cox with prior failure history as covariate).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import SurvfuncRight

OUT = cm.out_dir(__file__, "1")
IDEA = "1"
con = cm.con()
cm.style()
D, J, F, C = cm.DAILY, cm.JOBS, cm.FAILS, cm.CLEAN
lines = []


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


REPAIR = ["Rod Repair", "Corod Rod Repair", "Stick Rod Repair", "Rod Break - Corod"]
REPLACE = ["Corod Rod  Replacement - New String", "Stick Rod Replacement - New String"]
FAIL_JOBS = REPAIR + ["Pump Repair/Replacement", "Pump Repair", "PCP Replacement", "Tubing Repair"]
DOWNHOLE_CODES = "('Downhole Equipment','Downhole','RODSPART','Down Hole Failure','Unplanned Well - Downhole')"

# ------------------------------------------------------------------ 1. job events + per-event lost oil
jobs = con.sql(f"""
select uwi, start_date::date s, coalesce(end_date, start_date)::date e, job_category, job_type, field_est_total cost
from '{J}' where job_type in ({",".join("'" + x + "'" for x in REPAIR + REPLACE)})
order by uwi, s""").df()
# dedupe: same well, jobs starting within 3 days of a kept job are one event; replace wins over repair
jobs["is_replace"] = jobs.job_type.isin(REPLACE).astype(int)
ev = []
for uwi, g in jobs.groupby("uwi", sort=False):
    cur = None
    for r in g.itertuples(index=False):
        if cur is not None and (r.s - cur["s"]).days <= 3:
            cur["cost"] += r.cost if pd.notna(r.cost) else 0
            cur["is_replace"] = max(cur["is_replace"], r.is_replace)
            cur["e"] = max(cur["e"], r.e)
            continue
        if cur is not None:
            ev.append(cur)
        cur = dict(uwi=uwi, s=r.s, e=r.e, cost=r.cost if pd.notna(r.cost) else 0, is_replace=r.is_replace,
                   corod=int("Corod" in r.job_type), stick=int("Stick" in r.job_type))
    ev.append(cur)
ev = pd.DataFrame(ev)
ev["eid"] = np.arange(len(ev))
emit("Rod job rows -> deduplicated events", f"{len(jobs)} job rows -> {len(ev)} events "
     f"({ev.is_replace.sum()} replacements, {(1 - ev.is_replace).sum()} repairs), wells={ev.uwi.nunique()}")
con.register("ev", ev)

lost = con.sql(f"""
select ev.eid, coalesce(sum(d.lost_oil_m3),0) lost_m3
from ev left join '{D}' d on d.uwi=ev.uwi and d.production_date between ev.s - interval 7 day and ev.e + interval 1 day
   and d.downtime_code_2 in {DOWNHOLE_CODES}
group by 1""").df()
ev = ev.merge(lost, on="eid")

# per-well censoring date = last day the well was Producing in the data
last_prod = con.sql(f"select uwi, max(production_date)::date last_prod from '{D}' where well_daily_status='Producing' group by 1").df()
ev = ev.merge(last_prod, on="uwi", how="left")
ev = ev[ev.last_prod.notna()].copy()

# ------------------------------------------------------------------ 2. prior history and next-365 outcome
ev = ev.sort_values(["uwi", "s"]).reset_index(drop=True)
rep = ev[ev.is_replace == 0][["uwi", "s"]]
prior, nxt365, t_next, event = [], [], [], []
rep_by_well = {u: g.s.values for u, g in rep.groupby("uwi")}
for r in ev.itertuples(index=False):
    arr = rep_by_well.get(r.uwi, np.array([], dtype="datetime64[ns]"))
    s = np.datetime64(r.s)
    prior.append(int(((arr < s) & (arr >= s - np.timedelta64(365, "D"))).sum()))
    later = arr[arr > s + np.timedelta64(3, "D")]
    end = np.datetime64(r.last_prod)
    if len(later) and later[0] <= end:
        t_next.append(int((later[0] - s) / np.timedelta64(1, "D")))
        event.append(1)
    else:
        t_next.append(max(int((end - s) / np.timedelta64(1, "D")), 1))
        event.append(0)
    nxt365.append(int(((later > s) & (later <= s + np.timedelta64(365, "D"))).sum()))
ev["prior365"], ev["next365"], ev["t_next"], ev["event"] = prior, nxt365, t_next, event

# producing-day exposure in the 365 days after each event (wells get suspended)
expo = con.sql(f"""
select ev.eid, count(*) prod_days from ev join '{D}' d on d.uwi=ev.uwi
  and d.production_date > ev.s + interval 3 day and d.production_date <= ev.s + interval 365 day
  and d.well_daily_status='Producing'
group by 1""").df()
ev = ev.merge(expo, on="eid", how="left").fillna({"prod_days": 0})
# events from 2022 on only: 2021 events have left-censored prior history (data starts 2021-01-01)
HIST_START = pd.Timestamp("2022-01-01")
full = ev[(pd.to_datetime(ev.s) >= HIST_START) & (pd.to_datetime(ev.s) <= pd.Timestamp(cm.DATA_END) - pd.Timedelta(days=365))
          & (ev.prod_days >= 90)].copy()
full["rate_next"] = full.next365 / (full.prod_days / 365.0)
full["prior_bin"] = pd.cut(full.prior365, [-1, 0, 1, 2, 4, 100], labels=["0", "1", "2", "3-4", "5+"])

tab = (full.groupby(["prior_bin", "is_replace"], observed=True)
       .agg(n=("eid", "size"), repairs=("next365", "sum"), prod_yrs=("prod_days", lambda x: x.sum() / 365))
       .reset_index())
tab["rate"] = tab.repairs / tab.prod_yrs
tab["lo"] = tab.apply(lambda r: max(r.repairs - 1.96 * np.sqrt(r.repairs), 0) / r.prod_yrs, axis=1)
tab["hi"] = tab.apply(lambda r: (r.repairs + 1.96 * np.sqrt(max(r.repairs, 1))) / r.prod_yrs, axis=1)
emit("Rod repairs per producing-year in the 365 d after the event, by prior-365d repair count and action "
     "(events 2022-01-01 to 2025-10-27 with full 365 d window, >=90 producing days)", tab.round(3))

# ------------------------------------------------------------------ 3. Cox model: replace vs repair adjusting for history
cov = con.sql(f"""
select ev.eid, avg({C['rpm']}) rpm30, avg({C['oil']}+{C['wat']}) liq30, avg({C['wat']}/nullif({C['oil']}+{C['wat']},0)) wc30,
  any_value(d.field_operating_area) area
from ev join '{D}' d on d.uwi=ev.uwi and d.production_date between ev.s - interval 37 day and ev.s - interval 8 day
group by 1""").df()
m = ev.merge(cov, on="eid", how="inner")
m = m[m.rpm30.notna() & m.liq30.notna() & (pd.to_datetime(m.s) >= HIST_START)].copy()
m["log_prior"] = np.log1p(m.prior365)
m["rpm100"] = m.rpm30 / 100
m["log_liq"] = np.log1p(m.liq30)
m["year"] = pd.to_datetime(m.s).dt.year
m["t_next"] = m.t_next.clip(upper=730)
m.loc[m.t_next >= 730, "event"] = 0
X = m[["is_replace", "log_prior", "rpm100", "log_liq"]].astype(float)
mod = PHReg(m.t_next.astype(float), X, status=m.event.astype(float), strata=m.area.astype(str) + "_" + m.year.astype(str)).fit()
hr = pd.DataFrame({"HR": np.exp(mod.params), "HR_lo": np.exp(mod.conf_int()[:, 0]), "HR_hi": np.exp(mod.conf_int()[:, 1]),
                   "p": mod.pvalues}, index=X.columns)
emit(f"Cox PH: hazard of next rod repair (n={len(m)}, events={int(m.event.sum())}, stratified by area x year, events 2022+, follow-up capped 730 d)",
     hr.round(4))
# chronic-only model
mc = m[m.prior365 >= 2]
modc = PHReg(mc.t_next.astype(float), mc[["is_replace", "log_prior", "rpm100", "log_liq"]].astype(float),
             status=mc.event.astype(float), strata=mc.area.astype(str)).fit()
hrc = pd.DataFrame({"HR": np.exp(modc.params), "HR_lo": np.exp(modc.conf_int()[:, 0]), "HR_hi": np.exp(modc.conf_int()[:, 1]),
                    "p": modc.pvalues}, index=["is_replace", "log_prior", "rpm100", "log_liq"])
emit(f"Cox PH chronic wells only (prior365 >= 2; n={len(mc)}, replacements={int(mc.is_replace.sum())})", hrc.round(4))

# ------------------------------------------------------------------ 4. cost inputs
cost_rep = ev[ev.is_replace == 0].cost.median()
cost_rpl = ev[ev.is_replace == 1].cost.median()
lost_rep_mean = ev[ev.is_replace == 0].lost_m3.mean()
cost_inputs = pd.DataFrame({
    "median_job_cost_repair_CAD": [cost_rep], "median_job_cost_replace_CAD": [cost_rpl],
    "mean_cost_repair_CAD": [ev[ev.is_replace == 0].cost.mean()], "mean_cost_replace_CAD": [ev[ev.is_replace == 1].cost.mean()],
    "mean_lost_oil_per_repair_m3": [lost_rep_mean], "median_lost_oil_per_repair_m3": [ev[ev.is_replace == 0].lost_m3.median()],
    "share_repair_cost_zero": [(ev[ev.is_replace == 0].cost <= 0).mean()],
    "oil_CAD_m3": [cm.OIL_CAD_M3]})
emit("Cost inputs (all events 2021-2026)", cost_inputs.T.round(2))
# Repair cost: use mean of repairs with cost>0 since 2023 (older 'Rod Repair' rows often carry $0)
cost_rep_pos = ev[(ev.is_replace == 0) & (ev.cost > 0) & (pd.to_datetime(ev.s) >= "2023-01-01")].cost.mean()
cost_rpl_pos = ev[(ev.is_replace == 1) & (ev.cost > 0)].cost.mean()
fail_cost = cost_rep_pos + lost_rep_mean * cm.OIL_CAD_M3
emit("Unit economics used", pd.Series({
    "repair_job_cost_mean_CAD (cost>0, 2023+)": cost_rep_pos, "replace_job_cost_mean_CAD (cost>0)": cost_rpl_pos,
    "lost_oil_value_per_repair_CAD": lost_rep_mean * cm.OIL_CAD_M3, "all_in_cost_per_rod_failure_CAD": fail_cost,
    "incremental_cost_replace_vs_repair_CAD": cost_rpl_pos - cost_rep_pos}).round(0))

# ------------------------------------------------------------------ 5. chronic wells now and program value
asof = pd.Timestamp(cm.DATA_END)
recent = ev[(pd.to_datetime(ev.s) > asof - pd.Timedelta(days=365))]
last_replace = ev[ev.is_replace == 1].groupby("uwi").s.max()
chronic = (recent[recent.is_replace == 0].groupby("uwi")
           .agg(repairs_last365=("eid", "size"), repair_cost_last365=("cost", "sum"), lost_m3_last365=("lost_m3", "sum")).reset_index())
chronic["last_replace"] = chronic.uwi.map(last_replace)
chronic["replaced_last365"] = (pd.to_datetime(chronic.last_replace) > asof - pd.Timedelta(days=365)).fillna(False)
area = con.sql(f"select uwi, any_value(field_operating_area) area from '{D}' group by 1").df()
chronic = chronic.merge(area, on="uwi", how="left")
cause = con.sql(f"""select uwi, mode(cause) top_cause, count(*) n_fail_log,
   round(avg(case when cause='Corrosion' then 1.0 else 0 end),2) corrosion_share
   from '{F}' where failure_type='Rods' group by 1""").df()
chronic = chronic.merge(cause, on="uwi", how="left")
chronic["all_in_cost_last365_CAD"] = chronic.repair_cost_last365 + chronic.lost_m3_last365 * cm.OIL_CAD_M3

# Rates for repair vs replace for chronic wells (prior365 >= 3 events) from the table above
def pooled(df):
    return df.repairs.sum() / df.prod_yrs.sum()
t3 = tab[tab.prior_bin.isin(["3-4", "5+"])]
r_repair = pooled(t3[t3.is_replace == 0])
r_replace = pooled(t3[t3.is_replace == 1])
hr_rep = hrc.loc["is_replace", "HR"]
emit("Next-365 rod repair rate for chronic events (prior >= 3)", pd.Series({
    "after_repair_per_yr": r_repair, "after_replace_per_yr": r_replace,
    "raw_reduction": 1 - r_replace / r_repair, "cox_HR_chronic": hr_rep}).round(3))

# Break-even: replacing at the next failure on a well that fails lambda times/yr.
# avoided failures/yr = lambda * (1 - HR). Use Cox HR (adjusted) as the central estimate.
lam = np.linspace(0.5, 12, 200)
inc_cost = cost_rpl_pos - cost_rep_pos
H = 2.0   # years of benefit counted (conservative vs typical rod string life) - assumption
net = lam * (1 - hr_rep) * H * fail_cost - inc_cost
breakeven = inc_cost / ((1 - hr_rep) * H * fail_cost)
emit("Break-even failure rate for replacement (failures/yr), 2-yr horizon", f"{breakeven:.2f}")

# Program: chronic wells (>=3 repairs last 365 d) not replaced in last 365 d
prog = chronic[(chronic.repairs_last365 >= 3) & (~chronic.replaced_last365)].copy()
prog["avoided_fail_2y"] = prog.repairs_last365 * (1 - hr_rep) * H
prog["net_value_2y_CAD"] = prog.avoided_fail_2y * fail_cost - inc_cost
prog = prog.sort_values("net_value_2y_CAD", ascending=False)
prog.to_csv(OUT / "chronic_wells.csv", index=False)
emit("Program: chronic wells (>=3 rod repairs in last 365 d, no replacement in last 365 d)", pd.Series({
    "wells": len(prog), "repairs_last365": prog.repairs_last365.sum(),
    "all_in_cost_last365_CAD": prog.all_in_cost_last365_CAD.sum(),
    "replacement_capex_incremental_CAD": len(prog) * inc_cost,
    "avoided_failures_2y": prog.avoided_fail_2y.sum(),
    "net_value_2y_CAD": prog.net_value_2y_CAD.sum(),
    "net_value_2y_CAD_if_raw_rate_reduction": (prog.repairs_last365 * (1 - r_replace / r_repair) * H * fail_cost - inc_cost).sum(),
    "net_value_2y_CAD_if_HR_upper_CI": (prog.repairs_last365 * (1 - hrc.loc['is_replace', 'HR_hi']) * H * fail_cost - inc_cost).sum(),
    "wells_with_positive_value": int((prog.net_value_2y_CAD > 0).sum()),
    "top_cause_corrosion_wells": int((prog.top_cause == "Corrosion").sum()),
    "top_cause_fatigue_wells": int((prog.top_cause == "Fatigue").sum())}).round(1))

# Sensitivity of break-even and program net value to the key assumptions
lost_med = ev[ev.is_replace == 0].lost_m3.median()
scen = []
for name, hr_s, fc, ic, h in [
    ("central", hr_rep, fail_cost, inc_cost, H),
    ("HR at upper 95% CI", hrc.loc["is_replace", "HR_hi"], fail_cost, inc_cost, H),
    ("lost oil = median per event", hr_rep, cost_rep_pos + lost_med * cm.OIL_CAD_M3, inc_cost, H),
    ("lost oil ignored (job cost only)", hr_rep, cost_rep_pos, inc_cost, H),
    ("oil price -30%", hr_rep, cost_rep_pos + lost_rep_mean * cm.OIL_CAD_M3 * 0.7, inc_cost, H),
    ("incremental replace cost x2", hr_rep, fail_cost, inc_cost * 2, H),
    ("1-year horizon", hr_rep, fail_cost, inc_cost, 1.0),
    ("worst combo: HR upper CI, job cost only, cost x2, 1 yr", hrc.loc["is_replace", "HR_hi"], cost_rep_pos, inc_cost * 2, 1.0),
]:
    be = ic / ((1 - hr_s) * h * fc)
    nv = (prog.repairs_last365 * (1 - hr_s) * h * fc - ic).sum()
    scen.append(dict(scenario=name, HR=hr_s, failure_cost_CAD=fc, incremental_cost_CAD=ic, horizon_yr=h,
                     breakeven_failures_per_yr=be, program_net_CAD=nv, wells_positive=int((prog.repairs_last365 * (1 - hr_s) * h * fc - ic > 0).sum())))
emit("Sensitivity (145 program wells)", pd.DataFrame(scen).round(3).to_string(index=False))

emit("Top 15 program wells",prog.head(15)[["uwi", "area", "repairs_last365", "all_in_cost_last365_CAD", "top_cause",
                                            "corrosion_share", "net_value_2y_CAD"]].round(0))

# ------------------------------------------------------------------ 6. cost concentration (2021-2026, all failure-type jobs + lost oil)
wc = con.sql(f"""
with j as (select uwi, sum(field_est_total) cost, count(*) n from '{J}' where job_type in ({",".join("'" + x + "'" for x in FAIL_JOBS + REPLACE)}) group by 1),
l as (select uwi, sum(lost_oil_m3) lost from '{D}' where well_daily_status='Producing' and downtime_code_2 in {DOWNHOLE_CODES} group by 1)
select j.uwi, j.n, j.cost + coalesce(l.lost,0)*{cm.OIL_CAD_M3} allin from j left join l using (uwi) order by allin desc""").df()
wc["cum_share"] = wc.allin.cumsum() / wc.allin.sum()
wc["well_share"] = np.arange(1, len(wc) + 1) / len(wc)
top10 = wc[wc.well_share <= 0.10].allin.sum() / wc.allin.sum()
emit("All-in downhole failure cost concentration 2021-2026 (repair jobs + lost oil @ field-gate price)", pd.Series({
    "wells": len(wc), "total_allin_MCAD": wc.allin.sum() / 1e6, "top10pct_share": top10,
    "top20pct_share": wc[wc.well_share <= 0.20].allin.sum() / wc.allin.sum(),
    "top10pct_wells": int((wc.well_share <= 0.10).sum())}).round(3))

# ------------------------------------------------------------------ charts
# A: Lorenz / Pareto
fig, ax = plt.subplots()
ax.plot(wc.well_share * 100, wc.cum_share * 100, color=cm.C1, lw=2.5)
ax.plot([0, 100], [0, 100], color=cm.GREY, ls="--", lw=1)
ax.axvline(10, color=cm.C4, ls=":", lw=1.2)
ax.annotate(f"top 10% of wells\n= {top10:.0%} of cost", xy=(10, top10 * 100), xytext=(22, top10 * 100 - 18),
            arrowprops=dict(arrowstyle="->", color=cm.C4), color=cm.C4)
ax.set_xlabel("Wells ranked by all-in downhole failure cost (% of wells)")
ax.set_ylabel("Cumulative share of all-in cost (%)")
top20 = wc[wc.well_share <= 0.20].allin.sum() / wc.allin.sum()
ax.set_title(f"Downhole failure cost is concentrated: top 10% of wells = {top10:.0%}, top 20% = {top20:.0%} "
             f"of ${wc.allin.sum() / 1e6:.0f}M (2021-26)")
cm.save(fig, IDEA, "1a_cost_concentration.png")

# B: next-365 rate by prior bin and action
fig, ax = plt.subplots()
bins = ["0", "1", "2", "3-4", "5+"]
xs = np.arange(len(bins))
for k, (lab, col, off) in enumerate([("after a repair", cm.C2, -0.17), ("after a new rod string", cm.C1, 0.17)]):
    t = tab[tab.is_replace == k].set_index("prior_bin").reindex(bins)
    ax.bar(xs + off, t.rate, width=0.34, color=col, label=lab)
    ax.errorbar(xs + off, t.rate, yerr=[t.rate - t.lo, t.hi - t.rate], fmt="none", ecolor="black", lw=0.8, capsize=3)
    for x, n in zip(xs + off, t.n):
        if pd.notna(n):
            ax.text(x, 0.05, f"n={int(n)}", ha="center", va="bottom", fontsize=8, rotation=90, color="white")
ax.set_xticks(xs, [f"{b}" for b in bins])
ax.set_xlabel("Rod repairs on the well in the 365 days BEFORE the job")
ax.set_ylabel("Rod repairs per producing year, next 365 days")
ax.set_title("At every failure-history level, wells that got a new string fail less in the following year")
ax.legend(frameon=False)
cm.save(fig, IDEA, "1b_next_year_rate_by_history.png")

# C: Kaplan-Meier chronic wells
fig, ax = plt.subplots()
mc_all = ev[(ev.prior365 >= 2) & (pd.to_datetime(ev.s) >= HIST_START)].copy()
mc_all["t"] = mc_all.t_next.clip(upper=730)
mc_all.loc[mc_all.t_next > 730, "event"] = 0
for k, (lab, col) in enumerate([("repair", cm.C2), ("new rod string", cm.C1)]):
    g = mc_all[mc_all.is_replace == k]
    sf = SurvfuncRight(g.t.astype(float), g.event.astype(float))
    ax.step(sf.surv_times, sf.surv_prob, where="post", color=col, lw=2.2, label=f"{lab} (n={len(g)})")
    med = g.t[g.event == 1].median()
ax.set_xlabel("Days since the rod job")
ax.set_ylabel("Share of wells with no further rod repair")
ax.set_ylim(0, 1)
ax.set_title("Chronic wells (2+ repairs in prior year): a new string keeps them running much longer")
ax.legend(frameon=False)
cm.save(fig, IDEA, "1c_km_chronic.png")

# D: break-even
fig, ax = plt.subplots()
ax.plot(lam, net / 1e3, color=cm.C1, lw=2.5, label=f"central (Cox HR={hr_rep:.2f})")
net_hi = lam * (1 - hrc.loc["is_replace", "HR_hi"]) * H * fail_cost - inc_cost
ax.plot(lam, net_hi / 1e3, color=cm.C1, lw=1.2, ls="--", label=f"pessimistic (HR={hrc.loc['is_replace', 'HR_hi']:.2f}, upper 95% CI)")
ax.axhline(0, color="black", lw=0.8)
ax.axvline(breakeven, color=cm.C4, ls=":", lw=1.2)
ax.text(breakeven + 0.15, net.max() / 1e3 * 0.8, f"break-even\n{breakeven:.1f} failures/yr", color=cm.C4)
ax.set_xlabel("Well's rod failure rate (repairs per year)")
ax.set_ylabel("Net 2-year value of replacing the string (k CAD)")
ax.set_title("Replacing the string pays back on any well failing more than ~"
             f"{breakeven:.0f}x per year")
ax.legend(frameon=False, loc="upper left")
cm.save(fig, IDEA, "1d_break_even.png")

(OUT / "results.txt").write_text("".join(lines), encoding="utf-8")

# ------------------------------------------------------------------ machine-readable artifacts for the app
import json  # noqa: E402
ev[["uwi", "s", "e", "cost", "is_replace", "corod", "stick", "lost_m3", "prior365", "t_next", "event"]].to_parquet(OUT / "rod_events.parquet", index=False)
tab.assign(prior_bin=tab.prior_bin.astype(str)).to_csv(OUT / "rate_by_history.csv", index=False)
hr.rename_axis("term").reset_index().to_csv(OUT / "cox_all.csv", index=False)
hrc.rename_axis("term").reset_index().to_csv(OUT / "cox_chronic.csv", index=False)
pd.DataFrame(scen).to_csv(OUT / "sensitivity.csv", index=False)
km = []
for k, lab in enumerate(["repair", "new rod string"]):
    g = mc_all[mc_all.is_replace == k]
    sf = SurvfuncRight(g.t.astype(float), g.event.astype(float))
    km.append(pd.DataFrame({"group": lab, "n": len(g), "t": sf.surv_times, "surv": sf.surv_prob}))
pd.concat(km).to_csv(OUT / "km_chronic.csv", index=False)
(OUT / "economics.json").write_text(json.dumps({
    "oil_CAD_m3": cm.OIL_CAD_M3, "repair_job_cost": float(cost_rep_pos), "replace_job_cost": float(cost_rpl_pos),
    "lost_m3_per_repair_mean": float(lost_rep_mean), "lost_m3_per_repair_median": float(lost_med),
    "fail_cost": float(fail_cost), "inc_cost": float(inc_cost), "horizon_yr": H,
    "hr_all": float(hr.loc["is_replace", "HR"]), "hr_all_lo": float(hr.loc["is_replace", "HR_lo"]),
    "hr_all_hi": float(hr.loc["is_replace", "HR_hi"]),
    "hr_chronic": float(hr_rep), "hr_chronic_lo": float(hrc.loc["is_replace", "HR_lo"]),
    "hr_chronic_hi": float(hrc.loc["is_replace", "HR_hi"]), "breakeven": float(breakeven),
    "r_repair": float(r_repair), "r_replace": float(r_replace),
    "program_wells": int(len(prog)), "program_repairs": int(prog.repairs_last365.sum()),
    "program_allin": float(prog.all_in_cost_last365_CAD.sum()), "program_net": float(prog.net_value_2y_CAD.sum()),
    "program_net_hi": float((prog.repairs_last365 * (1 - hrc.loc["is_replace", "HR_hi"]) * H * fail_cost - inc_cost).sum()),
    "asof": cm.DATA_END, "n_cox": int(len(m)), "events_cox": int(m.event.sum()),
}, indent=2))
