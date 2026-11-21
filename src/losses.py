"""Topic 2 - estimate lost oil for every downtime day and attribute it to causes.

The reported `lost_oil_m3` is filled on only ~1/3 of rows, so we re-estimate it
for every downtime day as:  baseline_rate x hours_down / 24, where baseline_rate
is the well's trailing 30-day median oil rate on fully-running days (past only).
The reported value is used to validate the estimate where both exist.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import AVOIDABLE, FAILURE_CATEGORIES


def add_baseline(df: pd.DataFrame) -> pd.DataFrame:
    full = df["hours_on_prod"] >= 20
    rate = (df["oil_produced_m3"] * 24 / df["hours_on_prod"]).where(full)
    g = rate.groupby(df["uwi"], observed=True)
    base = g.rolling(30, min_periods=5).median().reset_index(level=0, drop=True).sort_index()
    base = base.groupby(df["uwi"], observed=True).shift(1)
    base = base.groupby(df["uwi"], observed=True).ffill(limit=180)
    df = df.copy()
    df["baseline_oil_m3d"] = base.astype("float32")
    down = df["hours_down"].fillna(0).clip(0, 24)
    df["est_lost_oil_m3"] = (df["baseline_oil_m3d"] * down / 24).where(down > 0, 0).fillna(0).astype("float32")
    df["avoidable"] = df["loss_category"].isin(AVOIDABLE) & (down > 0)
    return df


def validate_estimate(df: pd.DataFrame) -> dict:
    m = (df["lost_oil_m3"] > 0) & (df["est_lost_oil_m3"] > 0)
    a, b = df.loc[m, "lost_oil_m3"], df.loc[m, "est_lost_oil_m3"]
    return {"rows_compared": int(m.sum()), "pearson_r": round(float(np.corrcoef(a, b)[0, 1]), 3),
            "spearman_r": round(float(a.rank().corr(b.rank())), 3),
            "sum_est_over_sum_reported": round(float(b.sum() / a.sum()), 3),
            "reported_lost_oil_coverage_pct_of_downtime_days": round(
                100 * float((df.loc[df["hours_down"] > 0, "lost_oil_m3"].notna()).mean()), 1)}


def loss_tables(df: pd.DataFrame, ev: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = df[df["hours_down"].fillna(0) > 0].copy()
    d["month"] = d["production_date"].dt.to_period("M").dt.to_timestamp()
    d["year"] = d["production_date"].dt.year
    monthly = (d.groupby(["month", "field_operating_area", "loss_category"], observed=True)
                .agg(est_lost_oil_m3=("est_lost_oil_m3", "sum"),
                     reported_lost_oil_m3=("lost_oil_m3", "sum"),
                     hours_down=("hours_down", "sum"),
                     down_well_days=("hours_down", "size")).reset_index())
    monthly = monthly[monthly["hours_down"] > 0]

    by_well_year = (d.groupby(["uwi", "year", "loss_category"], observed=True)
                     .agg(est_lost_oil_m3=("est_lost_oil_m3", "sum"), hours_down=("hours_down", "sum"))
                     .reset_index())
    by_well_year = by_well_year[by_well_year["hours_down"] > 0]

    # production context per month / well
    p = df.assign(month=df["production_date"].dt.to_period("M").dt.to_timestamp())
    prod_month = (p.groupby(["month", "field_operating_area"], observed=True)
                   .agg(oil_m3=("oil_produced_m3", "sum"), water_m3=("water_produced_m3", "sum"),
                        running_well_days=("running", "sum")).reset_index())
    prod_month = prod_month[prod_month["running_well_days"] > 0]

    last = df.sort_values("production_date").groupby("uwi", observed=True).tail(1)
    wells = last[["uwi", "formatted_uwi", "field_operating_area", "facility_name", "province",
                  "surface_latitude", "surface_longitude", "pump_make", "pcp_pump_model",
                  "well_daily_status"]].copy()
    expo = (df.groupby([df["uwi"], df["production_date"].dt.year.rename("year")], observed=True)
              .agg(running_days=("running", "sum"), oil_m3=("oil_produced_m3", "sum")).reset_index())
    evy = (ev.groupby([ev["uwi"], ev["onset_date"].dt.year.rename("year")], observed=True)
             .agg(failures=("event_id", "size"), job_cost=("job_cost", "sum")).reset_index())
    well_year = expo.merge(evy, on=["uwi", "year"], how="left").fillna({"failures": 0, "job_cost": 0})
    return {"loss_monthly": monthly, "loss_by_well_year": by_well_year, "prod_monthly": prod_month,
            "wells": wells, "well_year": well_year}


def enrich_events(ev: pd.DataFrame, df: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Add per-event oil impact: hidden pre-failure decline + outage loss."""
    assert (df["uwi"].to_numpy() == feats["uwi"].to_numpy()).all()
    x = pd.DataFrame({"event_id": feats["next_event_id"], "k": feats["days_to_onset"],
                      "oil": df["oil_produced_m3"], "base": df["baseline_oil_m3d"]})
    ref = x[x["k"] == 15].groupby("event_id")["base"].first().rename("base_ref")
    w = x[x["k"].between(1, 14)].join(ref, on="event_id")
    w["deficit"] = (w["base_ref"] - w["oil"]).clip(lower=0)
    hidden = w.groupby("event_id")["deficit"].sum().rename("pre_failure_loss_m3")
    at_onset = x[x["k"] == 1].groupby("event_id")["base"].first().rename("baseline_at_onset_m3d")
    ev = ev.join(hidden, on="event_id").join(at_onset, on="event_id")
    ev["outage_loss_m3"] = ev["baseline_at_onset_m3d"] * ev["outage_days"].clip(upper=60)
    return ev


def summary(df: pd.DataFrame, ev: pd.DataFrame) -> dict:
    d = df[df["hours_down"].fillna(0) > 0]
    tot = d.groupby("loss_category", observed=True)["est_lost_oil_m3"].sum()
    yr = d.groupby([d["production_date"].dt.year, "avoidable"], observed=True)["est_lost_oil_m3"].sum().unstack()
    return {
        "est_avoidable_lost_oil_m3_total": round(float(tot.reindex(AVOIDABLE).sum()), 0),
        "est_failure_related_lost_oil_m3_total": round(float(tot.reindex(FAILURE_CATEGORIES).sum()), 0),
        "est_lost_by_category_m3": tot.sort_values(ascending=False).round(0).to_dict(),
        "est_avoidable_lost_by_year_m3": yr.get(True, pd.Series(dtype=float)).round(0).to_dict(),
        "events_total": int(len(ev)),
        "median_pre_failure_loss_m3": round(float(ev["pre_failure_loss_m3"].median()), 2),
        "median_outage_loss_m3": round(float(ev["outage_loss_m3"].median()), 2),
        "median_job_cost_cad": round(float(ev["job_cost"].median()), 0),
    }
