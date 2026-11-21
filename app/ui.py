"""Shared helpers for every page: data mode (private vs synthetic demo), the one central oil price,
cached artifact loading and chart styling."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.config import DEFAULT_NETBACK_CAD_PER_BBL, M3_TO_BBL  # noqa: E402

PRIVATE_OUT = Path(os.environ.get("OUT_DIR", ROOT / "outputs"))
DEMO_OUT = ROOT / "outputs_demo"

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GRAY, MUTED, CRITICAL = "#a9a8a1", "#898781", "#d03b3b"
CAUSE_COLORS = {"Corrosion": CRITICAL, "Fatigue": BLUE, "Load / Excess Stress": ORANGE, "Erosion": YELLOW}


def private_available() -> bool:
    return (PRIVATE_OUT / "risk_scores.parquet").exists() and (PRIVATE_OUT / "ideas" / "1" / "economics.json").exists()


def sidebar():
    """Mode toggle + price slider. Call once per run from the entry script."""
    st.sidebar.title("Predict the Break, Protect the Barrel")
    st.sidebar.caption("One platform, three decisions: today, at the pull, between failures")
    has_private = private_available()
    if "demo" not in st.session_state:   # ?demo=1 / ?demo=0 in the URL picks the mode for a new session
        q = st.query_params.get("demo")
        st.session_state["demo"] = (q == "1" or not has_private) if q is not None else not has_private
    st.sidebar.toggle("Synthetic demo data", key="demo", disabled=not has_private,
                      help="Fake wells, outages, rod jobs and crew-style notes with the same schemas, so the app runs "
                           "from a clean clone. Private mode needs the competition data and `build_artifacts.py`.")
    if st.session_state["demo"] and not (DEMO_OUT / "build_info.json").exists():
        with st.spinner("First run: generating synthetic demo data and building artifacts (about 30 s)..."):
            import subprocess
            r = subprocess.run([sys.executable, str(ROOT / "build_artifacts.py"), "--demo"], cwd=ROOT,
                               capture_output=True, text=True)
        if r.returncode != 0:
            st.error("Demo build failed: " + r.stderr[-1500:])
            st.stop()
    if st.session_state["demo"]:
        st.sidebar.info("Synthetic data - numbers are illustrative, not Strathcona results.", icon=":material/science:")
    st.sidebar.slider("Oil price, field gate (C$/bbl)", 20.0, 120.0, DEFAULT_NETBACK_CAD_PER_BBL, 0.5, key="price_bbl",
                      help="Default = WCS Hardisty (WTI 83.45 - 26.20 USD) x 1.4325 USD/CAD, less a 15% field-gate "
                           "haircut (our assumption). Every $ figure in the app recomputes from this.")
    st.sidebar.caption(f"= C${price_m3():,.0f}/m³ · revenue, not margin")


def intro(question: str, steps: list[str], note: str | None = None):
    """Page header: the one question the page answers, then numbered how-to steps."""
    st.markdown(f"<div style='font-size:1.05rem;opacity:.85;margin:-6px 0 10px'>{question}</div>",
                unsafe_allow_html=True)
    cols = st.columns(len(steps))
    for i, (c, s) in enumerate(zip(cols, steps), start=1):
        c.markdown(f"<div style='display:flex;gap:10px;align-items:flex-start'>"
                   f"<div style='flex:none;width:24px;height:24px;border-radius:50%;background:{BLUE};color:white;"
                   f"font-weight:600;font-size:13px;display:flex;align-items:center;justify-content:center'>{i}</div>"
                   f"<div style='font-size:.92rem;line-height:1.35'>{s}</div></div>", unsafe_allow_html=True)
    if note:
        st.caption(note)
    st.write("")


def filters(label: str = "Filters"):
    """A bordered filter bar; use as `with ui.filters(): ...`."""
    box = st.container(border=True)
    box.markdown(f"<div style='font-size:.8rem;font-weight:600;letter-spacing:.06em;text-transform:uppercase;"
                 f"opacity:.7'>{label}</div>", unsafe_allow_html=True)
    return box


def explain(text: str):
    """A one-line 'how to read this chart' note under a chart."""
    st.caption(f":material/info: {text}")


def hbar(labels, values, colors=None, text=None, hover=None, title=None, xaxis=None, height=None, customdata=None):
    """Horizontal bar chart, largest at the top, one bar per row (the default replacement for a table)."""
    labels = list(labels)
    fig = go.Figure(go.Bar(y=labels, x=list(values), orientation="h", marker_color=colors or BLUE,
                           text=text, textposition="outside", cliponaxis=False, customdata=customdata,
                           hovertemplate=hover or "%{y}: %{x:,.1f}<extra></extra>"))
    fig.update_layout(title=title, xaxis_title=xaxis, bargap=0.25,
                      yaxis=dict(autorange="reversed", automargin=True))
    return style(fig, height or max(200, 26 * len(labels) + 60))


def is_demo() -> bool:
    return bool(st.session_state.get("demo", not private_available()))


def out_dir() -> Path:
    return DEMO_OUT if is_demo() else PRIVATE_OUT


def price_bbl() -> float:
    return float(st.session_state.get("price_bbl", DEFAULT_NETBACK_CAD_PER_BBL))


def price_m3() -> float:
    return price_bbl() * M3_TO_BBL


def stamp(d: Path) -> float:
    f = d / "build_info.json"
    return f.stat().st_mtime if f.exists() else 0.0


@st.cache_data(show_spinner=False)
def _read(path: str, stamp_: float, kind: str):
    p = Path(path)
    if not p.exists():
        return None
    if kind == "parquet":
        return pd.read_parquet(p)
    if kind == "csv":
        return pd.read_csv(p)
    return json.loads(p.read_text())


def art(rel: str):
    """Read an artifact (parquet/csv/json) from the active output dir; None if missing."""
    d = out_dir()
    kind = rel.rsplit(".", 1)[-1]
    kind = "json" if kind == "json" else ("csv" if kind == "csv" else "parquet")
    return _read(str(d / rel), stamp(d), kind)


def require(*rels: str) -> bool:
    missing = [r for r in rels if not (out_dir() / r).exists()]
    if missing:
        mode = "--demo" if is_demo() else "--data-dir <folder with the parquets>"
        st.warning(f"Artifacts missing in `{out_dir().name}/`: {', '.join(missing)}. "
                   f"Run `python build_artifacts.py {mode}`.")
        return False
    return True


def style(fig: go.Figure, h: int = 340) -> go.Figure:
    top = 36 if fig.layout.annotations else 8
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=top, b=8), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, xanchor="left", title=None,
                                  bgcolor="rgba(0,0,0,0)"),
                      font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif"))
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)", zeroline=False)
    return fig


def show(fig, **kw):
    title = fig.layout.title.text
    if title:
        st.markdown(f"**{title}**")
        fig.update_layout(title=None)
    return st.plotly_chart(fig, use_container_width=True, theme="streamlit", **kw)


def money(x: float) -> str:
    a = abs(x)
    s = f"${a / 1e6:,.2f}M" if a >= 1e6 else (f"${a / 1e3:,.0f}k" if a >= 1e4 else f"${a:,.0f}")
    return ("-" if x < 0 else "") + s


def cad(x: float) -> str:
    """Exact dollars for worked arithmetic (money() rounds to k / M)."""
    return ("-" if x < 0 else "") + f"C\\${abs(x):,.0f}"


def mmoney(x: float) -> str:
    """money() for markdown text, where a bare $ pair would render as LaTeX."""
    return money(x).replace("$", "\\$")


def failure_cost_md(econ: dict, pm3: float, lost_oil: bool = True) -> str:
    """Where 'cost of one more rod failure' comes from, with the current sidebar price."""
    lost = econ["lost_m3_per_repair_mean"]
    oil = lost * pm3 if lost_oil else 0.0
    total = econ["repair_job_cost"] + oil
    return (f"**Cost of one rod failure = repair job + oil lost while the well is down = {cad(total)}**\n"
            f"- **Repair job {cad(econ['repair_job_cost'])}**: the average cost of rod-repair jobs in the job records "
            "(jobs since 2023 with a cost above zero; older repair rows are often entered as \\$0).\n"
            f"- **Lost oil {cad(oil)}**: on average a rod repair costs **{lost:.1f} m³** of oil, the downhole downtime "
            "logged in the daily records from 7 days before the job until the day after it ends, "
            + (f"× **C\\${pm3:,.0f}/m³** (the oil price in the sidebar)." if lost_oil
               else "not counted under the current stress-test setting."))


def new_string_md(econ: dict, cost_mult: float = 1.0) -> str:
    """Where the extra cost of a new string and the hazard ratio come from."""
    inc = econ["inc_cost"] * cost_mult
    return (f"- **Extra cost of a new string {cad(inc)}**: an average new-string job costs "
            f"{cad(econ['replace_job_cost'])} vs {cad(econ['repair_job_cost'])} for a repair. The rig is on the well "
            "anyway at the next pull, so only the difference counts"
            + (" (doubled by the stress test)." if cost_mult != 1 else ".") + "\n"
            f"- **Hazard ratio {econ['hr_chronic']:.2f}** (95% CI {econ['hr_chronic_lo']:.2f}–{econ['hr_chronic_hi']:.2f}): "
            f"in the job history, wells that got a new string had their next rod repair at {econ['hr_chronic']:.2f}× the "
            "rate of wells that got an ordinary repair. That comes from a survival (Cox) model on wells with 2+ repairs "
            "in the prior year, adjusted for prior failures, pump speed, liquid rate and area. So a new string removes "
            f"about {1 - econ['hr_chronic']:.0%} of the repairs the well would otherwise have.")


def well_label(uwi: str) -> str:
    return uwi


def open_well(uwi: str):
    """Jump to the Well Card for `uwi` (used by the queue and the program list)."""
    st.session_state["well"] = uwi
    st.switch_page(PAGES["well"])


PAGES: dict = {}   # filled by app.py: key -> st.Page
