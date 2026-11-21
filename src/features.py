"""Per well-day features (past-only) and the 14-day failure label."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HORIZON_DAYS, RUNNING_HOURS

CAT_FEATURES = ["field_operating_area", "pump_make", "last_component"]


def _roll(df: pd.DataFrame, s: pd.Series, w: int, fn: str = "mean", minp: int | None = None) -> pd.Series:
    """Rolling window over the previous `w` days (inclusive of today) within each well.

    Rows are contiguous daily records per well (checked: >99.9% of gaps are 1 day),
    so a row window equals a day window.
    """
    r = s.groupby(df["uwi"], observed=True).rolling(w, min_periods=minp or max(2, w // 3))
    out = getattr(r, fn)()
    return out.reset_index(level=0, drop=True).sort_index()


def _safe_ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    r = a / b.where(b > 0)
    return r.clip(upper=5)


def add_features(df: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["uwi", "production_date"]).reset_index(drop=True)
    f = pd.DataFrame(index=df.index)
    oil = df["oil_produced_m3"]
    water = df["water_produced_m3"]
    fluid = oil + water
    rate = (oil * 24 / df["hours_on_prod"]).where(df["hours_on_prod"] >= RUNNING_HOURS)
    wcut = (water / fluid).where(fluid > 0)
    eff = df["pump_efficiency_pct"]

    oil_3, oil_7, oil_30, oil_90 = (_roll(df, oil, w) for w in (3, 7, 30, 90))
    oil_prev7 = oil_7.groupby(df["uwi"], observed=True).shift(7)
    f["oil_7"] = oil_7
    f["oil_30"] = oil_30
    f["r_oil_3_30"] = _safe_ratio(oil_3, oil_30)
    f["r_oil_7_30"] = _safe_ratio(oil_7, oil_30)
    f["r_oil_30_90"] = _safe_ratio(oil_30, oil_90)
    f["r_oil_7_prev7"] = _safe_ratio(oil_7, oil_prev7)
    f["oil_cv_14"] = (_roll(df, oil, 14, "std") / _roll(df, oil, 14)).clip(upper=5)

    rate_7, rate_30 = _roll(df, rate, 7, minp=2), _roll(df, rate, 30, minp=5)
    f["rate_30"] = rate_30
    f["r_rate_7_30"] = _safe_ratio(rate_7, rate_30)

    fl_7, fl_30 = _roll(df, fluid, 7), _roll(df, fluid, 30)
    f["fluid_7"] = fl_7
    f["r_fluid_7_30"] = _safe_ratio(fl_7, fl_30)
    f["wcut_30"] = _roll(df, wcut, 30, minp=5)
    f["d_wcut_7_30"] = _roll(df, wcut, 7, minp=2) - f["wcut_30"]

    e7, e30 = _roll(df, eff, 7, minp=2), _roll(df, eff, 30, minp=5)
    f["eff_30"] = e30
    f["r_eff_7_30"] = _safe_ratio(e7, e30)
    f["d_eff_7_30"] = e7 - e30

    hrs = df["hours_on_prod"]
    f["hrs_on_7"] = _roll(df, hrs, 7)
    f["down_days_30"] = _roll(df, (hrs < RUNNING_HOURS).astype("float32"), 30, "sum")
    f["gas_oil_30"] = _safe_ratio(_roll(df, df["gas_produced_e3m3"], 30), oil_30)

    # pump / pressure levels (mostly manual, forward-filled readings -> use as levels only)
    g = df.groupby("uwi", observed=True)
    for c, name in [("pcp_pump_rpm", "rpm"), ("pcp_pump_displacement_m3d100rpm", "displacement"),
                    ("pcp_pump_rod_torque_ftlb", "torque"), ("pcp_pump_electric_current_a", "current"),
                    ("casing_pressure_kpa", "casing_kpa"), ("tubing_pressure_kpa", "tubing_kpa")]:
        f[name] = g[c].ffill(limit=60)
    rated = f["displacement"] * f["rpm"] / 100
    f["vol_eff_7"] = _safe_ratio(fl_7, rated)

    f["well_age_yrs"] = ((df["production_date"] - df["on_production_date"]).dt.days / 365.25).clip(lower=0)
    f["month"] = df["production_date"].dt.month

    # failure history (past only) from event onsets
    on = ev.loc[ev["onset_date"].notna(), ["uwi", "onset_date", "component", "event_id"]]
    on = on.sort_values("onset_date").reset_index(drop=True)
    on["n_prior"] = on.groupby("uwi", observed=True).cumcount() + 1
    key = df[["uwi", "production_date"]].copy()
    key["_i"] = np.arange(len(key))
    key = key.sort_values("production_date")
    back = pd.merge_asof(key, on.rename(columns={"onset_date": "last_onset"}), left_on="production_date",
                         right_on="last_onset", by="uwi", direction="backward")
    key365 = key.assign(d365=key["production_date"] - pd.Timedelta(days=365))
    back365 = pd.merge_asof(key365.sort_values("d365"), on[["uwi", "onset_date", "n_prior"]],
                            left_on="d365", right_on="onset_date", by="uwi", direction="backward")
    back = back.sort_values("_i")
    back365 = back365.sort_values("_i")
    f["days_since_failure"] = (back["production_date"] - back["last_onset"]).dt.days.to_numpy()
    n_now = back["n_prior"].fillna(0).to_numpy()
    f["n_failures_prior"] = n_now
    f["n_failures_365"] = n_now - back365["n_prior"].fillna(0).to_numpy()
    f["last_component"] = pd.Categorical(back["component"].fillna("None").to_numpy())

    # label: does a failure outage start in (t, t+H]?
    fwd = pd.merge_asof(key, on[["uwi", "onset_date", "event_id"]],
        left_on="production_date", right_on="onset_date", by="uwi",
        direction="forward", allow_exact_matches=False).sort_values("_i")
    days_to = (fwd["onset_date"] - fwd["production_date"]).dt.days.to_numpy()
    f["days_to_onset"] = days_to
    f["next_event_id"] = fwd["event_id"].to_numpy()
    f["y"] = (days_to <= HORIZON_DAYS).astype("int8")

    for c in ["field_operating_area", "pump_make"]:
        f[c] = df[c]
    f["uwi"] = df["uwi"]
    f["production_date"] = df["production_date"]
    f["eligible"] = (df["running"] & (df["well_daily_status"] == "Producing")
                     & f["oil_30"].notna() & (df["production_date"] <= df["production_date"].max()
                                              - pd.Timedelta(days=HORIZON_DAYS)))
    f["running"] = df["running"]
    num = f.select_dtypes("float64").columns
    f[num] = f[num].astype("float32")
    return f


FEATURES = [
    "oil_7", "oil_30", "r_oil_3_30", "r_oil_7_30", "r_oil_30_90", "r_oil_7_prev7", "oil_cv_14",
    "rate_30", "r_rate_7_30", "fluid_7", "r_fluid_7_30", "wcut_30", "d_wcut_7_30",
    "eff_30", "r_eff_7_30", "d_eff_7_30", "hrs_on_7", "down_days_30", "gas_oil_30",
    "rpm", "displacement", "torque", "current", "casing_kpa", "tubing_kpa", "vol_eff_7",
    "well_age_yrs", "month", "days_since_failure", "n_failures_prior", "n_failures_365",
    "field_operating_area", "pump_make", "last_component",
]
