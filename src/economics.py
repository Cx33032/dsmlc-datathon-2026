"""Replace-vs-repair economics (Idea 1), recomputed from the central price.

econ = Idea 1's economics.json: repair_job_cost, lost_m3_per_repair_mean/median, inc_cost, hr_chronic(+_hi), horizon_yr
  all-in cost per rod failure = repair job cost + lost oil per repair x price
  avoided failures over H yr   = lambda x (1 - HR) x H          (lambda = rod repairs in the last 365 d)
  net value of a new string    = avoided x all-in failure cost - incremental replacement cost
  break-even lambda            = incremental cost / ((1 - HR) x H x all-in failure cost)
"""
from __future__ import annotations

import pandas as pd


def fail_cost(econ: dict, price_m3: float, lost_oil: bool = True, lost_stat: str = "mean") -> float:
    lost = econ["lost_m3_per_repair_mean"] if lost_stat == "mean" else econ["lost_m3_per_repair_median"]
    return econ["repair_job_cost"] + (lost * price_m3 if lost_oil else 0.0)


def well_net(lam, econ: dict, price_m3: float, hr: float | None = None, cost_mult: float = 1.0,
             horizon: float | None = None, lost_oil: bool = True):
    hr = econ["hr_chronic"] if hr is None else hr
    h = econ["horizon_yr"] if horizon is None else horizon
    avoided = lam * (1 - hr) * h
    return avoided, avoided * fail_cost(econ, price_m3, lost_oil) - econ["inc_cost"] * cost_mult


def breakeven(econ: dict, price_m3: float, hr: float | None = None, cost_mult: float = 1.0,
              horizon: float | None = None, lost_oil: bool = True) -> float:
    hr = econ["hr_chronic"] if hr is None else hr
    h = econ["horizon_yr"] if horizon is None else horizon
    return econ["inc_cost"] * cost_mult / ((1 - hr) * h * fail_cost(econ, price_m3, lost_oil))


def sensitivity(lam: pd.Series, econ: dict, price_m3: float) -> pd.DataFrame:
    """Idea 1's sensitivity table, recomputed at the given price."""
    hr, hi = econ["hr_chronic"], econ["hr_chronic_hi"]
    base = fail_cost(econ, price_m3)
    rows = [("central", hr, base, 1, None), ("HR at upper 95% CI", hi, base, 1, None),
            ("lost oil = median per event", hr, fail_cost(econ, price_m3, lost_stat="median"), 1, None),
            ("lost oil ignored (job cost only)", hr, fail_cost(econ, price_m3, lost_oil=False), 1, None),
            ("oil price -30%", hr, fail_cost(econ, price_m3 * 0.7), 1, None),
            ("incremental replace cost x2", hr, base, 2, None),
            ("1-year horizon", hr, base, 1, 1.0),
            ("worst combo: HR upper CI, job cost only, cost x2, 1 yr", hi, fail_cost(econ, price_m3, lost_oil=False), 2, 1.0)]
    out = []
    for name, h_r, fc, mult, hz in rows:
        hz = econ["horizon_yr"] if hz is None else hz
        net = lam * (1 - h_r) * hz * fc - econ["inc_cost"] * mult
        out.append({"scenario": name, "HR": h_r, "failure_cost_CAD": fc, "incremental_cost_CAD": econ["inc_cost"] * mult,
                    "horizon_yr": hz, "breakeven_failures_per_yr": econ["inc_cost"] * mult / ((1 - h_r) * hz * fc),
                    "program_net_CAD": float(net.sum()), "wells_positive": int((net > 0).sum())})
    return pd.DataFrame(out)


def worst_case_wells(prog: pd.DataFrame, econ: dict, price_m3: float) -> pd.DataFrame:
    """Wells still worth a new string when every pessimistic case is stacked."""
    _, net = well_net(prog["repairs_last365"], econ, price_m3, hr=econ["hr_chronic_hi"], cost_mult=2,
                      horizon=1.0, lost_oil=False)
    return prog.assign(worst_case_net=net)[net > 0].sort_values("worst_case_net", ascending=False)
