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
    st.plotly_chart(fig, use_container_width=True, theme="streamlit", **kw)


def money(x: float) -> str:
    a = abs(x)
    s = f"${a / 1e6:,.2f}M" if a >= 1e6 else (f"${a / 1e3:,.0f}k" if a >= 1e4 else f"${a:,.0f}")
    return ("-" if x < 0 else "") + s


def well_label(uwi: str) -> str:
    return uwi


def open_well(uwi: str):
    """Jump to the Well Card for `uwi` (used by the queue and the program list)."""
    st.session_state["well"] = uwi
    st.switch_page(PAGES["well"])


PAGES: dict = {}   # filled by app.py: key -> st.Page
