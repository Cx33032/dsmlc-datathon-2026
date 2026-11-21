"""Dispatch queue: which newly reported equipment outage should an engineer review first?

Reconstructed from the team's "Dispatch by the Barrel" spec (the original code is not in this repo):

  ticket  = a well-day D on which an equipment outage is newly reported (hours_down > 0 on D, no
            downtime on D-1, cause = downhole or surface equipment; uneconomic shut-ins excluded)
  score   = expected down hours over D+1..D+3, estimated per (reason x first-day-hours bin) on the
            training period and shrunk toward the bin mean with weight 40, multiplied by the well's
            trailing healthy oil rate / 24 (m3 of oil at risk over the next 3 days)
  baseline policy = rank by the first-day reported lost oil
  outcomes (retrospective, never shown in decision mode):
            reconstructed exposure = actual down hours D+1..D+3 x healthy rate / 24
            recorded loss          = reported lost_oil_m3 on D+1..D+3
  evaluation: each test day, review the top K tickets; capture = picked outcome / all outcome.

Leakage rule: everything a ticket is scored with is known at the close of day D.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import (DISPATCH_HORIZON_D, DISPATCH_SHRINK, DISPATCH_TEST_END, DISPATCH_TEST_START,
                        DISPATCH_TRAIN_END, HEALTHY_HOURS)

EQUIPMENT_CATEGORIES = ["Downhole - Rods", "Downhole - Pump", "Downhole - Tubing/Packer", "Downhole - Other",
                        "Surface Equipment"]
HOUR_BINS = [-0.01, 6, 18, 24.01]
HOUR_LABELS = ["0-6 h", ">6-18 h", ">18 h"]
ROD_PUMP = ["Downhole - Rods", "Downhole - Pump"]


def healthy_rate(df: pd.DataFrame, window: int = 30) -> pd.Series:
    """Trailing mean oil rate over healthy days (>=22 h up, non-negative oil), up to and including
    the previous day, carried forward up to 180 days. Index-aligned with df (sorted by uwi, date)."""
    ok = (df["hours_on_prod"] >= HEALTHY_HOURS) & (df["oil_produced_m3"] >= 0)
    v = df["oil_produced_m3"].where(ok)
    r = v.groupby(df["uwi"], observed=True).transform(
        lambda s: s.rolling(window, min_periods=3).mean().shift(1))
    return r.groupby(df["uwi"], observed=True).ffill(limit=180)


def build_tickets(df: pd.DataFrame) -> pd.DataFrame:
    """df: cleaned production rows from src.data.load_production, sorted by uwi/date, contiguous days."""
    df = df.sort_values(["uwi", "production_date"]).reset_index(drop=True)
    g = df.groupby("uwi", observed=True)
    down = df["hours_down"].fillna(0).clip(0, 24)
    df["rate_h"] = healthy_rate(df)
    prev_down = g["hours_down"].shift(1).fillna(0)
    prev_date = g["production_date"].shift(1)
    new = (down > 0) & (prev_down <= 0) & (prev_date == df["production_date"] - pd.Timedelta(days=1))
    new &= df["loss_category"].isin(EQUIPMENT_CATEGORIES)
    # future outcomes D+1..D+3 (only used as labels / retrospective view)
    fut_h = sum(g["hours_down"].shift(-k).fillna(0).clip(0, 24) for k in range(1, DISPATCH_HORIZON_D + 1))
    fut_lost = sum(g["lost_oil_m3"].shift(-k).fillna(0).clip(lower=0) for k in range(1, DISPATCH_HORIZON_D + 1))
    fut_ok = g["production_date"].shift(-DISPATCH_HORIZON_D) == df["production_date"] + pd.Timedelta(days=DISPATCH_HORIZON_D)
    t = df.loc[new & df["rate_h"].notna() & fut_ok, ["uwi", "production_date", "field_operating_area",
                                                   "downtime_code_1", "loss_category", "rate_h"]].copy()
    t["first_day_hours"] = down[t.index]
    t["first_day_lost_m3"] = df.loc[t.index, "lost_oil_m3"].fillna(0).clip(lower=0)
    t["hours_bin"] = pd.cut(t["first_day_hours"], HOUR_BINS, labels=HOUR_LABELS).astype(str)
    t["reason"] = t["downtime_code_1"].astype(str)
    t["future_down_h"] = fut_h[t.index]
    t["recorded_loss_m3"] = fut_lost[t.index]
    t["exposure_m3"] = t["future_down_h"] * t["rate_h"] / 24
    return t.drop(columns="downtime_code_1").reset_index(drop=True)


def fit_shrunk_hours(train: pd.DataFrame, k: float = DISPATCH_SHRINK) -> dict:
    """Mean future down hours by (reason, hours_bin), shrunk toward the hours_bin mean with weight k."""
    b = train.groupby("hours_bin")["future_down_h"].mean()
    rb = train.groupby(["reason", "hours_bin"])["future_down_h"].agg(["mean", "size"]).reset_index()
    rb["est"] = (rb["size"] * rb["mean"] + k * rb["hours_bin"].map(b)) / (rb["size"] + k)
    return {"bin": b.to_dict(), "cell": {(r.reason, r.hours_bin): r.est for r in rb.itertuples()},
            "n": {(r.reason, r.hours_bin): int(r.size) for r in rb.itertuples()}}


def score(t: pd.DataFrame, model: dict) -> pd.DataFrame:
    t = t.copy()
    t["est_down_h"] = [model["cell"].get((r, b), model["bin"].get(b, np.nan))
                       for r, b in zip(t["reason"], t["hours_bin"])]
    t["cell_n"] = [model["n"].get((r, b), 0) for r, b in zip(t["reason"], t["hours_bin"])]
    t["score_m3"] = t["est_down_h"] * t["rate_h"] / 24
    t["rank"] = t.groupby("production_date")["score_m3"].rank(ascending=False, method="first")
    return t


def capture(t: pd.DataFrame, by: str, outcome: str, k: int) -> float:
    """Share of the period's total outcome captured by reviewing the top-k tickets per day ranked by `by`."""
    top = t.sort_values(["production_date", by], ascending=[True, False]).groupby("production_date").head(k)
    return float(top[outcome].sum() / t[outcome].sum())


def replay_table(test: pd.DataFrame, ks=(1, 2, 3, 5)) -> pd.DataFrame:
    rows = []
    for k in ks:
        for outcome, lab in (("exposure_m3", "reconstructed exposure"), ("recorded_loss_m3", "recorded loss")):
            rows.append(dict(K=k, outcome=lab,
                             dispatch=capture(test, "score_m3", outcome, k),
                             first_day_loss=capture(test, "first_day_lost_m3", outcome, k),
                             oracle=capture(test, outcome, outcome, k)))
    return pd.DataFrame(rows)


def run(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    t = build_tickets(df)
    train = t[t["production_date"] <= DISPATCH_TRAIN_END]
    model = fit_shrunk_hours(train)
    t = score(t, model)
    test = t[t["production_date"].between(DISPATCH_TEST_START, DISPATCH_TEST_END)]
    rep = replay_table(test)
    info = {"tickets_train": int(len(train)), "tickets_test": int(len(test)),
            "test_days": int(test["production_date"].nunique()),
            "tickets_per_day": float(len(test) / max(test["production_date"].nunique(), 1))}
    return t, rep, info
