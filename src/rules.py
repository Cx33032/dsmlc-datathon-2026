"""Decision rule: what to do at the pull on a rod/pump outage. One function, used by the queue and
the Well Card, unit-tested in tests/test_rules.py.

  1. >=3 rod repairs in the last 365 d and no new string in that window -> full new string at the next pull
     (Idea 1: Cox HR 0.49 for the next rod repair; break-even ~1 failure/yr)
  2. >=2 located breaks and ALL of them within a <=150 m band -> section replacement may suffice;
     add guides/centralisers over that band (Idea 5: same-well breaks repeat within 50 m at 2.9x chance)
  3. corrosion evidence (coded Corrosion, or crew text mentions pitting/corrosion, on any rod failure)
     -> batch inhibitor program + corrosion-resistant rod grade
  4. every line states the evidence count it rests on; too little evidence -> "insufficient data"
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

CHRONIC_REPAIRS = 3
BAND_MAX_M = 150.0
MIN_BREAKS_FOR_BAND = 2


@dataclass
class Evidence:
    repairs_365: int = 0                 # rod repair events in the 365 d before `asof`
    new_string_365: bool = False         # a new rod string was run in that window
    break_depths: list = field(default_factory=list)   # located break depths (m), any time before asof
    rod_failures_logged: int = 0         # rod failures in the failure log before asof
    coded_corrosion: int = 0             # of those, coded cause = Corrosion
    text_corrosion: int = 0              # of those, crew text mentions pitting / corrosion


@dataclass
class Action:
    kind: str          # "string" | "section" | "corrosion"
    status: str        # "recommend" | "not indicated" | "insufficient data"
    text: str
    evidence: str
    short: str = ""    # wording for the queue's one-line headline


def recommend(ev: Evidence) -> list[Action]:
    out: list[Action] = []
    # 1 -- full string
    if ev.new_string_365:
        out.append(Action("string", "not indicated", "New string already run in the last 365 days - repair and monitor.",
                          f"{ev.repairs_365} rod repairs in 365 d; new string in window"))
    elif ev.repairs_365 >= CHRONIC_REPAIRS:
        out.append(Action("string", "recommend", "Run a full new rod string at this pull.",
                          f"{ev.repairs_365} rod repairs in 365 d (threshold {CHRONIC_REPAIRS}), no new string",
                          "full new rod string"))
    else:
        out.append(Action("string", "not indicated", "Repair; the well is below the chronic threshold.",
                          f"{ev.repairs_365} rod repairs in 365 d (threshold {CHRONIC_REPAIRS})"))
    # 2 -- section / band
    d = sorted(float(x) for x in ev.break_depths if pd.notna(x))
    if len(d) < MIN_BREAKS_FOR_BAND:
        out.append(Action("section", "insufficient data", "Break depth: insufficient data for a section decision.",
                          f"{len(d)} located break(s); need {MIN_BREAKS_FOR_BAND}"))
    else:
        lo, hi = d[0], d[-1]
        if hi - lo <= BAND_MAX_M:
            out.append(Action("section", "recommend",
                              f"Section replacement may suffice; add guides/centralisers at {lo:.0f}-{hi:.0f} m.",
                              f"{len(d)} located breaks within a {hi - lo:.0f} m band",
                              f"section replacement + guides/centralisers at {lo:.0f}-{hi:.0f} m"))
        else:
            out.append(Action("section", "not indicated",
                              f"Breaks spread along the string ({lo:.0f}-{hi:.0f} m): no single section to target.",
                              f"{len(d)} located breaks over {hi - lo:.0f} m (> {BAND_MAX_M:.0f} m)"))
    # 3 -- corrosion
    if ev.rod_failures_logged == 0:
        out.append(Action("corrosion", "insufficient data", "Corrosion: insufficient data (no rod failures logged).",
                          "0 rod failures in the failure log"))
    elif ev.coded_corrosion > 0 or ev.text_corrosion > 0:
        out.append(Action("corrosion", "recommend",
                          "Add a batch inhibitor program and a corrosion-resistant rod grade.",
                          f"{ev.coded_corrosion} coded Corrosion, {ev.text_corrosion} with pitting/corrosion in crew text, "
                          f"of {ev.rod_failures_logged} rod failures",
                          "batch inhibitor + corrosion-resistant grade"))
    else:
        out.append(Action("corrosion", "not indicated", "No corrosion evidence.",
                          f"0 of {ev.rod_failures_logged} rod failures coded or described as corrosion"))
    return out


def headline(actions: list[Action]) -> str:
    """One line for the queue's reason card: 'Recommended at this pull: ...'."""
    rec = [a.short for a in actions if a.status == "recommend"]
    return ("Recommended at this pull: " + "; ".join(rec) + ".") if rec else "No change to the standard repair indicated."


def evidence_for(uwi: str, asof: pd.Timestamp, rod_events: pd.DataFrame, breaks: pd.DataFrame) -> Evidence:
    """Build Evidence for one well using only records strictly before `asof` (no look-ahead).
    rod_events: Idea 1 rod_events (uwi, s, is_replace); breaks: Idea 5 located_breaks (uwi, fd, depth_m,
    cause, kw_pitting, kw_corrosion)."""
    asof = pd.Timestamp(asof)
    e = rod_events[(rod_events["uwi"] == uwi) & (rod_events["s"] < asof)]
    win = e[e["s"] >= asof - pd.Timedelta(days=365)]  # same 365-day window as Idea 1
    b = breaks[(breaks["uwi"] == uwi) & (breaks["fd"] < asof)]
    text = (b["kw_pitting"].astype(bool) | b["kw_corrosion"].astype(bool)) if len(b) else pd.Series(dtype=bool)
    return Evidence(repairs_365=int((win["is_replace"] == 0).sum()), new_string_365=bool((win["is_replace"] == 1).any()),
                    break_depths=b["depth_m"].dropna().tolist(), rod_failures_logged=int(len(b)),
                    coded_corrosion=int((b["cause"] == "Corrosion").sum()), text_corrosion=int(text.sum()))
