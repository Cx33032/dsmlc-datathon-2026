"""Replacement program: which chronic wells get a new rod string, and is it worth it?"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from src.economics import breakeven, fail_cost, sensitivity, well_net, worst_case_wells

st.title("Replacement program")
st.caption("Wells with ≥3 rod repairs in the last 365 days and no new string: replace the whole string at the next "
           "pull instead of patching it again.")
if not ui.require("ideas/1/chronic_wells.csv", "ideas/1/economics.json", "recommendations.parquet"):
    st.stop()
econ = ui.art("ideas/1/economics.json")
prog = ui.art("ideas/1/chronic_wells.csv").merge(
    ui.art("recommendations.parquet")[["uwi", "section_status", "section_text", "corrosion_status"]], on="uwi", how="left")
pm3 = ui.price_m3()

with st.container(border=True):
    s1, s2, s3, s4 = st.columns(4)
    hr_lab = s1.radio("Hazard ratio", ["central", "upper 95% CI"], horizontal=True,
                      help=f"Cox HR of the next rod repair after a new string vs a repair, chronic wells: "
                           f"{econ['hr_chronic']:.3f} ({econ['hr_chronic_lo']:.3f}–{econ['hr_chronic_hi']:.3f}).")
    mult = s2.radio("Incremental string cost", ["×1", "×2"], horizontal=True)
    horizon = s3.radio("Benefit horizon", ["2 yr", "1 yr"], horizontal=True)
    lost_on = s4.toggle("Count lost oil", value=True)
hr = econ["hr_chronic"] if hr_lab == "central" else econ["hr_chronic_hi"]
cm_ = 2.0 if mult == "×2" else 1.0
hz = 2.0 if horizon == "2 yr" else 1.0
avoided, net = well_net(prog["repairs_last365"], econ, pm3, hr=hr, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
prog = prog.assign(avoided=avoided, net=net)
be = breakeven(econ, pm3, hr=hr, cost_mult=cm_, horizon=hz, lost_oil=lost_on)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Program wells", len(prog), f"{int(prog['repairs_last365'].sum())} rod repairs last year", delta_arrow="off",
          delta_color="off")
m2.metric("Program net value", ui.money(prog["net"].sum()), f"over {hz:.0f} yr", delta_arrow="off", delta_color="off")
m3.metric("Break-even, failures/yr", f"{be:.2f}", help="A new string pays back on any well failing more often than this.")
m4.metric("Wells worth replacing", f"{int((prog['net'] > 0).sum())} of {len(prog)}")

left, right = st.columns([3, 2])
with left:
    lam = np.linspace(0.5, 12, 200)
    fig = go.Figure()
    for h_r, lab, dash in ((econ["hr_chronic"], f"central HR {econ['hr_chronic']:.2f}", None),
                           (econ["hr_chronic_hi"], f"pessimistic HR {econ['hr_chronic_hi']:.2f}", "dash")):
        _, n = well_net(lam, econ, pm3, hr=h_r, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
        fig.add_trace(go.Scatter(x=lam, y=n / 1e3, mode="lines", name=lab, line=dict(color=ui.BLUE, width=2, dash=dash),
                                 hovertemplate="%{x:.1f} failures/yr → %{y:,.0f}k<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=ui.MUTED, width=1))
    fig.add_vline(x=be, line=dict(color=ui.CRITICAL, width=1.5, dash="dot"),
                  annotation_text=f"break-even {be:.1f}/yr", annotation_position="top right")
    fig.update_layout(title=f"Net value of a new string vs the well's failure rate (k C$, {hz:.0f} yr)",
                      xaxis_title="rod repairs per year", yaxis_title="k C$")
    ui.show(ui.style(fig, 340))
with right:
    by = prog.groupby("top_cause", dropna=False).agg(wells=("uwi", "size"), net=("net", "sum")).reset_index()
    by["top_cause"] = by["top_cause"].fillna("not in failure log")
    by = by.sort_values("net")
    fig = go.Figure(go.Bar(y=by["top_cause"], x=by["net"] / 1e6, orientation="h", marker_color=ui.BLUE,
                           text=[f"{w} wells" for w in by["wells"]], textposition="auto",
                           hovertemplate="%{y}: %{x:.2f}M<extra></extra>"))
    fig.update_layout(title="Net value by most common failure cause (C$M)", xaxis_title="C$M")
    ui.show(ui.style(fig, 340))

st.subheader("Ranked chronic wells")
f1, f2 = st.columns(2)
areas = f1.multiselect("Area", sorted(prog["area"].dropna().unique()), placeholder="All areas")
causes = f2.multiselect("Most common cause", sorted(prog["top_cause"].dropna().unique()), placeholder="All causes")
v = prog.copy()
if areas:
    v = v[v["area"].isin(areas)]
if causes:
    v = v[v["top_cause"].isin(causes)]
v = v.sort_values("net", ascending=False)
table = v[["uwi", "area", "repairs_last365", "top_cause", "all_in_cost_last365_CAD", "avoided", "net",
           "section_status", "corrosion_status"]].rename(columns={
    "uwi": "Well", "area": "Area", "repairs_last365": "Rod repairs 365 d", "top_cause": "Top cause",
    "all_in_cost_last365_CAD": "All-in cost last yr", "avoided": "Failures avoided", "net": "Net value",
    "section_status": "Section band", "corrosion_status": "Corrosion remedy"})
sel = st.dataframe(table, hide_index=True, use_container_width=True, height=360, on_select="rerun",
                   selection_mode="single-row",
                   column_config={"All-in cost last yr": st.column_config.NumberColumn(format="$%.0f"),
                                  "Net value": st.column_config.NumberColumn(format="$%.0f"),
                                  "Failures avoided": st.column_config.NumberColumn(format="%.1f")})
if sel.selection.rows:
    u = table.iloc[sel.selection.rows[0]]["Well"]
    if st.button(f"Open the well card for {u}", icon=":material/arrow_forward:"):
        ui.open_well(u)
else:
    st.caption("Select a row to open its well card.")

st.subheader("Does it survive pessimism?")
sens = sensitivity(prog["repairs_last365"], econ, pm3)
st.dataframe(sens.rename(columns={"breakeven_failures_per_yr": "break-even /yr", "program_net_CAD": "program net",
                                  "failure_cost_CAD": "cost per failure", "incremental_cost_CAD": "incremental cost"}),
             hide_index=True, use_container_width=True,
             column_config={"program net": st.column_config.NumberColumn(format="$%.0f"),
                            "cost per failure": st.column_config.NumberColumn(format="$%.0f"),
                            "incremental cost": st.column_config.NumberColumn(format="$%.0f"),
                            "HR": st.column_config.NumberColumn(format="%.3f"),
                            "break-even /yr": st.column_config.NumberColumn(format="%.2f")})
worst = worst_case_wells(prog, econ, pm3)
st.markdown(f"**Start with the worst {len(worst)}.** Stacking every pessimistic case at once (HR at the upper CI, "
            f"job cost only, string cost ×2, 1-year horizon), {len(worst)} wells still pay back. They are the "
            f"no-regret first wave.")
st.dataframe(worst[["uwi", "area", "repairs_last365", "top_cause", "worst_case_net"]].rename(columns={
    "uwi": "Well", "area": "Area", "repairs_last365": "Rod repairs 365 d", "top_cause": "Top cause",
    "worst_case_net": "Net, worst case"}), hide_index=True, use_container_width=True,
    column_config={"Net, worst case": st.column_config.NumberColumn(format="$%.0f")})
st.caption(f"Unit economics from Idea 1: repair job C${econ['repair_job_cost']:,.0f} (cost > 0, 2023+), "
           f"{econ['lost_m3_per_repair_mean']:.2f} m³ lost oil per repair, incremental string cost "
           f"C${econ['inc_cost']:,.0f}. Lost oil valued at the sidebar price (C${pm3:,.0f}/m³).")
