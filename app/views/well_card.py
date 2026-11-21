"""Well Card: what to do at the pull on this well, and the evidence behind it."""
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import ui
from src.economics import fail_cost, well_net
from src.rules import evidence_for, recommend

st.title("Well card")
if not ui.require("ideas/1/rod_events.parquet", "ideas/5/located_breaks.csv", "ideas/1/economics.json",
                  "recommendations.parquet"):
    st.stop()

rod = ui.art("ideas/1/rod_events.parquet").assign(s=lambda d: pd.to_datetime(d["s"]))
br = ui.art("ideas/5/located_breaks.csv").assign(fd=lambda d: pd.to_datetime(d["fd"]))
econ = ui.art("ideas/1/economics.json")
prog = ui.art("ideas/1/chronic_wells.csv")
recs = ui.art("recommendations.parquet")

# well picker: program wells first (worst first), then every other well with rod history
order = list(prog.sort_values("net_value_2y_CAD", ascending=False)["uwi"]) if prog is not None else []
order += sorted(set(recs["uwi"]) - set(order))
qp = st.query_params.get("uwi")
want = st.session_state.pop("well", None) or qp
idx = order.index(want) if want in order else 0
prog_set = set(prog["uwi"]) if prog is not None else set()
uwi = st.selectbox("Well", order, index=idx,
                   format_func=lambda u: f"{u}  ·  chronic program" if u in prog_set else u)
st.query_params["uwi"] = uwi

asof = pd.Timestamp(econ["asof"]) + pd.Timedelta(days=1)
ev = evidence_for(uwi, asof, rod, br)
acts = recommend(ev)
w_rod = rod[rod["uwi"] == uwi].sort_values("s")
w_br = br[br["uwi"] == uwi].sort_values("fd")
area = (w_br["area"].dropna().iloc[0] if w_br["area"].notna().any() else
        (prog.set_index("uwi").loc[uwi, "area"] if uwi in prog_set else ""))

# ---------------------------------------------------------------- recommendation
st.subheader("Recommended at the next pull")
st.caption(f"As of {econ['asof']} · {area} · decision rule in `src/rules.py` (same rule the queue uses)")
icon = {"recommend": ":material/check_circle:", "not indicated": ":material/remove:",
        "insufficient data": ":material/help:"}
cols = st.columns(3)
for c, a in zip(cols, acts):
    with c.container(border=True):
        label = {"string": "Rod string", "section": "Where on the string", "corrosion": "Corrosion remedy"}[a.kind]
        st.markdown(f"**{label}**")
        (st.success if a.status == "recommend" else st.info if a.status == "not indicated" else st.warning)(
            a.text, icon=icon[a.status])
        st.caption(f"Evidence: {a.evidence}")

# ---------------------------------------------------------------- economics
st.subheader("Replacement economics for this well")
pm3 = ui.price_m3()
lam = ev.repairs_365
avoided, net = well_net(lam, econ, pm3)
_, net_hi = well_net(lam, econ, pm3, hr=econ["hr_chronic_hi"])
e1, e2, e3, e4 = st.columns(4)
e1.metric("λ: rod repairs, last 365 d", lam)
e2.metric(f"Failures avoided over {econ['horizon_yr']:.0f} yr", f"{avoided:.1f}",
          help=f"λ × (1 − HR {econ['hr_chronic']:.3f}) × {econ['horizon_yr']:.0f} yr")
e3.metric("Net value of a new string", ui.money(net), f"{ui.money(net_hi)} at HR upper CI", delta_arrow="off",
          delta_color="off")
e4.metric("All-in cost per rod failure", ui.money(fail_cost(econ, pm3)),
          f"job {ui.money(econ['repair_job_cost'])} + lost oil", delta_arrow="off", delta_color="off")

# ---------------------------------------------------------------- timeline + break strip
left, right = st.columns([3, 2])
with left:
    fig = go.Figure()
    rep = w_rod[w_rod["is_replace"] == 0]
    new = w_rod[w_rod["is_replace"] == 1]
    fig.add_trace(go.Scatter(x=rep["s"], y=["Rod jobs"] * len(rep), mode="markers", name="repair",
                             marker=dict(symbol="circle", size=10, color=ui.ORANGE,
                                         line=dict(color="white", width=1.5)),
                             hovertemplate="%{x|%d %b %Y}: rod repair<extra></extra>"))
    fig.add_trace(go.Scatter(x=new["s"], y=["Rod jobs"] * len(new), mode="markers", name="new string",
                             marker=dict(symbol="diamond", size=14, color=ui.AQUA, line=dict(color="white", width=1.5)),
                             hovertemplate="%{x|%d %b %Y}: new rod string<extra></extra>"))
    for cause, g in w_br.groupby(w_br["cause"].fillna("Unknown")):
        fig.add_trace(go.Scatter(x=g["fd"], y=["Failures (coded cause)"] * len(g), mode="markers", name=cause,
                                 marker=dict(size=10, color=ui.CAUSE_COLORS.get(cause, ui.GRAY),
                                             line=dict(color="white", width=1.5)),
                                 hovertemplate="%{x|%d %b %Y}: " + cause + "<extra></extra>"))
    fig.update_layout(title="Rod jobs and logged rod failures", yaxis=dict(categoryorder="array",
                      categoryarray=["Failures (coded cause)", "Rod jobs"]))
    ui.show(ui.style(fig, 260))
with right:
    loc = w_br[w_br["depth_m"].notna()]
    fig = go.Figure()
    if len(loc) >= 2 and loc["depth_m"].max() - loc["depth_m"].min() <= 150:
        fig.add_vrect(x0=loc["depth_m"].min(), x1=loc["depth_m"].max(), fillcolor=ui.AQUA, opacity=0.15, line_width=0)
    for cause, g in loc.groupby(loc["cause"].fillna("Unknown")):
        fig.add_trace(go.Scatter(x=g["depth_m"], y=g["fd"], mode="markers", name=cause,
                                 marker=dict(size=11, color=ui.CAUSE_COLORS.get(cause, ui.GRAY),
                                             line=dict(color="white", width=1.5)),
                                 hovertemplate="%{x:.0f} m · %{y|%b %Y}<extra>" + cause + "</extra>"))
    band = f"band {loc['depth_m'].max() - loc['depth_m'].min():.0f} m" if len(loc) >= 2 else "fewer than 2 located"
    fig.update_layout(title=f"Located break depths ({len(loc)} of {len(w_br)} rod failures; {band})",
                      xaxis=dict(title="depth along the string (m)", range=[0, max(1000, loc["depth_m"].max() + 50)
                                 if len(loc) else 1000]), yaxis_title=None)
    ui.show(ui.style(fig, 260))

# ---------------------------------------------------------------- crew notes
st.subheader("What the crews wrote")
notes = w_br[w_br["failure_comments"].notna()].copy()
if notes.empty:
    st.caption("No crew comments on this well's rod failures.")
else:
    kw = re.compile(r"pit|corro|rust|@|\bat\b|\d{2,4}\s*m\b|jt|joint|#", re.I)
    notes["score"] = notes["failure_comments"].str.contains(kw).astype(int) + notes["depth_m"].notna()
    top = notes.sort_values(["score", "fd"], ascending=False).head(3)
    if ui.is_demo():
        st.caption("Synthetic crew-style notes (demo mode).")
    else:
        st.caption("Verbatim from the failure log (private mode only; never sent to an external service).")
    for r in top.itertuples():
        st.markdown(f"> {r.failure_comments}  \n> — {r.fd:%d %b %Y}, coded *{r.cause}*"
                    + (f", located at {r.depth_m:.0f} m" if pd.notna(r.depth_m) else ""))

# ---------------------------------------------------------------- 90-day trend
wd_all = ui.art("well_daily.parquet")
wd = wd_all[wd_all["uwi"].astype(str) == uwi].sort_values("production_date") if wd_all is not None else pd.DataFrame()
if len(wd):
    wd = wd[wd["production_date"] > wd["production_date"].max() - pd.Timedelta(days=90)]
    shock = ui.art("ideas/whiplash/well_shock.parquet")
    verdict = ui.art("ideas/whiplash/verdict.json") or {}
    rows = 4 if (shock is not None and verdict.get("keep")) else 3
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("Oil (m³/d)", "Pump RPM", "Rod torque (ft-lb)", "Shock index")[:rows])
    fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["oil_produced_m3"], mode="lines", name="oil",
                             line=dict(color=ui.BLUE, width=2)), 1, 1)
    fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["pcp_pump_rpm"], mode="lines", name="rpm",
                             line=dict(color=ui.ORANGE, width=2)), 2, 1)
    fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["pcp_pump_rod_torque_ftlb"], mode="lines", name="torque",
                             line=dict(color=ui.AQUA, width=2)), 3, 1)
    if rows == 4:
        s = shock[(shock["uwi"] == uwi) & (shock["production_date"] >= wd["production_date"].min())]
        fig.add_trace(go.Scatter(x=s["production_date"], y=s["shock_index"], mode="lines", name="shock",
                                 line=dict(color=ui.YELLOW, width=2)), 4, 1)
    fig.update_layout(showlegend=False, title="Last 90 days")
    ui.show(ui.style(fig, 120 * rows + 60))
    st.caption("Flat stretches in RPM and torque are carried-forward manual readings, not steady operation.")
