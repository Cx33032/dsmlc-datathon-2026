"""Shared helpers for every page: design tokens and page CSS, the page header, data mode (private vs
synthetic demo), the one central oil price, cached artifact loading and chart styling.

All colours, text styles and chart styling live here. Pages import them; no page defines its own."""
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

# ---------------------------------------------------------------- design tokens
# Chart colours. Each has one meaning in every chart of the app:
#   BLUE      the item to act on, or this app's method
#   GRAY      everything else, or the simple baseline
#   CRITICAL  loss, alarm, or a negative value
#   ORANGE, AQUA, YELLOW   further categories (causes, series), always explained by a legend
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GRAY, MUTED, CRITICAL = "#a9a8a1", "#898781", "#d03b3b"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
CAUSE_COLORS = {"Corrosion": CRITICAL, "Fatigue": BLUE, "Load / Excess Stress": ORANGE, "Erosion": YELLOW}
COLOR_RULE = "Red = loss, alarm or a negative value. Other colours are explained in each chart's legend or note."

FONT = "system-ui, -apple-system, Segoe UI, sans-serif"
GRID, AXIS = "rgba(137,135,129,0.25)", "#c3c2b7"
# Secondary text is the theme's own text colour at 80% opacity: 6.3:1 on white, 13:1 on the dark theme (WCAG AA).
# Chart text uses the theme text colour too, so it passes in light and dark mode without knowing the mode.
CSS = f"""<style>
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] *, .cn-label {{ color: inherit !important; opacity: .8; }}
[data-testid="stSidebarNav"] [data-testid="stIconMaterial"] {{ color: inherit; }}
[data-testid="stCaptionContainer"] * {{ opacity: 1; }}
[data-testid="stPlotlyChart"] {{ color: inherit; }}
[data-testid="stPlotlyChart"] :is(.cartesianlayer, .legend, .infolayer, .annotation, .barlayer, .scatterlayer) text
  {{ fill: currentColor !important; }}
/* section headings are h2 (page title is h1); keep them at the section size */
[data-testid="stMain"] h2 {{ font-size: 1.75rem; }}
.cn-summary {{ font-size: 1.15rem; line-height: 1.55; margin: -0.5rem 0 0.25rem; max-width: 62rem; }}
.cn-summary b {{ font-weight: 650; }}
[data-testid="stPopover"] button[kind="tertiary"], [data-testid="stPopover"] [data-testid="stPopoverButton"] {{ font-size: .85rem; opacity: .85; }}
.cn-label {{ font-size: .8rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }}
</style>"""


# ---------------------------------------------------------------- glossary
# Each definition is taken from docs/Dataset_Handbook.md, docs/ideas/*/idea.md or the app's own methods.
TERMS = {
    "UWI": "Unique Well Identifier, the Canadian standard well label. It is built from the well's legal land location.",
    "m³": f"Cubic metres of oil. 1 m³ = {M3_TO_BBL:.2f} barrels (bbl).",
    "bbl": f"Barrels of oil. {M3_TO_BBL:.2f} bbl = 1 m³.",
    "C$": "Canadian dollars. Every C$ figure uses the oil price in the sidebar.",
    "Facility": "The battery or plant that a well's production flows to and is measured at.",
    "Outage": "A period when a well is down (not running), with a coded reason.",
    "Oil at risk": "Expected extra hours down over the next 3 days × the well's healthy oil rate. The expected hours come from "
                   "past outages with the same reason and the same hours down on day 1.",
    "Chronic rod well": "A well with 3 or more rod repairs in the past 365 days and no new rod string.",
    "Rod string": "The steel rods that connect the surface drive head to the downhole pump. Rods fail more often than "
                  "anything else.",
    "Pull": "A rod truck job that pulls the rods and pump out of the well to repair or replace them.",
    "Section": "Replace only one section of the string. The app suggests this when all located breaks sit within 150 m.",
    "Corrosion remedy": "Add a batch inhibitor program and a corrosion-resistant rod grade.",
    "HR": "Hazard ratio: the rate of the next rod repair after a new string, divided by the rate after a repair. Below 1 "
          "means fewer repairs. 0.49 means about half the rate.",
    "CI": "Confidence interval. A 95% CI is the range the true value is likely to fall in, given the data.",
    "Net value": "Repair jobs and lost oil avoided by a new string, minus the extra cost of a new string over a repair.",
    "Pays back above": "A new string pays for itself on any well that fails more often than this many times a year.",
    "Laggard": "A well that stays down long after most wells at its facility are back on production.",
    "Replay": "The queue re-run on every day of 2026, using only what was known at the end of each day.",
    "Exposure": "Extra hours down over the next 3 days × the well's healthy oil rate.",
    "Recorded loss": "The operator's own lost-oil field in the production data.",
    "Cox model": "A survival model that compares repair rates after a new string and after a repair, adjusted for prior "
                 "failures, RPM, liquid rate, area and year.",
    "RPM": "Pump speed in revolutions per minute. Faster moves more fluid but causes more wear.",
    "Rod torque": "The twisting load on the rods. Rising torque can point to a pump or rod problem.",
    "Pump efficiency": "Fluid the pump actually moved compared with its rated volume. A drop often means wear.",
    "Watchlist": "The running wells with the highest model chance of a failure outage in the next 14 days.",
    "Avoidable loss": "Lost oil from all downtime except uneconomic long-term shut-ins, which are a business decision.",
}


def sidebar():
    """CSS, mode toggle and price slider. Call once per run from the entry script."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.sidebar.markdown("<div class='cn-label'>Settings for every page</div>", unsafe_allow_html=True)
    has_private = private_available()
    if "demo" not in st.session_state:   # ?demo=1 / ?demo=0 in the URL picks the mode for a new session
        q = st.query_params.get("demo")
        st.session_state["demo"] = (q == "1" or not has_private) if q is not None else not has_private
    st.sidebar.toggle("Use synthetic demo data", key="demo", disabled=not has_private,
                      help="Fake wells, outages, rod jobs and crew-style notes with the same columns, so the app runs "
                           "without the competition data. To use the real data, put the competition files in place "
                           "and run build_artifacts.py.")
    if st.session_state["demo"] and not (DEMO_OUT / "build_info.json").exists():
        with st.spinner("Building the synthetic demo data (about 30 seconds the first time)…"):
            import subprocess
            r = subprocess.run([sys.executable, str(ROOT / "build_artifacts.py"), "--demo"], cwd=ROOT,
                               capture_output=True, text=True)
        if r.returncode != 0:
            st.error("The demo data build failed. Run `python build_artifacts.py --demo` in a terminal to see why.\n\n"
                     + r.stderr[-1500:])
            st.stop()
    if st.session_state["demo"]:
        st.sidebar.info("Synthetic data. The numbers are examples, not Strathcona results.", icon=":material/science:")
    st.sidebar.slider("Oil price used for every C$ figure (C$ per bbl)", 20.0, 120.0, DEFAULT_NETBACK_CAD_PER_BBL, 0.5,
                      key="price_bbl",
                      help="Default: WCS Hardisty (WTI 83.45 - 26.20 USD) × 1.4325 USD/CAD, less a 15% field-gate "
                           "haircut (our assumption). Every C$ figure in the app changes with this price. Lost oil is valued as lost "
                           "revenue, before operating cost.")
    st.sidebar.caption(f"= C${price_m3():,.0f} per m³")


# ---------------------------------------------------------------- page layout
def header(title: str, how: list[str] | None = None, terms: list[str] | None = None, extra_terms: dict | None = None):
    """Page title (the question the page answers), then an empty slot for the one-sentence answer, then a closed
    'How to use this page' expander with the steps and the terms. Fill the slot with `summary(slot, ...)` once
    the data is ready."""
    st.title(title)
    slot = st.container()
    if how or terms or extra_terms:
        with st.expander("How to use this page, and what the terms mean", icon=":material/help:"):
            if how:
                st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(how, start=1)))
            defs = {k: TERMS[k] for k in (terms or [])} | (extra_terms or {})
            if defs:
                st.markdown("**Terms**\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in defs.items()))
            st.caption(COLOR_RULE)
    return slot


def summary(slot, text: str):
    """The one-sentence answer under the page title. `text` may hold <b> tags."""
    slot.markdown(f"<p class='cn-summary'>{text}</p>", unsafe_allow_html=True)


def filters(label: str = "Filters", reset_keys: list[str] | None = None):
    """A bordered filter bar with an optional 'Reset filters' button; use as `with ui.filters(...): ...`.
    Widgets inside must use the keys in `reset_keys` so the reset can clear them."""
    box = st.container(border=True)
    a, b = box.columns([4, 1], vertical_alignment="center")
    a.markdown(f"<div class='cn-label'>{label}</div>", unsafe_allow_html=True)
    if reset_keys:
        def _reset():
            for k in reset_keys:
                st.session_state.pop(k, None)
        b.button("Reset filters", key=f"reset_{label}", on_click=_reset, icon=":material/restart_alt:",
                 width="stretch", type="tertiary")
    return box


def empty(what: str, change: str):
    """Plain message for a selection with no rows: what is empty, and what to change."""
    st.info(f"{what} {change}", icon=":material/filter_alt_off:")


def explain(text: str, label: str = "How to read this"):
    """An explanation kept out of sight: a small closed info popover the user can open. Nothing shows by default."""
    import hashlib
    key = "exp_" + hashlib.md5((label + text).encode()).hexdigest()[:10]
    with st.popover(label, icon=":material/info:", type="tertiary", key=key):
        st.markdown(text)


def hbar(labels, values, colors=None, text=None, hover=None, title=None, xaxis=None, height=None, customdata=None):
    """Horizontal bar chart, largest at the top, one bar per row (the default replacement for a table)."""
    labels = list(labels)
    fig = go.Figure(go.Bar(y=labels, x=list(values), orientation="h", marker_color=colors or BLUE,
                           text=text, textposition="outside", cliponaxis=False, customdata=customdata,
                           hovertemplate=hover or "%{y}: %{x:,.1f}<extra></extra>"))
    fig.update_layout(title=title, xaxis_title=xaxis, bargap=0.25,
                      yaxis=dict(autorange="reversed", automargin=True))
    return style(fig, height or max(200, 26 * len(labels) + 60))


def style(fig: go.Figure, h: int = 340) -> go.Figure:
    """The one chart style: light grid, legend on top. Text colour comes from CSS (see CSS above)."""
    top = 36 if fig.layout.annotations else 8
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=top, b=8), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, xanchor="left", title=None,
                                  bgcolor="rgba(0,0,0,0)"),
                      font=dict(family=FONT))
    fig.update_xaxes(showgrid=False, linecolor=AXIS)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def show(fig, **kw):
    """Render the chart title as page text (it wraps on narrow screens instead of colliding with the legend),
    then the chart itself."""
    title = fig.layout.title.text
    if title:
        st.markdown(f"**{title}**")
        fig.update_layout(title=None)
    return st.plotly_chart(fig, width="stretch", theme="streamlit", **kw)


# ---------------------------------------------------------------- data
def private_available() -> bool:
    return (PRIVATE_OUT / "risk_scores.parquet").exists() and (PRIVATE_OUT / "ideas" / "1" / "economics.json").exists()


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
        mode_ = "--demo" if is_demo() else "--data-dir <folder with the parquets>"
        st.warning(f"This page has no data yet. Files missing in `{out_dir().name}/`: {', '.join(missing)}. "
                   f"To build them, run `python build_artifacts.py {mode_}`.")
        return False
    return True


def money(x: float) -> str:
    a = abs(x)
    s = f"C${a / 1e6:,.2f}M" if a >= 1e6 else (f"C${a / 1e3:,.0f}k" if a >= 1e4 else f"C${a:,.0f}")
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
