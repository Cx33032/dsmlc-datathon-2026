"""Leakage tests: nothing a decision is made with may depend on data from after the decision."""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import dispatch, shock

ROOT = Path(__file__).resolve().parents[1]


def tiny_production(seed=0, n_days=500, wells=("A", "B", "C")):
    rng = np.random.default_rng(seed)
    rows = []
    for w in wells:
        days = pd.date_range("2025-01-01", periods=n_days)
        down = np.where(rng.random(n_days) < 0.05, rng.choice([6.0, 12.0, 24.0], n_days), 0.0)
        oil = rng.lognormal(1, 0.2, n_days) * (24 - down) / 24
        rows.append(pd.DataFrame({
            "uwi": w, "production_date": days, "field_operating_area": "X", "hours_down": down,
            "hours_on_prod": 24 - down, "oil_produced_m3": oil, "lost_oil_m3": np.where(down > 0, down / 24 * 2.7, np.nan),
            "downtime_code_1": np.where(down > 0, rng.choice(["Rods", "Pump"], n_days), None),
            "loss_category": np.where(down > 0, rng.choice(["Downhole - Rods", "Downhole - Pump"], n_days), "")}))
    df = pd.concat(rows, ignore_index=True)
    df["uwi"] = df["uwi"].astype("category")
    return df


DECISION_COLS = ["rate_h", "first_day_hours", "first_day_lost_m3", "hours_bin", "reason", "loss_category"]


def test_dispatch_features_use_data_up_to_close_of_day_D_only():
    df = tiny_production()
    t = dispatch.build_tickets(df)
    assert len(t) > 10
    cut = t["production_date"].sort_values().iloc[len(t) // 2]
    future = df["production_date"] > cut
    df2 = df.copy()
    rng = np.random.default_rng(99)
    df2.loc[future, "oil_produced_m3"] = rng.lognormal(3, 1, future.sum())
    df2.loc[future, "hours_down"] = rng.choice([0.0, 24.0], future.sum())
    df2.loc[future, "lost_oil_m3"] = 999.0
    t2 = dispatch.build_tickets(df2)
    a = t[t["production_date"] <= cut].set_index(["uwi", "production_date"])[DECISION_COLS]
    b = t2[t2["production_date"] <= cut].set_index(["uwi", "production_date"])[DECISION_COLS]
    common = a.index.intersection(b.index)
    assert len(common) > 5
    pd.testing.assert_frame_equal(a.loc[common], b.loc[common])


def test_dispatch_model_is_fitted_on_training_period_only():
    df = tiny_production(n_days=400)
    t = dispatch.build_tickets(df)
    train = t[t["production_date"] <= "2025-06-30"]
    m1 = dispatch.fit_shrunk_hours(train)
    t_bad = t.copy()
    t_bad.loc[t_bad["production_date"] > "2025-06-30", "future_down_h"] = 1e6
    m2 = dispatch.fit_shrunk_hours(t_bad[t_bad["production_date"] <= "2025-06-30"])
    assert m1["cell"] == m2["cell"]


def tiny_pump(seed=1, n_days=400):
    rng = np.random.default_rng(seed)
    rows = []
    for w in ("A", "B"):
        dt = pd.date_range("2025-01-01", periods=n_days)
        on = np.where(rng.random(n_days) < 0.1, 12.0, 24.0)
        rows.append(pd.DataFrame({"uwi": w, "dt": dt, "on_h": on, "down_h": 24 - on,
                                  "rpm": np.where(on >= 22, 200 + rng.normal(0, 15, n_days).round(), np.nan),
                                  "tq": np.where(on >= 22, 600 + rng.normal(0, 40, n_days), np.nan),
                                  "cur": np.where(on >= 22, 60 + rng.normal(0, 5, n_days), np.nan)}))
    return pd.concat(rows, ignore_index=True)


def test_shock_index_on_day_D_uses_rows_before_D_only():
    d = tiny_pump()
    a, _ = shock.add_shock_index(d)
    D = pd.Timestamp("2025-09-01")
    d2 = d.copy()
    later = d2["dt"] >= D
    d2.loc[later, ["rpm", "tq", "cur"]] *= 3.0
    d2.loc[later, "on_h"] = 0.0
    d2.loc[later, "down_h"] = 24.0
    b, _ = shock.add_shock_index(d2)
    keep = a["dt"] <= D
    assert a.loc[keep, "shock_index"].notna().sum() > 100
    pd.testing.assert_series_equal(a.loc[keep, "shock_index"], b.loc[keep, "shock_index"])
    assert not np.allclose(a.loc[~keep, "shock_index"].fillna(0), b.loc[~keep, "shock_index"].fillna(0))


def test_whiplash_hazard_window_ends_at_least_7_days_before_the_failure():
    src = (ROOT / "data/ideas/whiplash/shock_index.py").read_text(encoding="utf-8")
    gap = int(re.search(r"GAP_D, WIN_D = (\d+), (\d+)", src).group(1))
    assert gap >= 7
    assert 'h_anchor = r.fd - pd.Timedelta(days=GAP_D)' in src
    assert "val(u, s - pd.Timedelta(days=GAP_D))" in src   # Cox covariate is lagged the same way


def _rod_events():
    for d in ("outputs", "outputs_demo"):
        p = ROOT / d / "ideas" / "1" / "rod_events.parquet"
        if p.exists():
            return pd.read_parquet(p)
    pytest.skip("no rod_events artifact; run build_artifacts.py")


def test_cox_prior_history_uses_only_events_strictly_before_the_job():
    ev = _rod_events()
    ev["s"] = pd.to_datetime(ev["s"])
    rep = ev[ev["is_replace"] == 0]
    by = {u: g["s"].to_numpy() for u, g in rep.groupby("uwi")}
    sample = ev.sample(min(len(ev), 2000), random_state=0)
    for r in sample.itertuples():
        arr = by.get(r.uwi, np.array([], dtype="datetime64[ns]"))
        s = np.datetime64(r.s)
        expect = int(((arr < s) & (arr >= s - np.timedelta64(365, "D"))).sum())
        assert r.prior365 == expect


def test_facility_incident_flags_the_well_that_lags_the_restart():
    from src import facility
    days = pd.date_range("2025-01-01", periods=60)
    rows = []
    for i in range(8):
        back = 38 if i == 7 else 32                    # all down on day 30; well 7 is back 6 days after the rest
        on = np.where((np.arange(60) >= 30) & (np.arange(60) < back), 0.0, 24.0)
        rows.append(pd.DataFrame({"uwi": f"W{i}", "production_date": days, "facility_name": "F1",
                                  "field_operating_area": "X", "hours_on_prod": on, "hours_down": 24 - on,
                                  "oil_produced_m3": on / 24 * 3, "lost_oil_m3": np.where(on == 0, 3.0, np.nan),
                                  "loss_category": np.where(on == 0, "Facility & Turnarounds", "")}))
    df = pd.concat(rows, ignore_index=True)
    inc, lag, aff, info = facility.run(df)
    assert info["sync_days"] == 1 and info["incidents"] == 1
    assert list(lag["uwi"]) == ["W7"]
    assert lag["days_after_peers"].iloc[0] == 6
