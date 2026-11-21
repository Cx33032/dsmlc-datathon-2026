"""Mechanical Whiplash - is volatile operation (not the RPM level) followed by rod failures?

Run:  python data/ideas/whiplash/shock_index.py      (after Idea 1, which provides rod job events)
Outputs: <out>/whiplash/results.txt, verdict.json, results_table.csv, case_crossover_pairs.csv,
         perm_null.csv, well_shock.parquet; charts in docs/ideas/whiplash/assets/

PRE-REGISTERED (written before the first run; windows and thresholds are not tuned afterwards)
  Expected direction: the Shock Index is HIGHER in the 30 days that end 7 days before a rod failure than in
  the same well's control windows 60-180 days earlier (conditional OR per 1 SD > 1).
  Keep rule: ship the index as a watch signal only if (a) the case-crossover OR > 1 with p < 0.05 by both
  conditional logit and the sign-flip permutation, AND (b) it keeps an HR > 1 with a 95% CI excluding 1
  when added to Idea 1's Cox model. Otherwise it goes to "ideas we tested and rejected".

Shock Index for well-day D (uses data strictly before D only):
  readings screened: RPM 1-720, torque 1-8,000 ft-lb, current 1-600 A, and only on steady days (>= 22 h up)
  components over trailing 14- and 30-day windows ending D-1:
    sd of day-over-day dRPM;  count |dRPM| >= 20;  CV of d-torque;  CV of d-current;
    run/stop transitions (up-hours crossing 22 h) + partial-downtime days
  each component -> z-score against the SAME well's past (expanding mean/sd up to D-1, >= 60 days)
  Shock Index = mean of the available z components (>= 3 required)
Known limit: daily data cannot see shocks that last seconds or minutes (stick-slip, torque spikes).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src import shock  # noqa: E402
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from statsmodels.discrete.conditional_models import ConditionalLogit
from statsmodels.duration.hazard_regression import PHReg

OUT = cm.out_dir(__file__, "whiplash")
IDEA = "whiplash"
con = cm.con()
cm.style()
lines = []
rng = np.random.default_rng(7)
GAP_D, WIN_D = 7, 30                      # hazard window = 30 days ending 7 days before the failure
CONTROL_OFFSETS = [60, 90, 120, 150, 180]  # control anchors, days before the hazard anchor
N_PERM = 10000


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


# ------------------------------------------------------------------ 1. load screened daily readings
d = con.sql(f"""
select uwi, field_operating_area area, production_date::date dt, coalesce(hours_on_prod,0) on_h,
       coalesce(hours_down,0) down_h,
       case when pcp_pump_rpm::double between 1 and 720 then pcp_pump_rpm::double end rpm,
       case when pcp_pump_rod_torque_ftlb between 1 and 8000 then pcp_pump_rod_torque_ftlb end tq,
       case when pcp_pump_electric_current_a between 1 and 600 then pcp_pump_electric_current_a end cur
from '{cm.DAILY}' where flow_direction='production' and well_daily_status='Producing'
order by uwi, dt""").df()
d = d.drop_duplicates(["uwi", "dt"]).reset_index(drop=True)
d["dt"] = pd.to_datetime(d["dt"])
steady = d["on_h"] >= 22
for c in ("rpm", "tq", "cur"):
    d[c] = d[c].where(steady)
cov = d.groupby("area")[["rpm", "tq", "cur"]].apply(lambda x: x.notna().mean()).mul(100).round(1)
cov["well_days"] = d.groupby("area").size()
emit("Coverage: % of producing well-days with a screened steady-state reading", cov)

# ------------------------------------------------------------------ 2. components (strictly past-only)
d, Z = shock.add_shock_index(d)
emit("Shock Index coverage", pd.Series({
    "producing_well_days": len(d), "with_shock_index_pct": round(100 * d["shock_index"].notna().mean(), 1),
    "wells_with_any": int(d.loc[d["shock_index"].notna(), "uwi"].nunique()),
    "median_components_available": float(Z.notna().sum(axis=1).median())}))
emit("Shock Index coverage by area (% of producing well-days)",
     d.groupby("area")["shock_index"].apply(lambda s: round(100 * s.notna().mean(), 1)))

# ------------------------------------------------------------------ 3. case-crossover on rod failures (Jun 2025 on)
f = con.sql(f"""select uwi, failure_start_date::date fd from '{cm.FAILS}'
               where failure_type='Rods' and failure_start_date >= '{cm.FAIL_LOG_START}'""").df()
f["fd"] = pd.to_datetime(f["fd"])
f = f.drop_duplicates().sort_values(["uwi", "fd"]).reset_index(drop=True)
rod_path = cm.out_dir(str(Path(__file__).resolve().parents[1] / "1" / "x.py"), "1") / "rod_events.parquet"
rod = pd.read_parquet(rod_path) if rod_path.exists() else pd.DataFrame(columns=["uwi", "s"])
rod["s"] = pd.to_datetime(rod["s"])
other = pd.concat([f.rename(columns={"fd": "t"}), rod[["uwi", "s"]].rename(columns={"s": "t"})])
other_by = {u: np.sort(x["t"].values) for u, x in other.groupby("uwi")}
idx = d.set_index(["uwi", "dt"])[["shock_index", "rpm_level_30"]]


def val(u, day, col="shock_index"):
    try:
        return idx.at[(u, day), col]
    except KeyError:
        return np.nan


rows = []
for i, r in enumerate(f.itertuples()):
    h_anchor = r.fd - pd.Timedelta(days=GAP_D)          # index at this date uses data up to fd-8
    h = val(r.uwi, h_anchor)
    if pd.isna(h):
        continue
    ts = other_by.get(r.uwi, np.array([], dtype="datetime64[ns]"))
    n_ctrl = 0
    for k in CONTROL_OFFSETS:
        a = h_anchor - pd.Timedelta(days=k)
        lo, hi = np.datetime64(a - pd.Timedelta(days=WIN_D + 7)), np.datetime64(a + pd.Timedelta(days=GAP_D + 7))
        if ((ts >= lo) & (ts <= hi)).any():             # control window overlaps another failure/rod job
            continue
        c = val(r.uwi, a)
        if pd.notna(c):
            rows.append(dict(fid=i, uwi=r.uwi, case=0, shock=c, rpm=val(r.uwi, a, "rpm_level_30")))
            n_ctrl += 1
    if n_ctrl:
        rows.append(dict(fid=i, uwi=r.uwi, case=1, shock=h, rpm=val(r.uwi, h_anchor, "rpm_level_30")))
cc = pd.DataFrame(rows)
res_rows = []
summary = {}
if len(cc) and cc["case"].sum() >= 20:
    pair = cc.groupby("fid").apply(lambda x: pd.Series({
        "uwi": x["uwi"].iloc[0], "hazard": x.loc[x.case == 1, "shock"].mean(),
        "control": x.loc[x.case == 0, "shock"].mean(), "n_controls": int((x.case == 0).sum())}), include_groups=False)
    pair = pair.dropna(subset=["hazard", "control"])
    pair["diff"] = pair["hazard"] - pair["control"]
    obs = pair["diff"].mean()
    signs = rng.choice([-1, 1], size=(N_PERM, len(pair)))
    null = (signs * pair["diff"].to_numpy()).mean(axis=1)
    p_perm = (np.sum(np.abs(null) >= abs(obs)) + 1) / (N_PERM + 1)
    wil = stats.wilcoxon(pair["diff"])
    sd_all = d["shock_index"].std()
    cl = cc.dropna(subset=["shock"]).copy()
    cl = cl[cl.groupby("fid")["case"].transform("sum") == 1]
    cl["shock_sd"] = cl["shock"] / sd_all
    mod = ConditionalLogit(cl["case"], cl[["shock_sd"]], groups=cl["fid"]).fit(disp=0)
    or_, (lo_, hi_) = np.exp(mod.params.iloc[0]), np.exp(mod.conf_int().iloc[0])
    p_cl = float(mod.pvalues.iloc[0])
    # contrast: RPM LEVEL in the same design
    cr = cc.dropna(subset=["rpm"]).copy()
    cr = cr[(cr.groupby("fid")["case"].transform("sum") == 1) & (cr.groupby("fid")["case"].transform("size") >= 2)]
    cr["rpm100"] = cr["rpm"] / 100
    modr = ConditionalLogit(cr["case"], cr[["rpm100"]], groups=cr["fid"]).fit(disp=0)
    emit("Case-crossover: Shock Index, hazard window (30 d ending 7 d before the rod failure) vs same-well controls "
         "60-180 d earlier", pd.Series({
             "failures_with_index": int(len(pair)), "wells": int(pair["uwi"].nunique()),
             "controls_per_failure_median": float(pair["n_controls"].median()),
             "mean_hazard": pair["hazard"].mean(), "mean_control": pair["control"].mean(), "mean_diff": obs,
             "share_hazard_higher": (pair["diff"] > 0).mean(), "wilcoxon_p": wil.pvalue,
             "signflip_perm_p": p_perm, "condlogit_OR_per_SD": or_, "OR_lo": lo_, "OR_hi": hi_, "condlogit_p": p_cl,
             "rpm_level_OR_per_100rpm": np.exp(modr.params.iloc[0]), "rpm_level_p": float(modr.pvalues.iloc[0])}).round(4))
    pair.reset_index().to_csv(OUT / "case_crossover_pairs.csv", index=False)
    pd.DataFrame({"mean_diff": null}).to_csv(OUT / "perm_null.csv", index=False)
    res_rows += [("Case-crossover", "Shock Index OR per 1 SD", f"{or_:.3f} ({lo_:.3f}-{hi_:.3f})", f"{p_cl:.3g}",
                  f"{len(pair)} failures, {pair['uwi'].nunique()} wells"),
                 ("Case-crossover", "Sign-flip permutation, mean diff", f"{obs:+.3f}", f"{p_perm:.3g}", f"{N_PERM:,} flips"),
                 ("Case-crossover", "RPM level OR per 100 rpm (contrast)", f"{np.exp(modr.params.iloc[0]):.3f}",
                  f"{float(modr.pvalues.iloc[0]):.3g}", "same design")]
    summary.update(cc_or=float(or_), cc_or_lo=float(lo_), cc_or_hi=float(hi_), cc_p=p_cl, cc_perm_p=float(p_perm),
                   cc_mean_diff=float(obs), cc_n=int(len(pair)))
else:
    emit("Case-crossover", f"too few rod failures with a computable index ({int(cc['case'].sum()) if len(cc) else 0})")

# ------------------------------------------------------------------ 4. add to Idea 1's Cox model (lagged, same spec)
if len(rod) and "t_next" in rod:
    con.register("rod_df", rod[["uwi", "s"]].drop_duplicates())
    covs = con.sql(f"""
    select r.uwi, r.s, avg({cm.CLEAN['rpm']}) rpm30, avg({cm.CLEAN['oil']}+{cm.CLEAN['wat']}) liq30,
           any_value(dd.field_operating_area) area
    from rod_df r join '{cm.DAILY}' dd on dd.uwi=r.uwi and dd.production_date between r.s - interval 37 day and r.s - interval 8 day
    group by 1,2""").df()
    covs["s"] = pd.to_datetime(covs["s"])
    m = rod.merge(covs, on=["uwi", "s"], how="inner")
    m = m[m.rpm30.notna() & m.liq30.notna() & (m.s >= "2022-01-01")].copy()
    m["shock"] = [val(u, s - pd.Timedelta(days=GAP_D)) for u, s in zip(m.uwi, m.s)]   # index uses data up to s-8
    m["log_prior"], m["rpm100"], m["log_liq"] = np.log1p(m.prior365), m.rpm30 / 100, np.log1p(m.liq30)
    m["year"] = m.s.dt.year
    m["t_next"] = m.t_next.clip(upper=730)
    m.loc[m.t_next >= 730, "event"] = 0
    sub = m[m.shock.notna()].copy()
    sub["shock_sd"] = sub.shock / d["shock_index"].std()
    strata = sub.area.astype(str) + "_" + sub.year.astype(str)

    def fit(cols):
        mod = PHReg(sub.t_next.astype(float), sub[cols].astype(float), status=sub.event.astype(float), strata=strata).fit()
        ci = mod.conf_int()
        return pd.DataFrame({"HR": np.exp(mod.params), "HR_lo": np.exp(ci[:, 0]), "HR_hi": np.exp(ci[:, 1]),
                             "p": mod.pvalues}, index=cols)

    base = fit(["is_replace", "log_prior", "rpm100", "log_liq"])
    withs = fit(["is_replace", "log_prior", "rpm100", "log_liq", "shock_sd"])
    emit(f"Cox (Idea 1 spec) on rod jobs with a computable index, without the Shock Index (n={len(sub)}, "
         f"events={int(sub.event.sum())}, all-jobs n={len(m)})", base.round(4))
    emit("Cox (Idea 1 spec) + Shock Index per 1 SD, measured in the 30 d ending 8 d before the job", withs.round(4))
    res_rows += [("Cox + shock", "Shock Index HR per 1 SD", f"{withs.loc['shock_sd', 'HR']:.3f} "
                  f"({withs.loc['shock_sd', 'HR_lo']:.3f}-{withs.loc['shock_sd', 'HR_hi']:.3f})",
                  f"{withs.loc['shock_sd', 'p']:.3g}", f"n={len(sub)} rod jobs"),
                 ("Cox + shock", "New-string HR without -> with shock",
                  f"{base.loc['is_replace', 'HR']:.3f} -> {withs.loc['is_replace', 'HR']:.3f}", "", "same subset"),
                 ("Cox + shock", "RPM level HR per 100 rpm (with shock)", f"{withs.loc['rpm100', 'HR']:.3f}",
                  f"{withs.loc['rpm100', 'p']:.3g}", "")]
    summary.update(cox_shock_hr=float(withs.loc["shock_sd", "HR"]), cox_shock_lo=float(withs.loc["shock_sd", "HR_lo"]),
                   cox_shock_hi=float(withs.loc["shock_sd", "HR_hi"]), cox_shock_p=float(withs.loc["shock_sd", "p"]),
                   cox_replace_hr_without=float(base.loc["is_replace", "HR"]),
                   cox_replace_hr_with=float(withs.loc["is_replace", "HR"]), cox_n=int(len(sub)))

# ------------------------------------------------------------------ 5. verdict (rule fixed above, before running)
keep = bool(summary.get("cc_or", 0) > 1 and summary.get("cc_p", 1) < 0.05 and summary.get("cc_perm_p", 1) < 0.05
            and summary.get("cox_shock_lo", 0) > 1)
cov_txt = (f"Tested population: producing well-days with steady-state (>=22 h) pump readings and >=3 of 10 "
           f"components; {100 * d['shock_index'].notna().mean():.1f}% of producing well-days. RPM, torque and current "
           f"are manual readings that repeat the previous day most of the time, so day-over-day changes are rare.")
if keep:
    txt = (f"Volatility precedes rod failures: OR {summary['cc_or']:.2f} per SD (p={summary['cc_p']:.3g}); "
           f"Cox HR {summary['cox_shock_hr']:.2f} per SD.")
elif "cc_or" in summary:
    cc_sig = summary["cc_or"] > 1 and summary["cc_p"] < 0.05 and summary["cc_perm_p"] < 0.05
    cc_txt = (f"case-crossover OR {summary['cc_or']:.2f} per SD ({summary['cc_or_lo']:.2f}-{summary['cc_or_hi']:.2f}, "
              f"p={summary['cc_p']:.2g}; permutation p={summary['cc_perm_p']:.2g})")
    cox_txt = (f"in Idea 1's Cox model the index has HR {summary['cox_shock_hr']:.2f} ({summary['cox_shock_lo']:.2f}-"
               f"{summary['cox_shock_hi']:.2f}) and the new-string HR moves {summary['cox_replace_hr_without']:.3f} -> "
               f"{summary['cox_replace_hr_with']:.3f}" if "cox_shock_hr" in summary else "the Cox test could not run")
    txt = (("A borderline " if cc_sig else "No usable signal at daily resolution: ") + cc_txt + ("; but " if cc_sig else "; ")
           + cox_txt + ". Fails the pre-registered keep rule, so the index stays out of every ranking.")
else:
    txt = "Not enough rod failures with a computable index to test."
verdict = dict(keep=keep, summary=txt, coverage=cov_txt, **summary,
               question="Are sudden day-to-day changes in RPM, torque, current and run hours followed by rod failures, "
                        "more than the RPM level is?",
               expected="Higher Shock Index in the 30 days ending 7 days before a rod failure than in the same well's "
                        "control windows 60-180 days earlier (OR > 1).")
(OUT / "verdict.json").write_text(json.dumps(verdict, indent=2))
pd.DataFrame(res_rows, columns=["test", "quantity", "estimate", "p", "n"]).to_csv(OUT / "results_table.csv", index=False)
emit("Verdict", ("KEEP: " if keep else "REJECT: ") + txt)
d.loc[d["dt"] >= "2025-06-01", ["uwi", "dt", "shock_index"]].rename(columns={"dt": "production_date"}) \
    .to_parquet(OUT / "well_shock.parquet", index=False)

# ------------------------------------------------------------------ charts
if "cc_or" in summary:
    pair_ = pd.read_csv(OUT / "case_crossover_pairs.csv")
    fig, ax = plt.subplots()
    ax.hist(null, bins=50, color=cm.GREY, alpha=0.8, label="sign-flip permutations")
    ax.axvline(summary["cc_mean_diff"], color=cm.C4, lw=2.5, label=f"observed {summary['cc_mean_diff']:+.3f}")
    ax.set_xlabel("Mean Shock Index difference, hazard minus control windows (z units)")
    ax.set_ylabel("Permutations")
    ax.set_title(f"Mechanical Whiplash: case-crossover on {summary['cc_n']} rod failures (p = {summary['cc_perm_p']:.2g})")
    ax.legend(frameon=False)
    cm.save(fig, IDEA, "w1_case_crossover.png")
    fig, ax = plt.subplots()
    ax.hist(pair_["diff"], bins=40, color=cm.C1)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Hazard minus control Shock Index, per failure")
    ax.set_ylabel("Rod failures")
    ax.set_title("Per-failure differences are centred on zero" if not keep else "Hazard windows run hotter")
    cm.save(fig, IDEA, "w2_pair_differences.png")
fig, ax = plt.subplots()
cov[["rpm", "tq", "cur"]].plot.bar(ax=ax, color=[cm.C1, cm.C2, cm.C3])
ax.set_ylabel("% of producing well-days with a steady reading")
ax.set_title("Pump-tag coverage limits who can be tested")
ax.legend(["RPM", "torque", "current"], frameon=False)
cm.save(fig, IDEA, "w3_coverage.png")

(OUT / "results.txt").write_text("".join(lines), encoding="utf-8")
