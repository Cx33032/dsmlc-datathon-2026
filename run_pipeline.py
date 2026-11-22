"""End-to-end pipeline: clean -> events -> losses (topic 2) -> model (topic 1) -> outputs.

Usage:  python run_pipeline.py           (about 3-6 minutes, ~3 GB RAM)
Outputs land in ./outputs and feed the Streamlit dashboard.
"""
from __future__ import annotations

import json
import time

import pandas as pd

from src import data, dispatch, facility, features, losses, model
from src.config import OUT


def log(msg: str, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def dump(obj, name):
    with open(OUT / name, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)


def main():
    log("loading + cleaning daily production")
    df, dq = data.load_production()
    dump(dq, "dq_report.json")
    data.stale_tag_report(df).to_csv(OUT / "stale_tags.csv", index=False)

    log("dispatch queue: score newly reported equipment outages + 2026 replay")
    tickets, replay, dinfo = dispatch.run(df)
    tickets.assign(uwi=tickets["uwi"].astype(str), field_operating_area=tickets["field_operating_area"].astype(str))         .query("production_date >= '2025-06-01'").to_parquet(OUT / "dispatch_tickets.parquet", index=False)
    replay.to_csv(OUT / "dispatch_replay.csv", index=False)
    dump(dinfo, "dispatch_info.json")

    log("facility restarts: synchronized outages + restart laggards")
    inc, lag, aff, finfo = facility.run(df)
    inc.to_parquet(OUT / "facility_incidents.parquet", index=False)
    lag.to_parquet(OUT / "facility_laggards.parquet", index=False)
    aff.to_parquet(OUT / "facility_affected.parquet", index=False)
    dump(finfo, "facility_info.json")

    log("building failure events from service jobs")
    jobs = data.load_jobs()
    ev = data.build_events(df, jobs)
    dump(data.validate_events(ev, data.load_failures()), "event_validation.json")

    log("features + labels")
    F = features.add_features(df, ev)

    log("topic 2: lost-oil estimation")
    df = losses.add_baseline(df)
    dump(losses.validate_estimate(df), "loss_validation.json")
    ev = losses.enrich_events(ev, df, F)
    for name, tbl in losses.loss_tables(df, ev).items():
        tbl.to_parquet(OUT / f"{name}.parquet", index=False)
    dump(losses.summary(df, ev), "loss_summary.json")

    log("topic 1: training LightGBM (time split)")
    booster, info = model.train(F)
    booster.save_model(str(OUT / "model.txt"))
    log(f"  best_iteration={info['best_iteration']}  valid AP={info['valid_ap_at_best']:.3f}")

    log("evaluating on held-out 2025-26")
    res, _ = model.evaluate(booster, F, ev)
    res["metrics"].to_csv(OUT / "metrics.csv", index=False)
    res["pr_curve"].to_csv(OUT / "pr_curve.csv", index=False)
    model.importance(booster).to_csv(OUT / "importance.csv", index=False)
    info.update(base_rate=res["base_rate"], n_test_events=res["n_test_events"])
    dump(info, "model_info.json")
    print(res["metrics"].drop(columns=[c for c in res["metrics"] if "median" in c]).round(3).to_string(index=False))

    tev = ev[ev["onset_date"] >= model.TEST_START].copy()
    for k, ids in res["caught"].items():
        tev[f"caught@{k}"] = tev["event_id"].isin(ids)
    tev["uwi"] = tev["uwi"].astype(str)
    tev.to_parquet(OUT / "test_events.parquet", index=False)
    ev.assign(uwi=ev["uwi"].astype(str)).to_parquet(OUT / "events.parquet", index=False)

    log("scoring 2025-26 + explaining the latest watchlist")
    sc = model.score_period(booster, F, model.TEST_START)
    sc.to_parquet(OUT / "risk_scores.parquet", index=False)
    last = sc["production_date"].max()
    top = sc[(sc["production_date"] == last)].nsmallest(100, "risk_rank")
    expl = model.explain(booster, F.loc[top.index])
    wl = top.join(expl[["drivers"]]).merge(
        pd.read_parquet(OUT / "wells.parquet")[["uwi", "formatted_uwi", "facility_name", "pump_make",
                                               "surface_latitude", "surface_longitude"]],
        on="uwi", how="left", suffixes=("", "_w"))
    wl = wl.join(F.loc[top.index, ["days_since_failure", "n_failures_365", "r_oil_7_30", "eff_30"]]
                 .reset_index(drop=True))
    wl.to_parquet(OUT / "watchlist.parquet", index=False)

    log("slim daily table for the dashboard drill-down (2024+)")
    keep = df["production_date"] >= "2024-01-01"
    slim = df.loc[keep, ["uwi", "production_date", "oil_produced_m3", "water_produced_m3",
                         "pump_efficiency_pct", "hours_on_prod", "baseline_oil_m3d", "est_lost_oil_m3",
                         "loss_category", "field_operating_area", "pcp_pump_rpm", "pcp_pump_rod_torque_ftlb",
                         "pcp_pump_electric_current_a", "hours_down"]].copy()
    slim["loss_category"] = slim["loss_category"].astype(str).where(df.loc[keep, "hours_down"] > 0, "")
    slim = slim.merge(sc[["uwi", "production_date", "risk", "risk_rank"]], on=["uwi", "production_date"], how="left")
    slim.to_parquet(OUT / "well_daily.parquet", index=False)
    log(f"done -> {OUT}")


if __name__ == "__main__":
    main()
