"""Synthetic demo data with the same schemas as the three competition parquets.

Nothing here comes from the competition data: well IDs, areas, coordinates, rates, costs, dates of
events and every line of crew-style text are generated from the random rules below. The point is that
the whole app (pipeline, ideas, dispatch, decision rule, pages) runs from a clean clone.

    from src.demo import generate; generate(Path("demo_data"))

Built-in structure, so the demo pages have something to show:
  * each well has a rod-failure rate (a few chronic wells fail 4-8x a year)
  * a new rod string halves the failure rate for two years
  * each well has a weak depth zone, and most breaks happen near it
  * each well leans to Corrosion, Fatigue or Load failures; some Fatigue notes mention pitting
  * manual pump tags (RPM, torque, current, pressures) are carried forward between visits
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

START, END = pd.Timestamp("2021-01-01"), pd.Timestamp("2026-10-27")
FAIL_LOG_START = pd.Timestamp("2025-06-01")
AREAS = {"North Lake": 1.6, "Ridgeview": 1.0, "Basin West": 0.8, "Cold Creek": 1.2, "Prairie Flats": 0.6}
MAKES = ["Acme PCP", "Borealis", "Kestrel", "Northstar"]
REPAIR_TYPES = ["Corod Rod Repair", "Rod Repair", "Stick Rod Repair"]
REPLACE_TYPES = ["Corod Rod  Replacement - New String", "Stick Rod Replacement - New String"]
OTHER_DOWN = [("Facility - Limited Capacity", "Facility", 0.010), ("Power Source/Supply - Unplanned - Grid", "Power Source/Supply", 0.006),
              ("Surface Equipment - Belt Problems", "Surface Equipment", 0.004),
              ("Surface Equipment - Engine/Motor Down", "Surface Equipment", 0.003),
              ("ALL - Facility - Turn Around", "Facility", 0.002)]
ROD_CODE = ("Downhole Equipment - Rods", "Downhole Equipment")
PUMP_CODE = ("Downhole Equipment - Pump", "Downhole Equipment")
TUBING_CODE = ("Downhole Equipment - Tubing Failure", "Downhole Equipment")


def _schema_daily() -> pa.Schema:
    s, d, dt = pa.string(), pa.float64(), pa.date32()
    return pa.schema([
        ("uwi", s), ("formatted_uwi", s), ("well_name", s), ("field_operating_area", s), ("province", s),
        ("surface_latitude", pa.decimal128(9, 7)), ("surface_longitude", pa.decimal128(10, 7)),
        ("on_production_date", dt), ("facility_name", s), ("well_daily_status", s), ("primary_fluid_type", s),
        ("flow_direction", s), ("production_date", dt), ("hours_down", d), ("hours_on_prod", d), ("lost_oil_m3", d),
        ("downtime_code_1", s), ("downtime_code_2", s), ("downtime_code_3", s), ("tubing_pressure_kpa", d),
        ("casing_pressure_kpa", d), ("injection_pressure_kpa", d), ("well_status", s), ("oil_produced_m3", d),
        ("gas_produced_e3m3", d), ("injection_volume_m3", d), ("injected_water_m3", d), ("injected_polymer_m3", d),
        ("pump_efficiency_pct", d), ("water_produced_m3", d), ("hydraulic_pressure_psi", d), ("choke_open_pct", d),
        ("pcp_pump_name", s), ("pcp_pump_make", s), ("pcp_pump_model", s), ("pcp_pump_displacement_m3d100rpm", d),
        ("pcp_pump_rpm", pa.decimal128(5, 0)), ("pcp_pump_comment", s), ("pcp_pump_electric_current_a", d),
        ("pcp_pump_rod_torque_ftlb", d), ("pcp_pump_volume_throughput_m3d", d)])


def _manual_tag(rng, n, level, sd, visit_every=(7, 30)):
    """A manually read tag: a new reading every 1-4 weeks, carried forward in between."""
    out = np.empty(n)
    i, v = 0, level
    while i < n:
        step = int(rng.integers(*visit_every))
        v = max(level + rng.normal(0, sd), 1)
        out[i:i + step] = v
        i += step
    return out


def _note(rng, cause, depth, stick):
    if depth is None:
        return rng.choice(["Broken rod", "Rod parted, no depth noted", "Pulled rods, broken string", None])
    if stick and rng.random() < 0.5:
        joint = max(int(round(depth / 7.62)), 1)
        base = rng.choice([f"Broken stick rod {joint}th", f"Broken pin on JT #{joint}", f"Parted rod #{joint}"])
    else:
        base = rng.choice([f"Broken corod @ {depth:.0f}m", f"Corod parted at {depth:.0f} m", f"Broken rod @ {depth:.0f}m"])
    if cause == "Corrosion" or (cause == "Fatigue" and rng.random() < 0.15):
        base += rng.choice([", heavy pitting on body", ", corrosion pits at break", ", rust and pitting noted"])
    return base


def _summary(rng, depth, cause):
    parts = ["MIRU rod truck.", "Pulled rods."]
    if depth is not None and rng.random() < 0.6:
        parts.append(f"Found rods broken at {depth:.0f}m.")
    if cause == "Corrosion":
        parts.append(rng.choice(["Minor pitting on several joints.", "Corrosion on rod body, replaced joints."]))
    elif cause == "Load / Excess Stress":
        parts.append("Break due to stress near coupling.")
    else:
        parts.append(rng.choice(["Rod wear on couplings, added guides.", "Replaced broken joint, ran back in."]))
    parts.append(f"Pulled free at {rng.integers(8, 16)},000 lbs. RDMO.")
    return " ".join(parts)


def generate(out_dir: Path, n_wells: int = 240, seed: int = 26) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    days = pd.date_range(START, END, freq="D")
    n = len(days)
    areas = list(AREAS)
    daily, jobs, fails = [], [], []
    # facility-wide outages (ESD / turnaround / power): ~2 a year per battery, most wells go down together
    fac_events = {}
    for a in areas:
        for b in (1, 2, 3):
            starts = np.flatnonzero(rng.random(n) < 2 / 365)
            fac_events[f"{a} Battery {b}"] = [(int(t0), int(rng.integers(1, 5)),
                                               rng.choice(["Facility - ESD", "ALL - Facility - Turn Around",
                                                           "Power Source/Supply - Unplanned - Grid"])) for t0 in starts]
    for w in range(n_wells):
        area = areas[w % len(areas)]
        uwi = f"DEMO{w:03d}{area[:2].upper()}W4"
        on_prod = START - pd.Timedelta(days=int(rng.integers(200, 4000)))
        rate0 = float(rng.lognormal(np.log(3.0), 0.6))
        wc = float(rng.uniform(0.90, 0.975))
        lam = float(rng.gamma(1.6, 1.0)) * AREAS[area] * (3.0 if rng.random() < 0.12 else 1.0)  # rod failures / yr
        cause_mix = rng.dirichlet([2.0, 3.0, 0.8])  # Corrosion, Fatigue, Load
        weak = float(rng.uniform(150, 850))
        stick = rng.random() < 0.3
        make = MAKES[w % len(MAKES)]
        disp = float(rng.choice([12.0, 18.0, 25.0, 32.0]))
        rpm_level = float(rng.uniform(120, 320))
        shutin_from = n - int(rng.integers(100, 400)) if rng.random() < 0.08 else n

        down = np.zeros(n)
        code1 = np.full(n, None, dtype=object)
        code2 = np.full(n, None, dtype=object)
        decline = np.ones(n)
        new_string_until = -1
        t = int(rng.integers(0, 120))
        while t < n:
            # rod failure process; a new string halves the hazard for 2 years
            mult = 0.45 if t <= new_string_until else 1.0
            gap = int(rng.exponential(365 / max(lam * mult, 0.05)))
            t += max(gap, 5)
            if t >= n - 2 or t >= shutin_from:
                break
            dur = int(rng.integers(1, 6))
            first = float(rng.choice([6.0, 12.0, 24.0], p=[0.3, 0.45, 0.25]))
            down[t] = first
            down[t + 1:t + dur] = 24.0
            code1[t:t + dur], code2[t:t + dur] = ROD_CODE
            decline[max(t - 10, 0):t] *= np.linspace(1.0, 0.75, len(decline[max(t - 10, 0):t]))
            d = days[t]
            replace = rng.random() < (0.12 if lam > 3 else 0.05)
            if replace:
                new_string_until = t + 730
            cause = rng.choice(["Corrosion", "Fatigue", "Load / Excess Stress"], p=cause_mix)
            depth = weak + rng.normal(0, 25) if rng.random() < 0.6 else float(rng.uniform(40, 950))
            depth = float(np.clip(depth, 15, 990))
            located = rng.random() < 0.55
            jt = rng.choice(REPLACE_TYPES if replace else REPAIR_TYPES)
            if stick and "Corod" in jt:
                jt = jt.replace("Corod", "Stick").replace("Stick Rod  Replacement", "Stick Rod Replacement")
            cost = float(rng.lognormal(np.log(22000 if replace else 7000), 0.35)) if rng.random() > 0.1 else 0.0
            jobs.append(dict(uwi=uwi, field_operating_area=area, job_category="Rod Truck" if not replace else "Workover",
                             job_type=jt, start_date=(d + pd.Timedelta(days=1)).date(),
                             end_date=(d + pd.Timedelta(days=dur)).date(), job_duration_days=float(dur),
                             objective="Repair rod string" if not replace else "Run new rod string",
                             summary=_summary(rng, depth if located else None, cause), field_est_total=cost))
            if d >= FAIL_LOG_START:
                fails.append(dict(uwi=uwi, field_operating_area=area, failure_start_date=d.date(),
                                  failure_end_date=(d + pd.Timedelta(days=dur)).date(), cause=cause,
                                  failure_detail="Stick rod" if stick else "Corod",
                                  failure_comments=_note(rng, cause, depth if located else None, stick),
                                  failure_type="Rods", action_taken="Repaired" if not replace else "Replaced"))
        # occasional pump / tubing failures and other downtime
        for code, p, ftype, jt in ((PUMP_CODE, 0.0012, "Pump", "Pump Repair/Replacement"),
                                   (TUBING_CODE, 0.0008, "Tubing", "Tubing Repair")):
            for t0 in np.flatnonzero(rng.random(n) < p):
                if down[t0] > 0 or t0 >= shutin_from or t0 >= n - 3:
                    continue
                dur = int(rng.integers(2, 7))
                down[t0:t0 + dur] = 24.0
                code1[t0:t0 + dur], code2[t0:t0 + dur] = code
                jobs.append(dict(uwi=uwi, field_operating_area=area, job_category="Workover", job_type=jt,
                                 start_date=(days[t0] + pd.Timedelta(days=1)).date(),
                                 end_date=(days[t0] + pd.Timedelta(days=dur)).date(), job_duration_days=float(dur),
                                 objective=f"Repair {ftype.lower()}", summary=f"MIRU. {ftype} repaired. RDMO.",
                                 field_est_total=float(rng.lognormal(np.log(15000), 0.4))))
                if days[t0] >= FAIL_LOG_START:
                    fails.append(dict(uwi=uwi, field_operating_area=area, failure_start_date=days[t0].date(),
                                      failure_end_date=(days[t0] + pd.Timedelta(days=dur)).date(), cause="Wear",
                                      failure_detail=ftype, failure_comments=f"{ftype} failure", failure_type=ftype,
                                      action_taken="Repaired"))
        for t0, dur, c1 in fac_events[f"{area} Battery {1 + w % 3}"]:
            if t0 >= shutin_from or rng.random() > 0.9:
                continue
            extra = int(rng.integers(3, 12)) if rng.random() < 0.08 else int(rng.integers(0, 2))   # restart laggards
            sl = slice(t0, min(t0 + dur + extra, n))
            free = down[sl] == 0
            down[sl] = np.where(free, 24.0, down[sl])
            code1[sl] = np.where(free, c1, code1[sl])
            code2[sl] = np.where(free, c1.split(" - ")[0] if not c1.startswith("ALL") else "Facility", code2[sl])
        for c1, c2, p in OTHER_DOWN:
            for t0 in np.flatnonzero(rng.random(n) < p):
                if down[t0] == 0:
                    down[t0] = float(rng.choice([4.0, 8.0, 12.0, 24.0]))
                    code1[t0], code2[t0] = c1, c2
        down[shutin_from:] = 24.0
        code1[shutin_from:], code2[shutin_from:] = "Uneconomic - Long Term Shut In", "Uneconomic"

        trend = rate0 * np.exp(-np.arange(n) / 365 * rng.uniform(0.02, 0.12))
        healthy = trend * decline * rng.lognormal(0, 0.12, n)
        on = 24.0 - down
        oil = healthy * on / 24
        lost = np.where(down > 0, healthy * down / 24 * rng.lognormal(0, 0.15, n), np.nan)
        lost[shutin_from:] = np.nan
        water = oil * wc / (1 - wc)
        rpm = _manual_tag(rng, n, rpm_level, 25) * (on > 0)
        status = np.where(np.arange(n) >= shutin_from, "Shut-in", "Producing")
        daily.append(pd.DataFrame({
            "uwi": uwi, "formatted_uwi": f"DEMO/{w:03d}-{area[:2].upper()}/0", "well_name": f"Demo {area} {w:03d}",
            "field_operating_area": area, "province": "Alberta" if w % 3 else "Saskatchewan",
            "surface_latitude": round(53.0 + w % 20 * 0.05 + rng.uniform(0, 0.02), 7),
            "surface_longitude": round(-110.0 - w // 20 * 0.07 - rng.uniform(0, 0.02), 7),
            "on_production_date": on_prod.date(), "facility_name": f"{area} Battery {1 + w % 3}",
            "well_daily_status": status, "primary_fluid_type": "Oil", "flow_direction": "production",
            "production_date": days.date, "hours_down": down, "hours_on_prod": on, "lost_oil_m3": lost,
            "downtime_code_1": code1, "downtime_code_2": code2, "downtime_code_3": None,
            "tubing_pressure_kpa": _manual_tag(rng, n, 1200, 200), "casing_pressure_kpa": _manual_tag(rng, n, 300, 80),
            "injection_pressure_kpa": np.nan, "well_status": "Active", "oil_produced_m3": oil,
            "gas_produced_e3m3": oil * rng.uniform(0.01, 0.05), "injection_volume_m3": np.nan, "injected_water_m3": np.nan,
            "injected_polymer_m3": np.nan, "pump_efficiency_pct": np.clip((oil + water) / (disp * rpm / 100 + 1e-9), 0, 2.5),
            "water_produced_m3": water, "hydraulic_pressure_psi": np.nan, "choke_open_pct": np.nan,
            "pcp_pump_name": f"{make} {int(disp)}", "pcp_pump_make": make, "pcp_pump_model": f"{int(disp)}-1200",
            "pcp_pump_displacement_m3d100rpm": disp, "pcp_pump_rpm": np.round(rpm), "pcp_pump_comment": None,
            "pcp_pump_electric_current_a": _manual_tag(rng, n, 40 + rpm_level / 10, 6) * (on > 0),
            "pcp_pump_rod_torque_ftlb": _manual_tag(rng, n, 400 + rpm_level, 60) * (on > 0),
            "pcp_pump_volume_throughput_m3d": disp * rpm / 100}))

    d = pd.concat(daily, ignore_index=True)
    for c in ("pcp_pump_rpm", "pcp_pump_electric_current_a", "pcp_pump_rod_torque_ftlb"):
        d[c] = d[c].where(d[c] > 0)
    sch = _schema_daily()
    d["surface_latitude"] = d["surface_latitude"].map(lambda x: __import__("decimal").Decimal(f"{x:.7f}"))
    d["surface_longitude"] = d["surface_longitude"].map(lambda x: __import__("decimal").Decimal(f"{x:.7f}"))
    d["pcp_pump_rpm"] = d["pcp_pump_rpm"].map(lambda x: None if pd.isna(x) else __import__("decimal").Decimal(int(x)))
    pq.write_table(pa.Table.from_pandas(d[sch.names], schema=sch, preserve_index=False), out_dir / "daily_production.parquet")

    j = pd.DataFrame(jobs)
    j["formatted_uwi"] = j["uwi"]
    j["well_name"] = j["uwi"]
    for c in ("job_subtype", "job_status_1", "job_status_2"):
        j[c] = None
    for c in ("actual_final_job_cost", "afe_cost_total", "afe_and_supp_cost_total", "duration_time_log_spud_td_hrs"):
        j[c] = np.nan
    j["start_date"] = pd.to_datetime(j["start_date"]).dt.date
    j["end_date"] = pd.to_datetime(j["end_date"]).dt.date
    jcols = ["uwi", "formatted_uwi", "well_name", "field_operating_area", "job_category", "job_type", "job_subtype",
             "start_date", "end_date", "job_duration_days", "job_status_1", "job_status_2", "objective", "summary",
             "actual_final_job_cost", "afe_cost_total", "afe_and_supp_cost_total", "field_est_total",
             "duration_time_log_spud_td_hrs"]
    j[jcols].to_parquet(out_dir / "well_jobs.parquet", index=False)

    f = pd.DataFrame(fails)
    f["formatted_uwi"] = f["uwi"]
    f["well_name"] = f["uwi"]
    for c in ("cause_detail", "failure_description", "failure_system", "cause_comments"):
        f[c] = None
    for c in ("cause_category", "failure_system_category", "failure_type_category"):
        f[c] = None
    fcols = ["uwi", "formatted_uwi", "well_name", "field_operating_area", "failure_start_date", "failure_end_date",
             "cause", "cause_detail", "cause_category", "action_taken", "failure_detail", "failure_description",
             "failure_system", "failure_system_category", "failure_comments", "failure_type_category",
             "cause_comments", "failure_type"]
    f[fcols].to_parquet(out_dir / "production_failures.parquet", index=False)
    print(f"[demo] {n_wells} wells, {len(d):,} well-days, {len(j):,} jobs, {len(f):,} failures -> {out_dir}")
    return out_dir
