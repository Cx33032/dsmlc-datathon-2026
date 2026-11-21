"""Idea 2 - step 2: time-split training and evaluation of the 30-day downhole-failure risk model.

Run:  python data/ideas/2/build_features.py   (once)
      python data/ideas/2/train_eval.py
Outputs: data/ideas/2/out/results.txt, charts in docs/ideas/2/assets/

Split (no random splits):
  train  t in [2022-01-03, 2023-11-30]          labels end <= 2023-12-30
  valid  t in [2024-01-01, 2024-11-30]          early stopping / model choice
  test   t in [2025-06-01, 2026-09-27]          failure-log era; evaluated on job labels AND failure-log labels
  (Dec 2024 - May 2025 is a gap: the failure log is incomplete there and it separates valid from test.)
Final model is refit on train+valid with the early-stopped number of trees, then scored once on test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common as cm
import numpy as np
import pandas as pd
import lightgbm as lgb
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

OUT = Path(__file__).resolve().parent / "out"
IDEA = "2"
cm.style()
lines = []


def emit(t, obj):
    s = f"\n### {t}\n{obj if isinstance(obj, str) else obj.to_string()}\n"
    print(s)
    lines.append(s)


s = pd.read_parquet(OUT / "snapshots.parquet")
s["t"] = pd.to_datetime(s.t)
HIST = ["n_fail_90", "n_fail_365", "n_fail_730", "days_since_fail", "days_since_replace"]
SENS = ["disp", "well_age_yrs", "oil7", "oil30", "oil90", "liq7", "liq30", "liq90", "wc30", "r_oil_7_30", "r_oil_30_90",
        "r_liq_7_30", "oil_slope30", "eff7", "eff30", "r_eff_7_90", "rpm7", "d_rpm_7_90", "tq7", "r_tq_7_90", "r_tqmax_90",
        "cur7", "r_cur_7_90", "tbg7", "d_tbg_7_90", "csg7", "tq_per_rpm", "vol_eff7", "down_days30", "down_days90", "hd30",
        "dh_days90", "dh_days365", "torq_days90"]
CAT = ["area", "make"]
FEATS = HIST + SENS + CAT

tr = s[(s.t >= "2022-01-03") & (s.t <= "2023-11-30")]   # 2021 dropped: history features left-censored
va = s[(s.t >= "2024-01-01") & (s.t <= "2024-11-30")]
te = s[(s.t >= cm.FAIL_LOG_START) & (s.t <= "2026-09-27")]
emit("Split sizes and base rates", pd.DataFrame({
    "rows": [len(tr), len(va), len(te)], "wells": [tr.uwi.nunique(), va.uwi.nunique(), te.uwi.nunique()],
    "y_job_rate": [tr.y_job.mean(), va.y_job.mean(), te.y_job.mean()], "y_flog_rate": [np.nan, np.nan, te.y_flog.mean()]},
    index=["train", "valid", "test"]).round(4))

params = dict(objective="binary", learning_rate=0.03, num_leaves=31, min_child_samples=200, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)


def fit_lgb(feats, name):
    dtr = lgb.Dataset(tr[feats], tr.y_job, categorical_feature=[c for c in CAT if c in feats])
    dva = lgb.Dataset(va[feats], va.y_job, reference=dtr)
    b = lgb.train(params, dtr, 3000, valid_sets=[dva], callbacks=[lgb.early_stopping(100, verbose=False)])
    n = b.best_iteration
    full = pd.concat([tr, va])
    bf = lgb.train(params, lgb.Dataset(full[feats], full.y_job, categorical_feature=[c for c in CAT if c in feats]), n)
    return bf, b.predict(va[feats], num_iteration=n), n


scores_te, scores_va = {}, {}
# Baseline 1: failure-history heuristic (repairs in last 365 d, tie-break by recency)
for df, store in [(va, scores_va), (te, scores_te)]:
    store["B1 history rule (repairs last 365 d)"] = df.n_fail_365.values + 1 / (1 + df.days_since_fail.fillna(9999).values)
# Baseline 2: logistic regression on history features
lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=2000))
Xh = lambda df: np.column_stack([df.n_fail_90, df.n_fail_365, df.n_fail_730, np.log1p(df.days_since_fail.fillna(3000)),
                                 np.log1p(df.days_since_replace.fillna(3000))])
lr.fit(Xh(pd.concat([tr, va])), pd.concat([tr, va]).y_job)
scores_te["B2 logistic, history only"] = lr.predict_proba(Xh(te))[:, 1]
lr_tr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=2000)).fit(Xh(tr), tr.y_job)
scores_va["B2 logistic, history only"] = lr_tr.predict_proba(Xh(va))[:, 1]
# Ablation: LightGBM sensors/production only (no failure history)
m_sens, v_sens, n_sens = fit_lgb(SENS + CAT, "sens")
scores_te["LGBM sensors+production only"] = m_sens.predict(te[SENS + CAT])
scores_va["LGBM sensors+production only"] = v_sens
# Full model
m_full, v_full, n_full = fit_lgb(FEATS, "full")
scores_te["LGBM full (history+sensors)"] = m_full.predict(te[FEATS])
scores_va["LGBM full (history+sensors)"] = v_full
emit("Trees chosen by early stopping", f"full={n_full}, sensors-only={n_sens}")


def prec_at_k(df, score, ylab, k):
    d = df[["t", ylab]].copy()
    d["s"] = score
    top = d.sort_values("s", ascending=False).groupby("t").head(k)
    return top[ylab].mean(), top[ylab].sum() / d[ylab].sum()


rows = []
for split, df, sc in [("valid", va, scores_va), ("test", te, scores_te)]:
    for name, scv in sc.items():
        for ylab in (["y_job"] if split == "valid" else ["y_job", "y_flog"]):
            p50, r50 = prec_at_k(df, scv, ylab, 50)
            p100, r100 = prec_at_k(df, scv, ylab, 100)
            rows.append(dict(split=split, model=name, label=ylab, roc_auc=roc_auc_score(df[ylab], scv),
                             pr_auc=average_precision_score(df[ylab], scv), base_rate=df[ylab].mean(),
                             prec_at50_wk=p50, recall_at50_wk=r50, prec_at100_wk=p100, recall_at100_wk=r100))
res = pd.DataFrame(rows)
emit("Metrics (precision/recall @K = top K wells per weekly snapshot)", res.round(4).to_string(index=False))

# Lead time: for test failures caught in the top-50 list, days between first flag and the failure job
d = te[["uwi", "t", "y_job", "days_to_fail"]].copy()
d["s"] = scores_te["LGBM full (history+sensors)"]
d["rank"] = d.groupby("t").s.rank(ascending=False)
caught = d[(d["rank"] <= 50) & (d.y_job == 1)]
emit("Lead time of top-50 hits on test (days from flag to failure job)", caught.days_to_fail.describe().round(1))

# Sensor contribution on top of history: does adding sensors move the needle?
emit("Weekly list size context", f"median wells scored per week on test = {te.groupby('t').size().median():.0f}")

# Feature importance
imp = pd.Series(m_full.feature_importance("gain"), index=FEATS).sort_values(ascending=False)
imp = imp / imp.sum()
emit("Feature importance (share of gain), full model", imp.head(20).round(4))

# Business arithmetic inputs
weeks = te.t.nunique()
fails_test = te.y_job.sum()
hits50 = res[(res.split == "test") & (res.model == "LGBM full (history+sensors)") & (res.label == "y_job")].prec_at50_wk.iloc[0] * 50
d["fdate"] = d.t + pd.to_timedelta(d.days_to_fail, unit="D")
all_ev = d[d.y_job == 1][["uwi", "fdate"]].drop_duplicates()
caught_ev = d[(d["rank"] <= 50) & (d.y_job == 1)][["uwi", "fdate"]].drop_duplicates()
first_flag = (d[(d["rank"] <= 50) & (d.y_job == 1)].groupby(["uwi", "fdate"]).days_to_fail.max())
emit("Business inputs (test window, top-50 weekly list)", pd.Series({
    "test_weeks": weeks, "true_positive_well_weeks_per_week_at50": hits50,
    "distinct_failure_events_with_a_snapshot_in_prior_30d": len(all_ev),
    "distinct_failure_events_flagged_at_least_once": len(caught_ev),
    "event_recall_at50": len(caught_ev) / len(all_ev),
    "median_days_first_flag_to_failure": first_flag.median(),
    "flagged_events_per_year": len(caught_ev) / (weeks / 52.18),
    "wells_with_flagged_event": caught_ev.uwi.nunique()}).round(3))

# ------------------------------------------------------------------ charts
# A: PR curves on test (failure-log labels)
fig, ax = plt.subplots()
cols = [cm.GREY, cm.C2, cm.C3, cm.C1]
for (name, scv), col in zip(scores_te.items(), cols):
    p, r, _ = precision_recall_curve(te.y_flog, scv)
    ap = average_precision_score(te.y_flog, scv)
    ax.plot(r, p, color=col, lw=2.2 if "full" in name else 1.5, label=f"{name}  (AP={ap:.3f})")
ax.axhline(te.y_flog.mean(), color="black", ls=":", lw=1, label=f"random (base rate {te.y_flog.mean():.3f})")
ax.set_xlabel("Recall (share of 30-day failures flagged)")
ax.set_ylabel("Precision (share of flags that fail within 30 d)")
ax.set_title("Out-of-time test (Jun 2025-Sep 2026, failure-log labels): history carries most of the signal")
ax.legend(frameon=False, fontsize=8.5)
ax.set_xlim(0, 1)
ax.set_ylim(0, 0.8)
cm.save(fig, IDEA, "2a_pr_curves_test.png")

# B: precision@K
fig, ax = plt.subplots()
ks = [10, 25, 50, 100, 150, 200, 300]
for (name, scv), col in zip(scores_te.items(), cols):
    ax.plot(ks, [prec_at_k(te, scv, "y_flog", k)[0] for k in ks], marker="o", color=col, lw=2, label=name)
ax.axhline(te.y_flog.mean(), color="black", ls=":", lw=1, label="random")
ax.set_xlabel("Wells flagged per week (K, out of ~%d scored)" % te.groupby("t").size().median())
ax.set_ylabel("Precision@K: share failing within 30 days")
ax.set_title("A weekly top-50 watch-list is ~%.1fx better than random" %
             (prec_at_k(te, scores_te["LGBM full (history+sensors)"], "y_flog", 50)[0] / te.y_flog.mean()))
ax.legend(frameon=False, fontsize=8.5)
cm.save(fig, IDEA, "2b_precision_at_k.png")

# C: feature importance
fig, ax = plt.subplots(figsize=(9, 6.5))
top = imp.head(15)[::-1]
colors = [cm.C2 if f in HIST else cm.C1 for f in top.index]
ax.barh(top.index, top.values * 100, color=colors)
ax.set_xlabel("Share of total split gain (%)")
ax.set_title("Failure history dominates; production/sensor trends add the rest\n(orange = job history, blue = daily production/sensor)")
cm.save(fig, IDEA, "2c_feature_importance.png")

# D: reliability by decile
fig, ax = plt.subplots()
tt = te.copy()
tt["s"] = scores_te["LGBM full (history+sensors)"]
tt["dec"] = pd.qcut(tt.s.rank(method="first"), 10, labels=False) + 1
g = tt.groupby("dec").agg(pred=("s", "mean"), obs_job=("y_job", "mean"), obs_flog=("y_flog", "mean"))
ax.plot(g.index, g.pred, marker="o", color=cm.GREY, label="mean predicted probability")
ax.plot(g.index, g.obs_job, marker="o", color=cm.C1, label="observed (repair-job label)")
ax.plot(g.index, g.obs_flog, marker="s", color=cm.C2, label="observed (failure-log label)")
ax.set_xlabel("Risk decile on test (1 = lowest)")
ax.set_ylabel("30-day failure rate")
ax.set_title("Top risk decile fails %.0fx more often than the bottom decile (test)" % (g.obs_flog.iloc[-1] / max(g.obs_flog.iloc[0], 1e-6)))
ax.legend(frameon=False)
cm.save(fig, IDEA, "2d_decile_calibration.png")
emit("Decile table (test)", g.round(4))

(OUT / "results.txt").write_text("".join(lines), encoding="utf-8")
