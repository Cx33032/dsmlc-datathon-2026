"""Mechanical Shock Index (Whiplash idea). Strictly past-only: the value on day D uses rows before D.

add_shock_index(d): d has one row per producing well-day, columns uwi, dt, on_h, down_h and screened
steady-state rpm / tq / cur (NaN when missing or not steady), sorted by uwi, dt.
Returns (d with shock_index + rpm_level_30, Z = the 10 within-well z-scored components).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_shock_index(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = d.copy()
    g = d.groupby("uwi", sort=False)
    prev_dt = g["dt"].shift(1)
    consec = prev_dt == d["dt"] - pd.Timedelta(days=1)
    for c in ("rpm", "tq", "cur"):
        d[f"d_{c}"] = (d[c] - g[c].shift(1)).where(consec)
    d["big_drpm"] = (d["d_rpm"].abs() >= 20).astype(float).where(d["d_rpm"].notna())
    up = d["on_h"] >= 22
    d["trans"] = ((up != g["on_h"].shift(1).ge(22)) & consec).astype(float) + ((d["down_h"] > 0) & (d["down_h"] < 24)).astype(float)

    comp = {}
    for w in (14, 30):
        r = lambda s, f: s.groupby(d["uwi"], sort=False).transform(lambda x: getattr(x.rolling(w, min_periods=w // 2), f)().shift(1))
        comp[f"sd_drpm_{w}"] = r(d["d_rpm"], "std")
        comp[f"n_big_drpm_{w}"] = r(d["big_drpm"], "sum")
        comp[f"cv_dtq_{w}"] = r(d["d_tq"], "std") / r(d["tq"], "mean")
        comp[f"cv_dcur_{w}"] = r(d["d_cur"], "std") / r(d["cur"], "mean")
        comp[f"n_trans_{w}"] = r(d["trans"], "sum")
    C = pd.DataFrame(comp)
    Z = pd.DataFrame(index=d.index)
    for c in C:
        x = C[c]
        m = x.groupby(d["uwi"], sort=False).transform(lambda s: s.expanding(60).mean().shift(1))
        sd = x.groupby(d["uwi"], sort=False).transform(lambda s: s.expanding(60).std().shift(1))
        Z[c] = ((x - m) / sd.replace(0, np.nan)).clip(-5, 5)
    d["shock_index"] = Z.mean(axis=1).where(Z.notna().sum(axis=1) >= 3)
    d["rpm_level_30"] = d.groupby("uwi", sort=False)["rpm"].transform(lambda s: s.rolling(30, min_periods=10).mean().shift(1))
    return d, Z
