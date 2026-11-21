"""Export well data + model outputs as Canary CSV Collector files (row-based format).

Each line is:  TagName,Timestamp,Value,Quality
  * TagName   = {Area}.{UWI}.{Measure}   (area/field roll-ups under {Area}._Area / _Field)
                The dataset ("Strathcona") is set in the collector config, so Canary shows
                Strathcona > Area > Well > Measure as a browsable tree.
  * Timestamp = ISO-8601 local time, one value per day (00:00)
  * Quality   = 192 Good | 64 Uncertain | 0 Bad   (the codes the CSV Collector accepts)
      - manual readings (pressures, torque, current, RPM) identical to the previous day are
        exported as Uncertain: they are carried-forward entries, not fresh measurements
      - raw values outside plausible limits (e.g. 999999 kPa, negative volumes) are exported
        with their raw value as Bad, so the historian keeps the evidence but trends skip them

Usage (after `python run_pipeline.py`):
  python canary/export_to_canary.py                          # 2026-01-01 onward, all areas (~330 MB)
  python canary/export_to_canary.py --start 2026-01-01 --areas Winter "Cactus Lake"
  python canary/export_to_canary.py --replay-dir C:/CanaryImport/Strathcona --replay-from 2026-09-01 --seconds 5
      -> drops one file per day into the collector's folder every 5 s ("live" demo)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DAILY, OUT  # noqa: E402
from src.data import LIMITS, LOSS_CATEGORIES, load_production  # noqa: E402
from src.losses import add_baseline  # noqa: E402

GOOD, UNCERTAIN, BAD = 192, 64, 0
WATCHLIST_K = 25

# daily column -> (tag measure, is_manual_reading)
MEASURES = {
    "oil_produced_m3": ("Oil_m3d", False), "water_produced_m3": ("Water_m3d", False),
    "gas_produced_e3m3": ("Gas_e3m3d", False), "hours_on_prod": ("HoursOn", False),
    "pump_efficiency_pct": ("PumpEfficiency", False),
    "pcp_pump_rpm": ("PumpRPM", True), "pcp_pump_rod_torque_ftlb": ("RodTorque_ftlb", True),
    "pcp_pump_electric_current_a": ("MotorCurrent_A", True),
    "casing_pressure_kpa": ("CasingPressure_kPa", True), "tubing_pressure_kpa": ("TubingPressure_kPa", True),
}
DERIVED = {"baseline_oil_m3d": "BaselineOil_m3d", "est_lost_oil_m3": "EstLostOil_m3",
           "downtime_flag": "Downtime", "loss_code": "LossCategoryCode"}
MODEL = {"risk": "FailureRisk14d", "risk_rank": "RiskRank", "alert": "RiskAlert"}


def clean(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_") or "Unknown"


def build_frame(start: str, end: str | None, areas: list[str] | None) -> pd.DataFrame:
    df, _ = load_production()
    df = add_baseline(df)  # baseline + estimated lost oil (needs history before `start`)
    m = df["production_date"] >= start
    if end:
        m &= df["production_date"] <= end
    if areas:
        m &= df["field_operating_area"].isin(areas)
    df = df.loc[m].copy()

    # raw (uncleaned) values so out-of-range readings can be exported as Bad quality
    raw = pq.read_table(DAILY, columns=["uwi", "production_date"] + [c for c in MEASURES if c in LIMITS],
                        filters=[("flow_direction", "==", "production")]).to_pandas()
    raw["production_date"] = pd.to_datetime(raw["production_date"]).astype("datetime64[ns]")
    raw = raw.drop_duplicates(["uwi", "production_date"], keep="last")
    raw = raw.rename(columns={c: f"raw_{c}" for c in raw.columns if c in MEASURES})
    raw["uwi"] = pd.Categorical(raw["uwi"], categories=df["uwi"].cat.categories)
    df = df.merge(raw, on=["uwi", "production_date"], how="left")

    df["downtime_flag"] = (df["hours_down"].fillna(0) > 0).astype(float)
    codes = {c: i for i, c in enumerate(LOSS_CATEGORIES, start=1)}
    df["loss_code"] = df["loss_category"].astype(str).map(codes).where(df["downtime_flag"] > 0, 0).astype(float)

    rs = pd.read_parquet(OUT / "risk_scores.parquet", columns=["uwi", "production_date", "risk", "risk_rank"])
    rs["uwi"] = pd.Categorical(rs["uwi"].astype(str), categories=df["uwi"].cat.categories)
    df = df.merge(rs, on=["uwi", "production_date"], how="left")
    info = json.loads((OUT / "model_info.json").read_text())
    # RiskAlert: 0 = normal, 1 = watch (top 5% on validation year), 2 = alarm (top 2%)
    df["alert"] = ((df["risk"] >= info["alert_threshold"]).astype(float)
                   + (df["risk"] >= info["alarm_threshold"]).astype(float)).where(df["risk"].notna())
    df["area_tag"] = df["field_operating_area"].astype(str).map(clean)
    df["uwi"] = df["uwi"].astype(str)
    return df.sort_values(["uwi", "production_date"]).reset_index(drop=True)


def to_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Long table: tag, ts, value, quality."""
    base = df["area_tag"] + "." + df["uwi"] + "."
    ts = df["production_date"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    parts = []
    g = df.groupby("uwi", sort=False)
    for col, (meas, manual) in MEASURES.items():
        val = df[col]
        q = pd.Series(GOOD, index=df.index)
        if manual:
            q = q.mask(val.notna() & (val == g[col].shift()), UNCERTAIN)
        rawc = f"raw_{col}"
        if rawc in df:
            bad = val.isna() & df[rawc].notna()
            val = val.where(~bad, df[rawc])
            q = q.mask(bad, BAD)
        parts.append(pd.DataFrame({"tag": base + meas, "ts": ts, "value": val, "quality": q}))
    for col, meas in {**DERIVED, **MODEL}.items():
        parts.append(pd.DataFrame({"tag": base + meas, "ts": ts, "value": df[col], "quality": GOOD}))

    # failure events as a pulse tag (1 on the outage-onset day) - shows as markers on Axiom trends
    ev = pd.read_parquet(OUT / "events.parquet", columns=["uwi", "onset_date", "job_cost"])
    ev = ev[ev["uwi"].isin(df["uwi"].unique()) & ev["onset_date"].between(df["production_date"].min(),
                                                                           df["production_date"].max())]
    area_of = df.drop_duplicates("uwi").set_index("uwi")["area_tag"]
    eb = area_of.reindex(ev["uwi"]).to_numpy() + "." + ev["uwi"].to_numpy() + "."
    for off, v in ((0, 1.0), (1, 0.0)):
        parts.append(pd.DataFrame({"tag": eb + "FailureEvent",
                                   "ts": (ev["onset_date"] + pd.Timedelta(days=off)).dt.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "value": v, "quality": GOOD}))
    parts.append(pd.DataFrame({"tag": eb + "RepairCost_CAD", "ts": ev["onset_date"].dt.strftime("%Y-%m-%dT%H:%M:%S"),
                               "value": ev["job_cost"], "quality": GOOD}))

    # area + field roll-ups
    avoid = df["loss_category"].astype(str) != "Shut-in (Uneconomic/LTSI)"
    df = df.assign(avoidable_lost=df["est_lost_oil_m3"].where(avoid, 0), on_watch=(df["risk_rank"] <= WATCHLIST_K),
                   running_f=df["running"].astype(float), ts=ts)
    agg = dict(Oil_m3d=("oil_produced_m3", "sum"), Water_m3d=("water_produced_m3", "sum"),
               EstLostOil_m3=("est_lost_oil_m3", "sum"), AvoidableLostOil_m3=("avoidable_lost", "sum"),
               RunningWells=("running_f", "sum"), WellsOnWatchlist=("on_watch", "sum"),
               WellsOnWatch=("alert", lambda x: (x >= 1).sum()),
               WellsInAlarm=("alert", lambda x: (x >= 2).sum()), MeanRisk=("risk", "mean"))
    for key, prefix in ((["area_tag", "ts"], None), (["ts"], "_Field._Total.")):
        r = df.groupby(key).agg(**agg).reset_index()
        pre = r["area_tag"] + "._Area." if prefix is None else prefix
        for meas in agg:
            parts.append(pd.DataFrame({"tag": pre + meas, "ts": r["ts"], "value": r[meas], "quality": GOOD}))

    out = pd.concat(parts, ignore_index=True)
    out = out[out["value"].notna()]
    out["value"] = out["value"].astype(float).round(4)
    return out


def write_files(lines: pd.DataFrame, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    lines = lines.assign(area=lines["tag"].str.split(".").str[0], year=lines["ts"].str[:4])
    paths = []
    for (area, year), g in lines.groupby(["area", "year"]):
        p = outdir / f"{area}_{year}.csv"
        g.sort_values(["tag", "ts"])[["tag", "ts", "value", "quality"]].to_csv(
            p, index=False, header=["TagName", "Timestamp", "Value", "Quality"])
        paths.append(p)
    return paths


def replay(lines: pd.DataFrame, target: Path, start: str, seconds: float):
    """Drop one CSV per day into the collector's watched folder to simulate live data."""
    target.mkdir(parents=True, exist_ok=True)
    days = sorted(d for d in lines["ts"].str[:10].unique() if d >= start)
    print(f"replaying {len(days)} days into {target} every {seconds}s (Ctrl+C to stop)")
    for d in days:
        g = lines[lines["ts"].str.startswith(d)]
        tmp = target / f".{d}.tmp"
        g[["tag", "ts", "value", "quality"]].to_csv(tmp, index=False,
                                                    header=["TagName", "Timestamp", "Value", "Quality"])
        tmp.rename(target / f"day_{d}.csv")  # atomic-ish: collector never sees a half-written file
        print(f"  {d}: {len(g):,} values")
        time.sleep(seconds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end")
    ap.add_argument("--areas", nargs="*")
    ap.add_argument("--out", default=str(OUT / "canary"))
    ap.add_argument("--replay-dir")
    ap.add_argument("--replay-from")
    ap.add_argument("--seconds", type=float, default=5.0)
    a = ap.parse_args()

    df = build_frame(a.start, a.end, a.areas)
    lines = to_lines(df)
    if a.replay_dir:
        replay(lines, Path(a.replay_dir), a.replay_from or a.start, a.seconds)
        return
    paths = write_files(lines, Path(a.out))
    tags = lines["tag"].nunique()
    q = lines["quality"].value_counts().to_dict()
    pd.DataFrame({"code": range(len(LOSS_CATEGORIES) + 1),
                  "loss_category": ["(no downtime)"] + LOSS_CATEGORIES}).to_csv(
        Path(a.out) / "LossCategoryCode_lookup.csv", index=False)
    print(f"wrote {len(paths)} files, {len(lines):,} values, {tags:,} tags -> {a.out}")
    print(f"quality counts: {q}  (192 good, 64 uncertain, 0 bad)")


if __name__ == "__main__":
    main()
