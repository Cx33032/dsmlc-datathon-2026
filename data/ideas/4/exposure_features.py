"""Idea 4 extended into Idea 2: does cumulative LOAD EXPOSURE improve the 30-day failure-risk model?

Run:  python data/ideas/2/build_features.py   (once, makes snapshots.parquet)
      python data/ideas/4/exposure_features.py
Outputs: data/ideas/4/out/exposure_results.txt, chart docs/ideas/4/assets/4h_exposure_lift.png

The rig cannot make data for historical wells, but its core idea can be tested on the real daily data:
fatigue grows with the load a rod string has carried since it was last replaced or repaired.
New features, all computed only from rows dated on or before the snapshot date t:
  revs_since_fail / revs_since_replace      rod revolutions = rpm x hours_on_prod x 60, summed since the last
                                            failure-type job / string replacement (one rotation = one bending cycle
                                            in a deviated well, the rotating-bending mechanism)
  dmg_since_fail / dmg_since_replace        same, each day weighted by (torque / 625 ft-lb)^5 (Basquin-style, m=5 is
                                            an assumption), using the last reported torque (torque tags are held for weeks)
  severity_since_fail                       dmg / revs: how hard the load was on average
Wells with no RPM tag (Fenn Big Valley, CHO-Non-Op) get missing values, not zeros.
Same time split, same LightGBM settings and same test windows as Idea 2; 5 seeds averaged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt
from sklearn.metrics import roc_auc_score, average_precision_score

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
cm.style()
lines = []


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


snap = pd.read_parquet(Path(__file__).resolve().parents[1] / "2" / "out" / "snapshots.parquet")
snap["t"] = pd.to_datetime(snap.t)
con = cm.con()
C = cm.CLEAN
TQ_REF, M = 625.0, 5.0

# ------------------------------------------------------------------ daily cumulative exposure per well
cum = con.sql(f"""
with d as (
  select uwi, production_date dt, hours_on_prod hp, {C['rpm']} rpm, {C['tq']} tq
  from '{cm.DAILY}' where flow_direction='production'),
f as (
  select uwi, dt, hp,
    last_value(rpm ignore nulls) over w rpm_f,
    last_value(tq ignore nulls) over w tq_f
  from d window w as (partition by uwi order by dt rows between unbounded preceding and current row)),
r as (
  select uwi, dt, rpm_f is not null has_rpm,
    coalesce(rpm_f, 0) * hp * 60 revs,
    coalesce(rpm_f, 0) * hp * 60 * power(least(coalesce(tq_f, {TQ_REF}) / {TQ_REF}, 6), {M}) dmg
  from f)
select uwi, dt::date dt, has_rpm,
  sum(revs) over (partition by uwi order by dt) cum_revs,
  sum(dmg) over (partition by uwi order by dt) cum_dmg
from r""").df()
cum["dt"] = pd.to_datetime(cum.dt)
cum = cum.sort_values(["dt", "uwi"]).reset_index(drop=True)
print("daily cumulative rows:", len(cum))


def cum_at(dates, label):
    """Cumulative revs/damage at the latest day <= dates for each well (0 before the well's first row)."""
    q = pd.DataFrame({"uwi": snap.uwi.values, "dt": dates}).reset_index().rename(columns={"index": "i"})
    ok = q.dt.notna()
    res = pd.DataFrame(index=q.index, columns=[f"{label}_revs", f"{label}_dmg"], dtype=float)
    qq = q[ok].sort_values("dt")
    m = pd.merge_asof(qq, cum[["uwi", "dt", "cum_revs", "cum_dmg"]], on="dt", by="uwi", direction="backward")
    res.loc[m.i.values, f"{label}_revs"] = m.cum_revs.values
    res.loc[m.i.values, f"{label}_dmg"] = m.cum_dmg.values
    return res.fillna(0.0)    # before the well's first row (or no earlier event): cumulative load was 0


now = pd.merge_asof(snap[["uwi", "t"]].reset_index().sort_values("t"), cum[["uwi", "dt", "cum_revs", "cum_dmg", "has_rpm"]],
                    left_on="t", right_on="dt", by="uwi", direction="backward").sort_values("index")
cur_revs, cur_dmg, has_rpm = now.cum_revs.values, now.cum_dmg.values, now.has_rpm.values.astype(bool)

# date of the last failure-type job / string replacement. No earlier event -> left-censored: counts from 2021-01-01
d_fail = snap.t - pd.to_timedelta(snap.days_since_fail, unit="D")
d_rep = snap.t - pd.to_timedelta(snap.days_since_replace, unit="D")
b_fail, b_rep = cum_at(d_fail.values, "fail"), cum_at(d_rep.values, "rep")
new = pd.DataFrame(index=snap.index)
new["revs_since_fail"] = (cur_revs - b_fail.fail_revs.values) / 1e6      # million revolutions
new["revs_since_replace"] = (cur_revs - b_rep.rep_revs.values) / 1e6
new["dmg_since_fail"] = (cur_dmg - b_fail.fail_dmg.values) / 1e6
new["dmg_since_replace"] = (cur_dmg - b_rep.rep_dmg.values) / 1e6
new["severity_since_fail"] = new.dmg_since_fail / new.revs_since_fail.replace(0, np.nan)
new["revs_per_day_since_fail"] = new.revs_since_fail * 1e6 / snap.days_since_fail.fillna(1826).clip(lower=1)
new.loc[~has_rpm, :] = np.nan
NEW = list(new.columns)
snap = pd.concat([snap, new], axis=1)
emit("New exposure features: summary (test window, wells with an RPM tag)", snap[snap.t >= cm.FAIL_LOG_START][NEW].describe().T.round(3))

# ------------------------------------------------------------------ same model and split as Idea 2
HIST = ["n_fail_90", "n_fail_365", "n_fail_730", "days_since_fail", "days_since_replace"]
SENS = ["disp", "well_age_yrs", "oil7", "oil30", "oil90", "liq7", "liq30", "liq90", "wc30", "r_oil_7_30", "r_oil_30_90",
        "r_liq_7_30", "oil_slope30", "eff7", "eff30", "r_eff_7_90", "rpm7", "d_rpm_7_90", "tq7", "r_tq_7_90", "r_tqmax_90",
        "cur7", "r_cur_7_90", "tbg7", "d_tbg_7_90", "csg7", "tq_per_rpm", "vol_eff7", "down_days30", "down_days90", "hd30",
        "dh_days90", "dh_days365", "torq_days90"]
CAT = ["area", "make"]
BASE = HIST + SENS + CAT
tr = snap[(snap.t >= "2022-01-03") & (snap.t <= "2023-11-30")]
va = snap[(snap.t >= "2024-01-01") & (snap.t <= "2024-11-30")]
te = snap[(snap.t >= cm.FAIL_LOG_START) & (snap.t <= "2026-09-27")]
params = dict(objective="binary", learning_rate=0.03, num_leaves=31, min_child_samples=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1)


def fit_predict(feats, seed):
    p = {**params, "seed": seed}
    cats = [c for c in CAT if c in feats]
    b = lgb.train(p, lgb.Dataset(tr[feats], tr.y_job, categorical_feature=cats), 3000,
                  valid_sets=[lgb.Dataset(va[feats], va.y_job)], callbacks=[lgb.early_stopping(100, verbose=False)])
    n = b.best_iteration
    full = pd.concat([tr, va])
    bf = lgb.train(p, lgb.Dataset(full[feats], full.y_job, categorical_feature=cats), n)
    return bf, bf.predict(te[feats]), n


def prec_at_k(df, score, ylab, k):
    d = df[["t", ylab]].copy()
    d["s"] = score
    top = d.sort_values("s", ascending=False).groupby("t").head(k)
    return top[ylab].mean()


variants = {"Idea 2 baseline": BASE,
            "+ cumulative revolutions only": BASE + ["revs_since_fail", "revs_since_replace", "revs_per_day_since_fail"],
            "+ revolutions and torque-weighted damage": BASE + NEW}
rows, models = [], {}
for name, feats in variants.items():
    for seed in range(5):
        m, sc, n = fit_predict(feats, seed)
        for ylab in ["y_flog", "y_job"]:
            rows.append(dict(variant=name, seed=seed, label=ylab, roc_auc=roc_auc_score(te[ylab], sc),
                             pr_auc=average_precision_score(te[ylab], sc), p50=prec_at_k(te, sc, ylab, 50),
                             p100=prec_at_k(te, sc, ylab, 100)))
        models[name] = m
res = pd.DataFrame(rows)
summ = res.groupby(["label", "variant"])[["roc_auc", "pr_auc", "p50", "p100"]].agg(["mean", "std"]).round(4)
emit("Out-of-time test (Jun 2025 - Sep 2026), mean and std over 5 seeds", summ)
base = res[res.variant == "Idea 2 baseline"].groupby("label")[["roc_auc", "pr_auc", "p50", "p100"]].mean()
full = res[res.variant == "+ revolutions and torque-weighted damage"].groupby("label")[["roc_auc", "pr_auc", "p50", "p100"]].mean()
emit("Relative change of full variant vs baseline (%)", ((full / base - 1) * 100).round(2))

# paired comparison per seed on the failure-log label
b_ = res[(res.variant == "Idea 2 baseline") & (res.label == "y_flog")].set_index("seed")
f_ = res[(res.variant == "+ revolutions and torque-weighted damage") & (res.label == "y_flog")].set_index("seed")
emit("Per-seed difference in PR-AUC (full minus baseline), failure-log label", (f_.pr_auc - b_.pr_auc).round(4))

imp = pd.Series(models["+ revolutions and torque-weighted damage"].feature_importance("gain"),
                index=variants["+ revolutions and torque-weighted damage"])
imp = (imp / imp.sum()).sort_values(ascending=False)
emit("Feature importance (share of gain), full variant: top 12 and the new features", pd.concat([imp.head(12), imp[NEW]]).round(4))

# ------------------------------------------------------------------ only wells with an RPM tag (where the new features exist)
mask = te.rpm7.notna().values


def sub_metrics(feats):
    out = []
    for seed in range(5):
        _, sc, _ = fit_predict(feats, seed)
        d = te[mask]
        out.append((roc_auc_score(d.y_flog, sc[mask]), average_precision_score(d.y_flog, sc[mask]), prec_at_k(d, sc[mask], "y_flog", 50)))
    return np.mean(out, axis=0)


sub = pd.DataFrame({"baseline": sub_metrics(BASE), "full": sub_metrics(BASE + NEW)}, index=["roc_auc", "pr_auc", "p50"]).T.round(4)
emit("Same test, wells with an RPM tag only", sub)

# ------------------------------------------------------------------ chart
fig, ax = plt.subplots()
ks = [10, 25, 50, 100, 150, 200]
cols = [cm.GREY, cm.C2, cm.C1]
for (name, feats), col in zip(variants.items(), cols):
    ys = []
    for k in ks:
        ys.append(np.mean([prec_at_k(te, fit_predict(feats, s)[1], "y_flog", k) for s in range(2)]))
    ax.plot(ks, ys, marker="o", color=col, lw=2, label=name)
ax.axhline(te.y_flog.mean(), color="black", ls=":", lw=1, label="random")
ax.set_xlabel("Wells flagged per week (K)")
ax.set_ylabel("Precision@K (failure within 30 d)")
ax.set_title("Does cumulative load exposure help the risk model? (out-of-time test)")
ax.legend(frameon=False, fontsize=9)
cm.save(fig, "4", "4h_exposure_lift.png")
(OUT / "exposure_results.txt").write_text("".join(lines), encoding="utf-8")
