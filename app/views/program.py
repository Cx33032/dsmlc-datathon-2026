"""Replacement program: which chronic wells get a new rod string, and is it worth it?"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui
from src.economics import breakeven, fail_cost, sensitivity, well_net, worst_case_wells

st.title("Replacement program")
ui.intro("Which wells should get a whole new rod string at their next failure instead of another repair, and is it "
         "worth the money?",
         ["Use the <b>filters</b> to look at one area, one failure cause, or only the worst wells.",
          "Open <b>Stress-test</b> and push the assumptions to their pessimistic end; watch whether the value stays "
          "positive.",
          "<b>Click a bar</b> in the ranked chart to open that well's card."])
if not ui.require("ideas/1/chronic_wells.csv", "ideas/1/economics.json", "recommendations.parquet"):
    st.stop()
econ = ui.art("ideas/1/economics.json")
prog_all = ui.art("ideas/1/chronic_wells.csv").merge(
    ui.art("recommendations.parquet")[["uwi", "section_status", "corrosion_status"]], on="uwi", how="left")
prog_all["top_cause"] = prog_all["top_cause"].fillna("not in failure log")
pm3 = ui.price_m3()

with ui.filters():
    c1, c2, c3, c4 = st.columns([1.2, 1.3, 1, 1.4])
    areas = c1.multiselect("Area", sorted(prog_all["area"].dropna().unique()), placeholder="All areas")
    causes = c2.multiselect("Most common failure cause", sorted(prog_all["top_cause"].unique()), placeholder="All causes")
    min_rep = c3.slider("Min. repairs last year", 3, int(prog_all["repairs_last365"].max()), 3)
    extra = c4.multiselect("Also recommended", ["Section band", "Corrosion remedy"], placeholder="Anything")
prog = prog_all[prog_all["repairs_last365"] >= min_rep]
if areas:
    prog = prog[prog["area"].isin(areas)]
if causes:
    prog = prog[prog["top_cause"].isin(causes)]
if "Section band" in extra:
    prog = prog[prog["section_status"] == "recommend"]
if "Corrosion remedy" in extra:
    prog = prog[prog["corrosion_status"] == "recommend"]
if prog.empty:
    st.info("No wells match these filters.")
    st.stop()

with st.expander("Stress-test the assumptions", icon=":material/tune:"):
    s1, s2, s3, s4 = st.columns(4)
    hr_lab = s1.radio("Effect of a new string", ["central", "weakest (upper 95% CI)"],
                      help=f"Hazard ratio of the next rod repair after a new string vs a repair: {econ['hr_chronic']:.2f} "
                           f"(95% CI {econ['hr_chronic_lo']:.2f}–{econ['hr_chronic_hi']:.2f}). Lower = bigger effect.")
    mult = s2.radio("Cost of a new string", ["as recorded", "double"])
    horizon = s3.radio("Years of benefit counted", ["2 years", "1 year"])
    lost_on = s4.toggle("Count lost oil", value=True, help="Off = count only the repair job cost.")
    st.caption("The oil price is in the sidebar. All numbers on this page update as you change these.")
hr = econ["hr_chronic"] if hr_lab == "central" else econ["hr_chronic_hi"]
cm_ = 2.0 if mult == "double" else 1.0
hz = 2.0 if horizon == "2 years" else 1.0
avoided, net = well_net(prog["repairs_last365"], econ, pm3, hr=hr, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
prog = prog.assign(avoided=avoided, net=net).sort_values("net", ascending=False)
be = breakeven(econ, pm3, hr=hr, cost_mult=cm_, horizon=hz, lost_oil=lost_on)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Wells", len(prog), f"{int(prog['repairs_last365'].sum())} rod repairs last year", delta_arrow="off",
          delta_color="off")
m2.metric(f"Net value over {hz:.0f} yr", ui.money(prog["net"].sum()),
          help="Money saved on repairs and lost oil, minus the extra cost of the new strings. Worked out below.")
m3.metric("Pays back above (failures/yr)", f"{be:.1f}", help="A new string pays for itself on any well failing more often "
                                                           "than this.")
m4.metric("Wells worth replacing", f"{int((prog['net'] > 0).sum())} of {len(prog)}")

# ---------------------------------------------------------------- what "net value" means
fc = fail_cost(econ, pm3, lost_on)
gross = float(prog["avoided"].sum() * fc)
capex = float(econ["inc_cost"] * cm_ * len(prog))
with st.expander(f"What 'net value over {hz:.0f} yr' means", icon=":material/calculate:", expanded=True):
    a, b = st.columns([3, 2])
    with a:
        st.markdown(f"**For each well: net value = repairs a new string avoids over {hz:.0f} yr × cost of one failure − "
                    "extra cost of a new string.** The headline adds that up over the wells shown.")
        st.markdown(f"- **Repairs avoided** = the well's repairs last year × (1 − {hr:.3f}) × {hz:.0f} yr. Over these "
                    f"{len(prog)} wells: {int(prog['repairs_last365'].sum())} repairs a year → "
                    f"**{prog['avoided'].sum():,.0f} repairs avoided**.\n"
                    f"- × **{ui.cad(fc)}** per failure = **{ui.cad(gross)}** of repairs and lost oil that never happen.\n"
                    f"- − **{ui.cad(econ['inc_cost'] * cm_)}** extra per new string × {len(prog)} wells = "
                    f"**{ui.cad(capex)}**.\n"
                    f"- = **{ui.cad(gross - capex)}** net value over {hz:.0f} yr.")
        st.markdown(ui.failure_cost_md(econ, pm3, lost_on))
        st.markdown(ui.new_string_md(econ, cm_))
        st.caption("'Net' = money saved minus money spent, not discounted. The stress-test settings above change every "
                   "number here.")
    with b:
        fig = go.Figure(go.Waterfall(
            x=["Failures avoided", "Extra cost of new strings", "Net value"], measure=["relative", "relative", "total"],
            y=[gross / 1e6, -capex / 1e6, 0], text=[ui.money(gross), "-" + ui.money(capex), ui.money(gross - capex)],
            textposition="outside", cliponaxis=False, connector=dict(line=dict(color=ui.GRAY, width=1)),
            increasing=dict(marker=dict(color=ui.AQUA)), decreasing=dict(marker=dict(color=ui.CRITICAL)),
            totals=dict(marker=dict(color=ui.BLUE)), hovertemplate="%{x}: %{y:.2f}M<extra></extra>"))
        fig.update_layout(title=f"From savings to net value ({hz:.0f} yr, C$M)", yaxis_title="C$M", showlegend=False)
        fig.update_yaxes(range=[min(0, (gross - capex) / 1e6 * 1.2), gross / 1e6 * 1.2])
        ui.show(ui.style(fig, 320))

# ---------------------------------------------------------------- ranked wells (replaces the table)
st.subheader("Which wells first")
n = st.slider("Show the top", 5, max(5, min(60, len(prog))), min(20, len(prog)), key="prog_n")
g = prog.head(n)
colors = [ui.BLUE if v > 0 else ui.CRITICAL for v in g["net"]]
tags = [" · ".join(x for x in (f"{r} repairs", "section" if s == "recommend" else "", "corrosion" if c == "recommend" else "") if x)
        for r, s, c in zip(g["repairs_last365"], g["section_status"], g["corrosion_status"])]
fig = ui.hbar([f"{u} · {a}" for u, a in zip(g["uwi"], g["area"])], g["net"] / 1e3, colors=colors,
              text=[f"{ui.money(v)} · {t}" for v, t in zip(g["net"], tags)], xaxis="net value of a new string (k C$)",
              hover="%{y}<br>%{x:,.0f}k C$<extra></extra>", title="Net value of a new string, best first (click a bar)")
fig.update_xaxes(range=[min(0, g["net"].min() / 1e3 * 1.2), g["net"].max() / 1e3 * 1.55])
ev = ui.show(fig, on_select="rerun", selection_mode="points", key="prog_rank")
ui.explain("'section' = breaks cluster in one band, so a section and guides may be enough; 'corrosion' = add an "
           "inhibitor and a corrosion-resistant grade. Red bars would lose money under the current assumptions.")
if ev and ev.selection and ev.selection.points:
    y = ev.selection.points[0].get("y", "")
    u = y.split(" · ")[0]
    b1, b2 = st.columns([3, 1])
    b1.markdown(f"Selected **{u}**.")
    if b2.button("Open well card", icon=":material/arrow_forward:"):
        ui.open_well(u)

# ---------------------------------------------------------------- break-even + by cause
left, right = st.columns([3, 2])
with left:
    lam = np.linspace(0.5, 12, 200)
    fig = go.Figure()
    for h_r, lab, dash in ((econ["hr_chronic"], f"central effect (HR {econ['hr_chronic']:.2f})", None),
                           (econ["hr_chronic_hi"], f"weakest effect (HR {econ['hr_chronic_hi']:.2f})", "dash")):
        _, nn = well_net(lam, econ, pm3, hr=h_r, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
        fig.add_trace(go.Scatter(x=lam, y=nn / 1e3, mode="lines", name=lab, line=dict(color=ui.BLUE, width=2, dash=dash),
                                 hovertemplate="%{x:.1f} failures/yr → %{y:,.0f}k<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=ui.MUTED, width=1))
    fig.add_vline(x=be, line=dict(color=ui.CRITICAL, width=1.5, dash="dot"),
                  annotation_text=f"pays back above {be:.1f}/yr", annotation_position="top right")
    fig.update_layout(title="When does a new string pay back?", xaxis_title="rod repairs per year on the well",
                      yaxis_title="net value (k C$)")
    ui.show(ui.style(fig, 320))
    ui.explain("Every program well fails at least 3 times a year, well to the right of the pay-back line.")
with right:
    by = prog.groupby("top_cause").agg(wells=("uwi", "size"), net=("net", "sum")).reset_index().sort_values("net",
                                                                                                         ascending=False)
    fig = ui.hbar(by["top_cause"], by["net"] / 1e6, text=[f"{w} wells" for w in by["wells"]], xaxis="C$M",
                  hover="%{y}: %{x:.2f}M<extra></extra>", title="Value by most common failure cause (C$M)", height=320)
    fig.update_xaxes(range=[0, max(by["net"].max() / 1e6 * 1.35, 0.01)])
    ui.show(fig)
    ui.explain("Most of the value sits in fatigue and corrosion wells.")

# ---------------------------------------------------------------- stress test (replaces the sensitivity table)
st.subheader("Does it survive pessimism?")
sens = sensitivity(prog["repairs_last365"], econ, pm3)
sens = sens[~sens["scenario"].str.startswith("worst combo")]
colors = [ui.BLUE if v > 0 else ui.CRITICAL for v in sens["program_net_CAD"]]
fig = ui.hbar(sens["scenario"], sens["program_net_CAD"] / 1e6, colors=colors,
              text=[f"{ui.money(v)} · pays back above {b:.1f}/yr · {w} wells positive"
                    for v, b, w in zip(sens["program_net_CAD"], sens["breakeven_failures_per_yr"], sens["wells_positive"])],
              xaxis="program net value (C$M)", hover="%{y}: %{x:.2f}M<extra></extra>",
              title="Program value when one assumption at a time goes against us")
lo = min(0, sens["program_net_CAD"].min() / 1e6 * 1.3)
fig.update_xaxes(range=[lo, sens["program_net_CAD"].max() / 1e6 * 1.9])
ui.show(fig)
ui.explain("Each bar changes one assumption and keeps the rest at the central case.")

worst = worst_case_wells(prog, econ, pm3)
st.markdown(f"**Start with these {len(worst)}.** They pay back even when every pessimistic case is true at once "
            "(weakest effect, job cost only, double string cost, 1 year).")
if len(worst):
    fig = ui.hbar([f"{u} · {a}" for u, a in zip(worst["uwi"], worst["area"])], worst["worst_case_net"] / 1e3,
                  text=[f"{ui.money(v)} · {r} repairs" for v, r in zip(worst["worst_case_net"], worst["repairs_last365"])],
                  xaxis="net value in the worst case (k C$)", hover="%{y}<br>%{x:,.0f}k C$<extra></extra>",
                  colors=ui.AQUA)
    fig.update_xaxes(range=[0, worst["worst_case_net"].max() / 1e3 * 1.5])
    ui.show(fig)
st.caption(f"From the job records: repair job C${econ['repair_job_cost']:,.0f} on average (2023 on, cost > 0), "
           f"{econ['lost_m3_per_repair_mean']:.1f} m³ of oil lost per repair, a new string costs C${econ['inc_cost']:,.0f} "
           f"more than a repair. Lost oil valued at C${pm3:,.0f}/m³.")
