"""Facility restarts: group simultaneous outages into one facility incident, then flag the wells that
lag during the restart.

Definitions (fixed before looking at results):
  onset        a well that was running on D-1 (>= 12 h on) and is down on D (< 12 h on); uneconomic /
               long-term shut-ins excluded
  sync day     a facility-day on which >= 5 wells AND >= 25% of the facility's wells running on D-1 have an onset
  incident     sync days at the same facility within 3 days of each other; affected wells = their onset wells
  restart      a well's first running day after its onset (search window 60 days)
  T75          the day by which 75% of the incident's affected wells were back
  laggard      an affected well that restarts >= 3 days after T75 (or is still down 30 days after T75)
  recovery cohort = incidents where T75 is reached within 30 days of the incident start
  lag loss     days down beyond T75 x the well's trailing healthy rate (what a restart check could recover)

The live flag uses only data up to day D: on D, a well is flagged if it is still down while >= 75% of its
incident peers have been back for 3 days.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.dispatch import healthy_rate

MIN_WELLS, MIN_SHARE, MERGE_D, SEARCH_D = 5, 0.25, 3, 60
PEER_SHARE, LAG_D, T75_MAX_D = 0.75, 3, 30
RUN_H = 12.0
SHUTIN = "Shut-in (Uneconomic/LTSI)"


def run(df: pd.DataFrame):
    """Returns (incidents, laggards, affected well-outages, summary)."""
    df = df[df["facility_name"].notna()].sort_values(["uwi", "production_date"]).reset_index(drop=True)
    df = df.assign(uwi=df["uwi"].astype(str), facility_name=df["facility_name"].astype(str))
    df["rate_h"] = healthy_rate(df)
    g = df.groupby("uwi", sort=False)
    running = df["hours_on_prod"].fillna(0) >= RUN_H
    prev_run = g["hours_on_prod"].shift(1).fillna(0) >= RUN_H
    consec = g["production_date"].shift(1) == df["production_date"] - pd.Timedelta(days=1)
    onset = prev_run & ~running & consec & (df["loss_category"].astype(str) != SHUTIN)
    df["onset"], df["prev_run"] = onset, prev_run & consec

    fd = df.groupby(["facility_name", "production_date"]).agg(onsets=("onset", "sum"), base=("prev_run", "sum"))
    sync = fd[(fd["onsets"] >= MIN_WELLS) & (fd["onsets"] >= MIN_SHARE * fd["base"])].reset_index()
    if sync.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {"sync_days": 0}
    sync = sync.sort_values(["facility_name", "production_date"])
    new_inc = sync.groupby("facility_name")["production_date"].diff().dt.days.fillna(999) > MERGE_D
    sync["incident"] = new_inc.cumsum()

    on = df.loc[df["onset"], ["uwi", "facility_name", "production_date", "lost_oil_m3", "rate_h", "loss_category",
                              "field_operating_area"]]
    aff = on.merge(sync[["facility_name", "production_date", "incident"]], on=["facility_name", "production_date"])
    # restart day: first running day after onset (within SEARCH_D)
    run_days = df.loc[running, ["uwi", "production_date"]].rename(columns={"production_date": "restart"})
    aff = aff.sort_values("production_date")
    aff = pd.merge_asof(aff, run_days.sort_values("restart"), left_on="production_date", right_on="restart",
                        by="uwi", direction="forward", allow_exact_matches=False)
    aff.loc[(aff["restart"] - aff["production_date"]).dt.days > SEARCH_D, "restart"] = pd.NaT
    aff["days_down"] = (aff["restart"] - aff["production_date"]).dt.days

    inc_rows, lag_rows = [], []
    for inc, a in aff.groupby("incident"):
        start = a["production_date"].min()
        n = len(a)
        need = int(np.ceil(PEER_SHARE * n))
        back = a["restart"].dropna().sort_values()
        t75 = back.iloc[need - 1] if len(back) >= need else pd.NaT
        cohort = pd.notna(t75) and (t75 - start).days <= T75_MAX_D
        lag = pd.Series(False, index=a.index)
        lag_days = pd.Series(np.nan, index=a.index)
        if cohort:
            end = a["restart"].fillna(t75 + pd.Timedelta(days=T75_MAX_D))
            lag_days = (end - t75).dt.days.clip(lower=0)
            lag = lag_days >= LAG_D
        inc_rows.append(dict(incident=int(inc), facility_name=a["facility_name"].iloc[0],
                             area=str(a["field_operating_area"].iloc[0]), start=start,
                             sync_days=int(sync.loc[sync["incident"] == inc].shape[0]), wells=n,
                             onset_lost_oil_m3=float(a["lost_oil_m3"].fillna(0).clip(lower=0).sum()),
                             main_cause=a["loss_category"].astype(str).mode().iloc[0], t75=t75, recovery_cohort=cohort,
                             median_days_down=float(a["days_down"].median()), laggards=int(lag.sum())))
        for i in a.index[lag]:
            r = a.loc[i]
            lag_rows.append(dict(incident=int(inc), uwi=r["uwi"], facility_name=r["facility_name"],
                                 area=str(r["field_operating_area"]), onset=r["production_date"], t75=t75,
                                 restart=r["restart"], days_after_peers=float(lag_days[i]), rate_h=float(r["rate_h"])
                                 if pd.notna(r["rate_h"]) else np.nan,
                                 lag_loss_m3=float(lag_days[i] * r["rate_h"]) if pd.notna(r["rate_h"]) else np.nan,
                                 cause=str(r["loss_category"])))
    inc = pd.DataFrame(inc_rows)
    lag = pd.DataFrame(lag_rows)
    info = {"sync_days": int(len(sync)), "facilities": int(sync["facility_name"].nunique()),
            "incidents": int(len(inc)), "onset_lost_oil_m3": float(inc["onset_lost_oil_m3"].sum()),
            "affected_well_outages": int(inc["wells"].sum()),
            "cohort_incidents": int(inc["recovery_cohort"].sum()),
            "cohort_well_outages": int(inc.loc[inc["recovery_cohort"], "wells"].sum()),
            "laggard_cases": int(len(lag)), "laggard_wells": int(lag["uwi"].nunique()) if len(lag) else 0,
            "lag_loss_m3": float(lag["lag_loss_m3"].sum()) if len(lag) else 0.0,
            "repeat_laggard_wells": int((lag["uwi"].value_counts() >= 2).sum()) if len(lag) else 0,
            "definition": {"min_wells": MIN_WELLS, "min_share": MIN_SHARE, "merge_days": MERGE_D,
                           "peer_share": PEER_SHARE, "lag_days": LAG_D}}
    aff_out = aff[["incident", "uwi", "facility_name", "production_date", "restart", "days_down", "rate_h",
                   "lost_oil_m3"]].rename(columns={"production_date": "onset"})
    return inc, lag, aff_out, info
