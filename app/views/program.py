"""Replacement program: which chronic wells get a new rod string, and is it worth it?"""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

import ui
from src.economics import breakeven, fail_cost, sensitivity, well_net, worst_case_wells

top_slot = ui.header(
    "Which wells should get a new rod string, and does it pay?",
    how=["Read the sentence under the title: what the program costs, what it saves, and where to start.",
         "Open 'Test the assumptions' and set each one to its pessimistic value. Check that the net value stays "
         "positive.",
         "Pick a well under the ranked chart, or click a bar, to open its well card.",
         "Use the filters to show one area, one failure cause, or only the worst wells."],
    terms=["Chronic rod well", "Rod string", "Net value", "Pays back above", "HR", "CI", "Section", "Corrosion remedy",
           "UWI", "m³", "C$"])
if not ui.require("ideas/1/chronic_wells.csv", "ideas/1/economics.json", "recommendations.parquet"):
    st.stop()
econ = ui.art("ideas/1/economics.json")
prog_all = ui.art("ideas/1/chronic_wells.csv").merge(
    ui.art("recommendations.parquet")[["uwi", "section_status", "corrosion_status"]], on="uwi", how="left")
prog_all["top_cause"] = prog_all["top_cause"].fillna("not in failure log")
pm3 = ui.price_m3()

with ui.filters(reset_keys=["p_area", "p_cause", "p_min", "p_extra"]):
    c1, c2, c3, c4 = st.columns([1.2, 1.3, 1, 1.4])
    areas = c1.multiselect("Area", sorted(prog_all["area"].dropna().unique()), placeholder="All areas", key="p_area")
    causes = c2.multiselect("Most common failure cause", sorted(prog_all["top_cause"].unique()),
                            placeholder="All causes", key="p_cause")
    min_rep = c3.slider("At least this many rod repairs last year", 3, int(prog_all["repairs_last365"].max()), 3,
                        key="p_min")
    extra = c4.multiselect("Show only wells that also need", ["Section", "Corrosion remedy"], placeholder="Anything",
                           key="p_extra")
prog = prog_all[prog_all["repairs_last365"] >= min_rep]
if areas:
    prog = prog[prog["area"].isin(areas)]
if causes:
    prog = prog[prog["top_cause"].isin(causes)]
if "Section" in extra:
    prog = prog[prog["section_status"] == "recommend"]
if "Corrosion remedy" in extra:
    prog = prog[prog["corrosion_status"] == "recommend"]
if prog.empty:
    ui.empty("No program wells match these filters.",
             "Lower the minimum number of repairs, remove a filter, or press Reset filters.")
    st.stop()

with st.expander("Test the assumptions", icon=":material/tune:"):
    s1, s2, s3, s4 = st.columns(4)
    EXPECTED, WEAKEST = "expected", "weakest (upper 95% CI)"
    hr_lab = s1.radio("Effect of a new string", [EXPECTED, WEAKEST],
                      help=f"Hazard ratio (HR) of the next rod repair after a new string vs after a repair: "
                           f"{econ['hr_chronic']:.2f} (95% confidence interval {econ['hr_chronic_lo']:.2f} to "
                           f"{econ['hr_chronic_hi']:.2f}). Lower = bigger effect.")
    mult = s2.radio("Cost of a new string", ["as recorded", "double"])
    horizon = s3.radio("Years of benefit counted", ["2 years", "1 year"])
    lost_on = s4.toggle("Count lost oil", value=True, help="Off = count only the repair job cost.")
    st.caption("The oil price is in the sidebar. Every number on this page changes with these settings.")
hr = econ["hr_chronic"] if hr_lab == EXPECTED else econ["hr_chronic_hi"]
cm_ = 2.0 if mult == "double" else 1.0
hz = 2.0 if horizon == "2 years" else 1.0
avoided, net = well_net(prog["repairs_last365"], econ, pm3, hr=hr, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
prog = prog.assign(avoided=avoided, net=net).sort_values("net", ascending=False)
be = breakeven(econ, pm3, hr=hr, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
worst = worst_case_wells(prog, econ, pm3)
# Net value = (repairs avoided × cost of one failure) - extra cost of a new string; split it into its two parts.
fc = fail_cost(econ, pm3, lost_on)
cost = len(prog) * econ["inc_cost"] * cm_
saved = float(prog["avoided"].sum()) * fc
n_pos = int((prog["net"] > 0).sum())

# ---------------------------------------------------------------- the answer
with top_slot:
    ui.summary(top_slot, f"New strings on these <b>{len(prog)} wells</b> cost <b>{ui.money(cost)}</b> more than repairs "
                         f"and avoid <b>{ui.money(saved)}</b> of repair jobs{' and lost oil' if lost_on else ''} over "
                         f"{hz:.0f} year{'s' if hz > 1 else ''}: a net <b>{ui.money(prog['net'].sum())}</b>. "
                         f"{n_pos} of {len(prog)} wells pay back. "
                         + (f"Start with the {len(worst)} wells that pay back even in the worst case."
                            if len(worst) else ""))
    if len(worst) and st.button(f"Open the well card for {worst.iloc[0]['uwi']}", type="primary",
                                icon=":material/arrow_forward:", key="p_open_first"):
        ui.open_well(worst.iloc[0]["uwi"])

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Wells", len(prog), f"{int(prog['repairs_last365'].sum())} rod repairs last year", delta_arrow="off",
          delta_color="off")
m2.metric("Extra cost", ui.money(cost), help=f"Extra cost of the new strings: C${econ['inc_cost']:,.0f} more than a repair, per well"
                                                             + (", doubled" if cm_ > 1 else "") + ".")
m3.metric(f"Saved, {hz:.0f} yr", ui.money(saved),
          help="Repairs avoided × cost of one rod failure (repair job" + (" + lost oil)." if lost_on else ")."))
m4.metric(f"Net value, {hz:.0f} yr", ui.money(prog["net"].sum()), help=ui.TERMS["Net value"])
m5.metric("Pays back above", f"{be:.1f}/yr", help=ui.TERMS["Pays back above"] + " Unit: rod repairs per year.")

# ---------------------------------------------------------------- what "net value" means
gross, capex = saved, cost
with st.expander(f"How the net value over {hz:.0f} yr is worked out", icon=":material/calculate:"):
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
            totals=dict(marker=dict(color=ui.BLUE)), hovertemplate="%{x}: C$%{y:.2f}M<extra></extra>"))
        fig.update_layout(title=f"Savings minus extra cost leave {ui.money(gross - capex)} over {hz:.0f} yr",
                          yaxis_title="million C$", showlegend=False)
        fig.update_yaxes(range=[min(0, (gross - capex) / 1e6 * 1.2), gross / 1e6 * 1.2])
        ui.show(ui.style(fig, 320))

# ---------------------------------------------------------------- ranked wells (replaces the table)
st.header("Which wells first")
n = st.slider("Number of wells to show", 5, max(5, min(60, len(prog))), min(20, len(prog)), key="prog_n")
g = prog.head(n)
colors = [ui.BLUE if v > 0 else ui.CRITICAL for v in g["net"]]
tags = [" · ".join(x for x in (f"{r} repairs", "section" if s == "recommend" else "", "corrosion" if c == "recommend" else "") if x)
        for r, s, c in zip(g["repairs_last365"], g["section_status"], g["corrosion_status"])]
fig = ui.hbar([f"{u} · {a}" for u, a in zip(g["uwi"], g["area"])], g["net"] / 1e3, colors=colors,
              text=[f"{ui.money(v)} · {t}" for v, t in zip(g["net"], tags)],
              xaxis=f"net value of a new string over {hz:.0f} yr (thousand C$)",
              hover="%{y}<br>C$%{x:,.0f}k<extra></extra>",
              title=f"{g.iloc[0]['uwi']} gains the most from a new string: {ui.money(g.iloc[0]['net'])}")
fig.update_xaxes(range=[min(0, g["net"].min() / 1e3 * 1.2), g["net"].max() / 1e3 * 1.55])
ev = ui.show(fig, on_select="rerun", selection_mode="points", key="prog_rank")
ui.explain("Wells are ranked by net value. 'section' = breaks cluster in one band, so a section and guides may be "
           "enough. 'corrosion' = add an inhibitor and a corrosion-resistant grade. A red bar would lose money under "
           "the current settings.")
picked = ev.selection.points[0].get("y", "").split(" · ")[0] if ev and ev.selection and ev.selection.points else None
order = list(g["uwi"])
b1, b2 = st.columns([3, 1], vertical_alignment="bottom")
sel = b1.selectbox("Well to open", order, index=order.index(picked) if picked in order else 0,
                   format_func=lambda u: f"{u} · {ui.money(float(g.loc[g['uwi'] == u, 'net'].iloc[0]))}")
if b2.button("Open well card", icon=":material/arrow_forward:", key="p_open_sel", width="stretch"):
    ui.open_well(sel)

# ---------------------------------------------------------------- break-even + by cause
left, right = st.columns([3, 2])
with left:
    lam = np.linspace(0.5, 12, 200)
    fig = go.Figure()
    for h_r, lab, dash in ((econ["hr_chronic"], f"expected effect (HR {econ['hr_chronic']:.2f})", None),
                           (econ["hr_chronic_hi"], f"weakest effect (HR {econ['hr_chronic_hi']:.2f})", "dash")):
        _, nn = well_net(lam, econ, pm3, hr=h_r, cost_mult=cm_, horizon=hz, lost_oil=lost_on)
        fig.add_trace(go.Scatter(x=lam, y=nn / 1e3, mode="lines", name=lab, line=dict(color=ui.BLUE, width=2, dash=dash),
                                 hovertemplate="%{x:.1f} repairs/yr: C$%{y:,.0f}k<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=ui.MUTED, width=1))
    fig.add_vline(x=be, line=dict(color=ui.CRITICAL, width=1.5, dash="dot"),
                  annotation_text=f"pays back above {be:.1f}/yr", annotation_position="top right")
    fig.update_layout(title=f"A new string pays back on any well with more than {be:.1f} rod repairs a year",
                      xaxis_title="rod repairs per year on the well",
                      yaxis_title=f"net value over {hz:.0f} yr (thousand C$)")
    ui.show(ui.style(fig, 320))
    ui.explain("Every program well has at least 3 rod repairs a year, to the right of the pay-back line.")
with right:
    by = prog.groupby("top_cause").agg(wells=("uwi", "size"), net=("net", "sum")).reset_index().sort_values("net",
                                                                                                         ascending=False)
    fig = ui.hbar(by["top_cause"], by["net"] / 1e6, text=[f"{w} wells" for w in by["wells"]],
                  xaxis="net value (million C$)", hover="%{y}: C$%{x:.2f}M<extra></extra>",
                  title=f"{by.iloc[0]['top_cause']} wells hold the most value", height=320)
    fig.update_xaxes(range=[0, max(by["net"].max() / 1e6 * 1.35, 0.01)])
    ui.show(fig)
    ui.explain("Wells are grouped by their most common coded failure cause.")

# ---------------------------------------------------------------- stress test (replaces the sensitivity table)
st.header("Does it survive pessimism?")
NAMES = {"central": "Expected case",
         "HR at upper 95% CI": "Weakest new-string effect (upper 95% CI)",
         "lost oil = median per event": "Lost oil per repair at the median",
         "lost oil ignored (job cost only)": "Repair job cost only, no lost oil",
         "oil price -30%": "Oil price 30% lower",
         "incremental replace cost x2": "New string costs twice as much",
         "1-year horizon": "Only 1 year of benefit"}
sens = sensitivity(prog["repairs_last365"], econ, pm3)
sens = sens[~sens["scenario"].str.startswith("worst combo")].reset_index(drop=True)
vals = sens["program_net_CAD"] / 1e6
labels = [NAMES.get(s, s) for s in sens["scenario"]]
txt = [f"{ui.money(v)} · {w} wells pay back" for v, w in zip(sens["program_net_CAD"], sens["wells_positive"])]
fig = ui.hbar(labels, vals, colors=[ui.BLUE if v > 0 else ui.CRITICAL for v in vals],
              text=[t if v > 0 else "" for t, v in zip(txt, vals)],
              xaxis="program net value (million C$)", customdata=sens["breakeven_failures_per_yr"],
              hover="%{y}: C$%{x:.2f}M, pays back above %{customdata:.1f} repairs/yr<extra></extra>",
              title=f"The program stays positive in {int((vals[1:] > 0).sum())} of {len(vals) - 1} pessimistic cases")
neg = vals <= 0
if neg.any():   # labels of negative bars go right of zero, so they never collide with the axis labels
    fig.add_trace(go.Scatter(x=[0] * int(neg.sum()), y=[l for l, m in zip(labels, neg) if m], mode="text",
                             text=["  " + t for t, m in zip(txt, neg) if m], textposition="middle right",
                             hoverinfo="skip", showlegend=False, cliponaxis=False))
lo = min(0, vals.min() * 1.3)
fig.update_xaxes(range=[lo, vals.max() * 1.9])
fig.update_layout(showlegend=False)
ui.show(fig)
ui.explain("Each bar changes one assumption and keeps the rest at the expected case.")

if len(worst):
    fig = ui.hbar([f"{u} · {a}" for u, a in zip(worst["uwi"], worst["area"])], worst["worst_case_net"] / 1e3,
                  text=[f"{ui.money(v)} · {r} repairs" for v, r in zip(worst["worst_case_net"], worst["repairs_last365"])],
                  xaxis="net value in the worst case (thousand C$)", hover="%{y}<br>C$%{x:,.0f}k<extra></extra>",
                  title=f"Start with these {len(worst)} wells: they pay back even in the worst case", colors=ui.AQUA)
    fig.update_xaxes(range=[0, worst["worst_case_net"].max() / 1e3 * 1.5])
    ui.show(fig)
    ui.explain("Worst case = the weakest new-string effect, repair job cost only, double string cost and 1 year of "
               "benefit, all at once.")
ui.explain(f"From the job records: a repair job costs C\\${econ['repair_job_cost']:,.0f} on average (2023 on, cost > 0), "
           f"each repair loses {econ['lost_m3_per_repair_mean']:.1f} m³ of oil, and a new string costs "
           f"C\\${econ['inc_cost']:,.0f} more than a repair. Lost oil is valued at C\\${pm3:,.0f}/m³.",
           label="Where the costs come from")
