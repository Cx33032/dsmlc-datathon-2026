"""Topic 1 - 14-day failure early-warning model (LightGBM) and its evaluation."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .config import HORIZON_DAYS, TRAIN_END, VALID_END
from .features import CAT_FEATURES, FEATURES

TRAIN_START = "2021-04-01"  # first quarter has no failure history yet (data starts 2021-01-01)
TEST_START = pd.Timestamp(VALID_END) + pd.Timedelta(days=1)

# chosen on the 2024 validation year (small sweep: valid AP 0.162-0.166 across configs)
PARAMS = dict(objective="binary", learning_rate=0.03, num_leaves=31, min_data_in_leaf=2000,
              feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0,
              metric="average_precision", verbose=-1, num_threads=12, seed=7)

READABLE = {
    "oil_7": "Oil, 7-day avg", "oil_30": "Oil, 30-day avg", "r_oil_3_30": "Oil 3d vs 30d",
    "r_oil_7_30": "Oil 7d vs 30d", "r_oil_30_90": "Oil 30d vs 90d", "r_oil_7_prev7": "Oil this week vs last",
    "oil_cv_14": "Oil volatility (14d)", "rate_30": "Oil rate (30d)", "r_rate_7_30": "Oil rate 7d vs 30d",
    "fluid_7": "Total fluid (7d)", "r_fluid_7_30": "Fluid 7d vs 30d", "wcut_30": "Water cut",
    "d_wcut_7_30": "Water cut change", "eff_30": "Pump efficiency (30d)", "r_eff_7_30": "Pump eff. 7d vs 30d",
    "d_eff_7_30": "Pump eff. change", "hrs_on_7": "Hours on (7d)", "down_days_30": "Down days (30d)",
    "gas_oil_30": "Gas-oil ratio", "rpm": "Pump RPM", "displacement": "Pump displacement",
    "torque": "Rod torque", "current": "Motor current", "casing_kpa": "Casing pressure",
    "tubing_kpa": "Tubing pressure", "vol_eff_7": "Fluid vs rated pump volume", "well_age_yrs": "Well age",
    "month": "Month", "days_since_failure": "Days since last failure", "n_failures_prior": "Failures since 2021",
    "n_failures_365": "Failures in last year", "field_operating_area": "Area", "pump_make": "Pump make",
    "last_component": "Last failed component",
}


def split(F: pd.DataFrame):
    E = F[F["eligible"] & (F["production_date"] >= TRAIN_START)]
    tr = E[E["production_date"] <= TRAIN_END]
    va = E[(E["production_date"] > TRAIN_END) & (E["production_date"] <= VALID_END)]
    te = E[E["production_date"] > VALID_END]
    return tr, va, te


def _ds(X: pd.DataFrame, y=None, ref=None):
    return lgb.Dataset(X[FEATURES], label=y, categorical_feature=CAT_FEATURES, reference=ref,
                       free_raw_data=False)


def train(F: pd.DataFrame) -> tuple[lgb.Booster, dict]:
    tr, va, te = split(F)
    dtr = _ds(tr, tr["y"])
    dva = _ds(va, va["y"], dtr)
    m0 = lgb.train(PARAMS, dtr, num_boost_round=3000, valid_sets=[dva],
                   callbacks=[lgb.early_stopping(150, verbose=False)])
    best = m0.best_iteration
    # refit on train+valid (all data before the test period) with the chosen #rounds
    trva = pd.concat([tr, va])
    model = lgb.train(PARAMS, _ds(trva, trva["y"]), num_boost_round=best)
    info = {"best_iteration": int(best), "valid_ap_at_best": float(m0.best_score["valid_0"]["average_precision"]),
            "n_train": len(tr), "n_valid": len(va), "n_test": len(te),
            "train_period": f"{TRAIN_START}..{TRAIN_END}", "valid_period": f"..{VALID_END}",
            "test_period": f"{TEST_START.date()}..{te['production_date'].max().date()}"}
    # two-tier thresholds fixed on the validation year (model m0 never trained on it):
    #   watch = top 5% of well-days (review list), alarm = top 2% (operator alarm in Canary)
    pv = m0.predict(va[FEATURES], num_iteration=best)
    info["alert_threshold"] = float(np.quantile(pv, 0.95))
    info["alarm_threshold"] = float(np.quantile(pv, 0.98))
    return model, info


# ---------------------------------------------------------------- evaluation
def baseline_scores(X: pd.DataFrame) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    return {
        "Rule: oil 7d < 30d": (1 - X["r_oil_7_30"].fillna(1)).to_numpy(),
        "Rule: failure history": (X["n_failures_365"] + 1 / (1 + X["days_since_failure"].fillna(9999))).to_numpy(),
        "Random": rng.random(len(X)),
    }


def topk_eval(X: pd.DataFrame, score: np.ndarray, ev: pd.DataFrame, k: int) -> dict:
    d = X[["uwi", "production_date", "y", "next_event_id", "days_to_onset"]].copy()
    d["s"] = score
    d["rank"] = d.groupby("production_date")["s"].rank(ascending=False, method="first")
    flag = d[d["rank"] <= k]
    prec = flag["y"].mean()
    # event-level: was the well flagged at least once in the 14 days before onset?
    tev = ev[ev["predictable"] & (ev["onset_date"] > X["production_date"].min() + pd.Timedelta(days=HORIZON_DAYS))
             & (ev["onset_date"] <= X["production_date"].max())]
    hits = flag[flag["y"] == 1].groupby("next_event_id")["days_to_onset"].max()
    caught = tev["event_id"].isin(hits.index)
    # workload: an "alert" = a well entering the top-K list (it was not on it the day before).
    # A random list churns every day, so it creates far more alerts for the same K.
    fl = flag[["uwi", "production_date"]].sort_values(["uwi", "production_date"])
    gap = fl.groupby("uwi", observed=True)["production_date"].diff().dt.days
    new_alerts = int((gap.isna() | (gap > 1)).sum())
    n_days = d["production_date"].nunique()
    return {"k": k, "precision_at_k": float(prec), "lift": float(prec / d["y"].mean()),
            "event_recall": float(caught.mean()), "events": int(len(tev)),
            "alerts_per_day": new_alerts / n_days,
            "events_caught_per_100_alerts": 100 * float(caught.sum()) / max(new_alerts, 1),
            "median_lead_days": float(hits.reindex(tev.loc[caught, "event_id"]).median()) if caught.any() else np.nan,
            "caught_event_ids": tev.loc[caught, "event_id"].to_numpy()}


def evaluate(model: lgb.Booster, F: pd.DataFrame, ev: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    _, _, te = split(F)
    s = model.predict(te[FEATURES])
    scores = {"LightGBM": s, **baseline_scores(te)}
    rows, caught = [], {}
    for name, sc in scores.items():
        r = {"model": name, "roc_auc": roc_auc_score(te["y"], sc), "pr_auc": average_precision_score(te["y"], sc)}
        for k in (10, 25, 50):
            t = topk_eval(te, sc, ev, k)
            r[f"precision@{k}"] = t["precision_at_k"]
            r[f"lift@{k}"] = t["lift"]
            r[f"event_recall@{k}"] = t["event_recall"]
            r[f"median_lead_days@{k}"] = t["median_lead_days"]
            r[f"alerts_per_day@{k}"] = t["alerts_per_day"]
            r[f"caught_per_100_alerts@{k}"] = t["events_caught_per_100_alerts"]
            if name == "LightGBM":
                caught[k] = t["caught_event_ids"]
        rows.append(r)
    metrics = pd.DataFrame(rows)
    pr = _pr_curve(te["y"].to_numpy(), s)
    return {"metrics": metrics, "base_rate": float(te["y"].mean()), "pr_curve": pr,
            "caught": caught, "n_test_events": topk_eval(te, s, ev, 25)["events"]}, te.assign(score=s)


def _pr_curve(y: np.ndarray, s: np.ndarray, n: int = 200) -> pd.DataFrame:
    from sklearn.metrics import precision_recall_curve
    p, r, _ = precision_recall_curve(y, s)
    idx = np.linspace(0, len(p) - 1, n).astype(int)
    return pd.DataFrame({"precision": p[idx], "recall": r[idx]})


def importance(model: lgb.Booster) -> pd.DataFrame:
    imp = pd.DataFrame({"feature": model.feature_name(),
                        "gain": model.feature_importance("gain")})
    imp["gain_pct"] = 100 * imp["gain"] / imp["gain"].sum()
    imp["label"] = imp["feature"].map(READABLE)
    return imp.sort_values("gain", ascending=False)


# ---------------------------------------------------------------- scoring + explanations
def score_period(model: lgb.Booster, F: pd.DataFrame, start) -> pd.DataFrame:
    """Score every running producing well-day from `start` (includes the final 14 days
    that have no label yet - those are the live watchlist)."""
    m = F["running"] & F["oil_30"].notna() & (F["production_date"] >= start)
    X = F.loc[m]
    out = X[["uwi", "production_date", "field_operating_area", "y", "days_to_onset"]].copy()
    out["label_known"] = X["eligible"].to_numpy()
    out["risk"] = model.predict(X[FEATURES]).astype("float32")
    out["risk_rank"] = out.groupby("production_date")["risk"].rank(ascending=False, method="first").astype("int32")
    return out


def explain(model: lgb.Booster, X: pd.DataFrame, top: int = 3) -> pd.DataFrame:
    """Per-row top positive SHAP drivers (LightGBM native TreeSHAP)."""
    contrib = model.predict(X[FEATURES], pred_contrib=True)[:, :-1]
    names = np.array([READABLE[f] for f in FEATURES])
    order = np.argsort(-contrib, axis=1)[:, :top]
    drivers = []
    for i, o in enumerate(order):
        parts = [f"{names[j]} ({_fmt(X.iloc[i][FEATURES[j]])})" for j in o if contrib[i, j] > 0]
        drivers.append("; ".join(parts))
    return pd.DataFrame({"uwi": X["uwi"].to_numpy(), "drivers": drivers}, index=X.index)


def _fmt(v) -> str:
    if isinstance(v, (float, np.floating)):
        if np.isnan(v):
            return "n/a"
        if float(v).is_integer():
            return f"{int(v):,}"
        return f"{v:.2f}" if abs(v) < 10 else f"{v:,.0f}"
    return str(v)
