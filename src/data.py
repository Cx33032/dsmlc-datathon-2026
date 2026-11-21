"""Loading, cleaning, downtime categorisation and failure-event construction."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .config import DAILY, FAILURES, JOBS, RUNNING_HOURS

PROD_COLS = [
    "uwi", "formatted_uwi", "field_operating_area", "province",
    "surface_latitude", "surface_longitude", "on_production_date", "facility_name",
    "well_daily_status", "primary_fluid_type", "production_date",
    "hours_down", "hours_on_prod", "lost_oil_m3", "downtime_code_1",
    "tubing_pressure_kpa", "casing_pressure_kpa",
    "oil_produced_m3", "gas_produced_e3m3", "water_produced_m3",
    "pump_efficiency_pct", "pcp_pump_make", "pcp_pump_model",
    "pcp_pump_displacement_m3d100rpm", "pcp_pump_rpm",
    "pcp_pump_electric_current_a", "pcp_pump_rod_torque_ftlb",
    "pcp_pump_volume_throughput_m3d",
]
CAT_COLS = ["uwi", "formatted_uwi", "field_operating_area", "province", "facility_name",
            "well_daily_status", "primary_fluid_type", "downtime_code_1",
            "pcp_pump_make", "pcp_pump_model"]

# Plausibility limits; values outside are treated as sensor/entry errors -> NaN.
LIMITS = {
    "oil_produced_m3": (0, 400), "water_produced_m3": (0, 5000), "gas_produced_e3m3": (0, 100),
    "tubing_pressure_kpa": (0, 20000), "casing_pressure_kpa": (0, 20000),
    "pump_efficiency_pct": (0, 3), "pcp_pump_rpm": (1, 1000),
    "pcp_pump_electric_current_a": (0, 1000), "pcp_pump_rod_torque_ftlb": (0, 20000),
    "pcp_pump_volume_throughput_m3d": (0, 5000), "lost_oil_m3": (0, 400),
}

# ---------------------------------------------------------------- downtime codes
LOSS_CATEGORIES = [
    "Downhole - Rods", "Downhole - Pump", "Downhole - Tubing/Packer", "Downhole - Other",
    "Surface Equipment", "Power", "Pipeline/Flowline", "Facility - Capacity",
    "Facility & Turnarounds", "Development/Planned Ops", "Planned Maintenance",
    "Other", "Uncoded", "Shut-in (Uneconomic/LTSI)",
]
AVOIDABLE = [c for c in LOSS_CATEGORIES if c not in ("Shut-in (Uneconomic/LTSI)",)]
FAILURE_CATEGORIES = ["Downhole - Rods", "Downhole - Pump", "Downhole - Tubing/Packer"]

_RULES = [  # first match wins; order matters
    ("Shut-in (Uneconomic/LTSI)", r"uneco|long term|ltsi|^suspended"),
    ("Surface Equipment", r"^surface|surf eqpt|surf ups|engine|wellhead|electrical|belt"),
    ("Downhole - Rods", r"rod"),
    ("Downhole - Pump", r"pump|torqued|gas-lock|lost suction"),
    ("Downhole - Tubing/Packer", r"tubing|packer"),
    ("Downhole - Other", r"downhole|\bdh\b|service rig|loaded up|plunger|waxed|disposal"),
    ("Power", r"power|grid|genset"),
    ("Pipeline/Flowline", r"pipeline|flowline|\bpipe\b"),
    ("Facility - Capacity", r"capacity|contraint|high pipe"),
    ("Development/Planned Ops", r"develop|drill|frac|stimulat|offset|eor|voidage|conc ops"),
    ("Facility & Turnarounds", r"facility|fac\b|plant|turn ?around|compressor|process|amine|"
                               r"inlet sep|third party|trucking|lift gas|water source"),
    ("Planned Maintenance", r"scheduled|planned"),
]


def categorize_downtime(code: str | float) -> str:
    if not isinstance(code, str) or not code.strip():
        return "Uncoded"
    c = code.lower()
    for cat, pat in _RULES:
        if re.search(pat, c):
            return cat
    return "Other"


def normalize_make(m: str | float) -> str:
    if not isinstance(m, str):
        return "Unknown"
    k = re.sub(r"[^A-Z]", "", m.upper())
    table = {"WEATHERFORD": "Weatherford", "PCM": "PCM", "MANTL": "Mantl", "BMWPUMP": "BMW",
             "BMW": "BMW", "LSI": "LSI", "LIFTINGSOLUTIONS": "LSI", "KUDU": "Kudu",
             "EUROPUMP": "Europump"}
    return table.get(k, "Other" if k not in ("PCP", "PCPPUMP", "") else "Unknown")


# ---------------------------------------------------------------- loading
def load_production(columns: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Producing-direction well-days, cleaned. Returns (df, data-quality report)."""
    cols = columns or PROD_COLS
    tbl = pq.read_table(DAILY, columns=cols, filters=[("flow_direction", "==", "production")])
    df = tbl.to_pandas()
    dq: dict[str, int] = {"rows_raw": len(df)}

    df["production_date"] = pd.to_datetime(df["production_date"]).astype("datetime64[ns]")
    if "on_production_date" in df:
        df["on_production_date"] = pd.to_datetime(df["on_production_date"]).astype("datetime64[ns]")
    for c in ("surface_latitude", "surface_longitude", "pcp_pump_rpm"):
        if c in df:
            df[c] = df[c].astype("float64")
    for c in CAT_COLS:
        if c in df:
            df[c] = df[c].astype("category")

    n0 = len(df)
    df = df.sort_values(["uwi", "production_date"]).drop_duplicates(["uwi", "production_date"], keep="last")
    dq["duplicate_well_days_removed"] = n0 - len(df)

    for c, (lo, hi) in LIMITS.items():
        if c in df:
            bad = df[c].notna() & ((df[c] < lo) | (df[c] > hi))
            dq[f"out_of_range_{c}"] = int(bad.sum())
            df.loc[bad, c] = np.nan

    df["running"] = (df["hours_on_prod"] >= RUNNING_HOURS) & df["oil_produced_m3"].notna()
    if "downtime_code_1" in df:
        cats = {c: categorize_downtime(c) for c in df["downtime_code_1"].cat.categories}
        df["loss_category"] = df["downtime_code_1"].map(cats).astype("object")
        df.loc[df["loss_category"].isna(), "loss_category"] = "Uncoded"
        df["loss_category"] = df["loss_category"].astype("category")
    if "pcp_pump_make" in df:
        mk = {c: normalize_make(c) for c in df["pcp_pump_make"].cat.categories}
        df["pump_make"] = df["pcp_pump_make"].map(mk).astype("object").fillna("Unknown").astype("category")
    df = df.reset_index(drop=True)
    dq["rows_clean"] = len(df)
    return df, dq


def stale_tag_report(df: pd.DataFrame) -> pd.DataFrame:
    """Share of readings identical to the previous day (forward-filled manual readings)."""
    cols = ["tubing_pressure_kpa", "casing_pressure_kpa", "pcp_pump_rpm",
            "pcp_pump_rod_torque_ftlb", "pcp_pump_electric_current_a",
            "pump_efficiency_pct", "oil_produced_m3", "water_produced_m3"]
    rows = []
    g = df.groupby("uwi", observed=True)
    for c in cols:
        prev = g[c].shift()
        m = df[c].notna() & prev.notna()
        rows.append({"tag": c, "coverage_pct": 100 * df[c].notna().mean(),
                     "repeat_prev_day_pct": 100 * (df.loc[m, c] == prev[m]).mean()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- failure events
FAILURE_JOB_TYPES = {
    "Rod Truck": {"Corod Rod Repair", "Rod Repair", "Stick Rod Repair", "Polish Rod Repair", "Rotor Change"},
    "Workover": {"Pump Repair/Replacement", "Tubing Repair", "Rod Break - Corod", "PCP Replacement",
                 "Pump Repair", "Rod Repair", "Packer Repair", "Rod Break - Stick", "BHP Replacement",
                 "ESP Replacement", "ESP Repair", "Casing Repair", "Casing Failure",
                 "Down Hole Equipment Repair", "Polish Rod Repair"},
}


def failure_component(job_type: str) -> str:
    t = job_type.lower()
    if "rod" in t:
        return "Rods"
    if "pump" in t or "pcp" in t or "rotor" in t or "esp" in t or "bhp" in t:
        return "Pump"
    if "tubing" in t or "packer" in t:
        return "Tubing/Packer"
    return "Other"


def load_jobs() -> pd.DataFrame:
    j = pd.read_parquet(JOBS)
    j["start_date"] = pd.to_datetime(j["start_date"]).astype("datetime64[ns]")
    j["end_date"] = pd.to_datetime(j["end_date"], errors="coerce").astype("datetime64[ns]")
    j["is_failure_job"] = [jt in FAILURE_JOB_TYPES.get(jc, set())
                           for jc, jt in zip(j["job_category"], j["job_type"])]
    return j


def load_failures() -> pd.DataFrame:
    f = pd.read_parquet(FAILURES)
    f["failure_start_date"] = pd.to_datetime(f["failure_start_date"]).astype("datetime64[ns]")
    return f


def build_events(df: pd.DataFrame, jobs: pd.DataFrame, merge_days: int = 7) -> pd.DataFrame:
    """One row per failure event, with outage onset and return-to-service dates.

    Event = a failure-repair job (consistent definition across all six years; the
    failure log only covers 2025-26 and is used to validate this proxy).
    onset = day after the last running day on/before the job start (the outage
    usually begins 1-3 days before the job is logged). Jobs on the same well within
    `merge_days` of each other are merged into one event.
    """
    fj = jobs.loc[jobs["is_failure_job"], ["uwi", "start_date", "job_category", "job_type",
                                           "job_subtype", "field_est_total"]].copy()
    fj = fj[fj["uwi"].isin(df["uwi"].cat.categories)]
    fj["uwi"] = pd.Categorical(fj["uwi"], categories=df["uwi"].cat.categories)
    fj = fj.sort_values(["uwi", "start_date"])
    # merge jobs close together on the same well
    gap = fj.groupby("uwi", observed=True)["start_date"].diff().dt.days
    fj["event_no"] = (gap.isna() | (gap > merge_days)).cumsum()
    ev = fj.groupby("event_no").agg(
        uwi=("uwi", "first"), job_date=("start_date", "first"),
        job_category=("job_category", lambda s: "Workover" if (s == "Workover").any() else "Rod Truck"),
        job_type=("job_type", "first"), job_subtype=("job_subtype", "first"),
        job_cost=("field_est_total", "sum"), n_jobs=("start_date", "size"),
    ).reset_index(drop=True)
    ev["uwi"] = pd.Categorical(ev["uwi"], categories=df["uwi"].cat.categories)
    ev["component"] = ev["job_type"].map(failure_component)

    run = df.loc[df["running"], ["uwi", "production_date"]].rename(columns={"production_date": "run_date"})
    run = run.sort_values("run_date")
    e = ev.sort_values("job_date")
    last_run = pd.merge_asof(e, run, left_on="job_date", right_on="run_date", by="uwi",
                             direction="backward", tolerance=pd.Timedelta(days=60))
    last_run = last_run.rename(columns={"run_date": "last_run_date"})
    nxt = pd.merge_asof(last_run.sort_values("job_date"), run, left_on="job_date", right_on="run_date",
                        by="uwi", direction="forward", allow_exact_matches=False,
                        tolerance=pd.Timedelta(days=120))
    ev = nxt.rename(columns={"run_date": "back_online_date"})
    ev["onset_date"] = (ev["last_run_date"] + pd.Timedelta(days=1)).where(
        ev["last_run_date"].notna(), pd.NaT)
    ev["onset_date"] = ev[["onset_date", "job_date"]].min(axis=1)
    # predictable = the well was running shortly before the outage (not a long shut-in)
    ev["predictable"] = ev["last_run_date"].notna() & (
        (ev["job_date"] - ev["last_run_date"]).dt.days <= 30)
    ev["outage_days"] = (ev["back_online_date"] - ev["onset_date"]).dt.days
    ev = ev.sort_values(["uwi", "onset_date"]).reset_index(drop=True)
    ev["event_id"] = np.arange(len(ev))
    return ev


def validate_events(ev: pd.DataFrame, failures: pd.DataFrame, window: int = 14) -> dict:
    """How well the job-based events line up with the independent failure log (2025-26)."""
    f = failures[["uwi", "failure_start_date"]].dropna().copy()
    f = f[f["failure_start_date"] >= "2025-01-01"]
    e = ev.loc[ev["job_date"] >= "2025-01-01", ["uwi", "job_date"]].copy()
    e["uwi"] = e["uwi"].astype(str)
    m = f.merge(e, on="uwi", how="left")
    m["dt"] = (m["job_date"] - m["failure_start_date"]).dt.days.abs()
    f_hit = m.groupby(["uwi", "failure_start_date"])["dt"].min().le(window).mean()
    m2 = e.merge(f, on="uwi", how="left")
    m2["dt"] = (m2["failure_start_date"] - m2["job_date"]).dt.days.abs()
    e_hit = m2.groupby(["uwi", "job_date"])["dt"].min().le(window).mean()
    return {"failure_log_records_2025_26": int(len(f)),
            "job_events_2025_26": int(len(e)),
            "pct_failure_records_matched_by_job_event": round(100 * f_hit, 1),
            "pct_job_events_matched_by_failure_record": round(100 * e_hit, 1),
            "match_window_days": window}
