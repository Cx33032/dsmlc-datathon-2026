"""Today's queue: which newly reported equipment outage should an engineer review first?"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

top_slot = ui.header(
    "Which outage should you review first today?",
    how=["Pick a day. The app opens on the busiest recent day.",
         "Read the sentence under the title. It names the outage with the most oil at risk.",
         "Press **Open the well card** to see what to do at the pull.",
         "Use the filters to show only your area, one cause, or chronic rod wells. The ranking then covers only "
         "the outages you can see.",
         "Click a bar to see why that outage ranks where it does."],
    terms=["Outage", "Oil at risk", "Chronic rod well", "UWI", "m³", "C$", "Replay"])
if not ui.require("dispatch_tickets.parquet", "dispatch_replay.csv"):
    st.stop()

t = ui.art("dispatch_tickets.parquet")
days = sorted(t["production_date"].dt.date.unique())
recent = t[t["production_date"] > t["production_date"].max() - pd.Timedelta(days=14)]
default_day = recent.groupby(recent["production_date"].dt.date).size().idxmax()   # busiest recent day
DECIDE, REPLAY = "What was known that day", "Add what happened next (replay)"

with ui.filters(reset_keys=["q_day", "q_area", "q_cause", "q_k", "q_chronic", "q_mode"]):
    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1])
    day = c1.date_input("Day", value=default_day, min_value=days[0], max_value=days[-1], key="q_day")
    day_t = t[t["production_date"].dt.date == day]
    areas = c2.multiselect("Area", sorted(day_t["field_operating_area"].unique()), placeholder="All areas", key="q_area")
    causes = c3.multiselect("Cause", sorted(day_t["loss_category"].unique()), placeholder="All causes", key="q_cause")
    k = c4.number_input("Outages you can review today", 1, 10, 2, key="q_k",
                        help="The top ones are drawn in blue and get a reason card below the chart.")
    d1, d2 = st.columns([1, 2.6])
    chronic_only = d1.toggle("Show only chronic rod wells", key="q_chronic", help=ui.TERMS["Chronic rod well"])
    mode = d2.segmented_control("Show", [DECIDE, REPLAY], required=True, default=DECIDE, key="q_mode",
                                help="The first option shows only what was known at the end of the day. Replay also "
                                     "shows what each outage lost over the next 3 days, to check the ranking.")
replay = mode == REPLAY

q = day_t.copy()
if areas:
    q = q[q["field_operating_area"].isin(areas)]
if causes:
    q = q[q["loss_category"].isin(causes)]
if chronic_only:
    q = q[q["chronic"]]
q = q.sort_values("score_m3", ascending=False).reset_index(drop=True)
if q.empty:
    ui.empty(f"No new equipment outages match these filters on {day:%d %b %Y}.",
             "Pick another day, remove a filter, or press Reset filters.")
    st.stop()
pm3 = ui.price_m3()
q["rank"] = range(1, len(q) + 1)
q["at_risk_cad"] = q["score_m3"] * pm3
top = q.head(k)
first = q.iloc[0]
share = 100 * top["score_m3"].sum() / max(q["score_m3"].sum(), 1e-9)

# ---------------------------------------------------------------- the answer
with top_slot:
    ui.summary(top_slot, f"Review <b>#1 {first['uwi']}</b> ({first['field_operating_area']}) first: "
                         f"<b>{first['score_m3']:.1f} m³</b> of oil (≈ {ui.money(first['at_risk_cad'])}) is at risk over "
                         f"the next 3 days. That is the most of the {len(q)} new outages on {day:%d %b %Y}. "
                         f"Your top {len(top)} hold {share:.0f}% of the oil at risk.")
    if st.button(f"Open the well card for {first['uwi']}", type="primary", icon=":material/arrow_forward:",
                 key="q_open_first"):
        ui.open_well(first["uwi"])

m1, m2, m3, m4 = st.columns(4)
m1.metric("New outages", len(q), help="After the filters.")
m2.metric(f"Oil at risk in your top {len(top)}", f"{top['score_m3'].sum():,.1f} m³", f"{share:.0f}% of the list",
          delta_arrow="off", delta_color="off")
m3.metric(f"Value at risk in your top {len(top)}", ui.money(top["at_risk_cad"].sum()))
m4.metric("Chronic rod wells", int(q["chronic"].sum()), help=ui.TERMS["Chronic rod well"])

# ---------------------------------------------------------------- the queue as a chart
lab = [f"#{r.rank} {r.uwi} · {r.field_operating_area}" for r in q.itertuples()]
colors = [ui.BLUE if r <= k else ui.GRAY for r in q["rank"]]
txt = [f"{v:.1f} m³ · {c}{' · chronic rod well' if ch else ''}"
       for v, c, ch in zip(q["score_m3"], q["loss_category"], q["chronic"])]
fig = ui.hbar(lab, q["score_m3"], colors=colors, text=txt, xaxis="oil at risk over the next 3 days (m³)",
              hover="%{y}<br>%{x:.1f} m³ at risk<extra></extra>",
              title=f"The {len(top)} blue outages hold {share:.0f}% of the oil at risk on {day:%d %b %Y}")
if replay:
    fig.add_trace(go.Scatter(y=lab, x=q["exposure_m3"], mode="markers", name="actually lost over the next 3 days",
                             marker=dict(symbol="diamond", size=11, color=ui.ORANGE, line=dict(color="white", width=1.5)),
                             hovertemplate="%{y}<br>actual: %{x:.1f} m³<extra></extra>"))
    fig.update_layout(showlegend=True)
fig.update_xaxes(range=[0, max(q["score_m3"].max(), q["exposure_m3"].max() if replay else 0) * 1.45])
ev = ui.show(fig, on_select="rerun", selection_mode="points", key="queue_chart")
ui.explain("Each bar is one new outage, ranked by oil at risk. Blue = the outages you can review today. "
           "Filters re-rank the list, so 'top 2' means the top 2 of what you can see."
           + (" Orange diamonds show what each outage actually lost. Nobody knew this on the day." if replay else ""))
if replay:
    oc1, oc2 = st.columns(2)
    oc1.metric(f"Share of the actual loss in your top {len(top)}",
               f"{100 * top['exposure_m3'].sum() / max(q['exposure_m3'].sum(), 1e-9):.0f}%",
               help=ui.TERMS["Exposure"])
    oc2.metric(f"Same, using the operator's recorded loss",
               f"{100 * top['recorded_loss_m3'].sum() / max(q['recorded_loss_m3'].sum(), 1e-9):.0f}%",
               help=ui.TERMS["Recorded loss"])

# ---------------------------------------------------------------- reason cards
picked = None
if ev and ev.selection and ev.selection.points:
    y = ev.selection.points[0].get("y")
    if y in lab:
        picked = q.iloc[lab.index(y)]
cards = [picked] if picked is not None else [r for _, r in top.iterrows()]
st.header(f"Why #{int(picked['rank'])} ranks there" if picked is not None else f"Why the top {len(cards)} rank there")
if picked is None:
    st.caption("Click any bar in the chart to see the reason for that outage.")
for r in cards:
    with st.container(border=True):
        a, b = st.columns([3, 1])
        badge = " :blue-badge[chronic rod well]" if r["chronic"] else ""
        a.markdown(f"**#{r['rank']} · {r['uwi']}** · {r['field_operating_area']}{badge}")
        a.markdown(f"Reported **{r['reason']}** with **{r['first_day_hours']:.0f} h** down on day 1. Outages like this "
                   f"stayed down **{r['est_down_h']:.1f} h** more over the next 3 days (based on {r['cell_n']:,} past "
                   f"cases). The well's healthy rate is **{r['rate_h']:.1f} m³/d**, so **{r['score_m3']:.1f} m³** "
                   f"(≈ {ui.money(r['at_risk_cad'])}) is at risk.")
        a.caption(f"{r['rod_repairs_365']} rod repairs in the year before this outage.")
        if r["pull_recommendation"]:
            a.success(r["pull_recommendation"], icon=":material/build:")
        if b.button("Open well card", key=f"wc_{r['uwi']}_{r['rank']}", icon=":material/arrow_forward:"):
            ui.open_well(r["uwi"])

# ---------------------------------------------------------------- facility restart laggards on this day
lagq = ui.art("facility_laggards.parquet")
if lagq is not None and len(lagq):
    D = pd.Timestamp(day)
    end = lagq["restart"].fillna(pd.to_datetime(lagq["t75"]) + pd.Timedelta(days=30))
    live = lagq[(pd.to_datetime(lagq["t75"]) + pd.Timedelta(days=3) <= D) & (D < end)]
    if areas:
        live = live[live["area"].isin(areas)]
    if len(live):
        with st.container(border=True):
            a, b = st.columns([4, 1])
            a.markdown(f"**:material/factory: Restart check needed: {len(live)} well(s) still down after their facility "
                       f"restarted**")
            for r in live.itertuples():
                a.markdown(f"- {r.uwi} at {r.facility_name}: 75% of the other wells there are back since "
                           f"{pd.Timestamp(r.t75):%d %b}. About {r.rate_h:.1f} m³/d is waiting.")
            if b.button("Open facility restarts", icon=":material/arrow_forward:"):
                st.switch_page(ui.PAGES["facility"])

# ---------------------------------------------------------------- validation, as a chart
with st.expander("Does this ranking work? Check it on 2026"):
    rep = ui.art("dispatch_replay.csv")
    info = ui.art("dispatch_info.json") or {}
    kk = st.select_slider("Outages reviewed per day", options=sorted(rep["K"].unique()), value=2 if 2 in set(rep["K"]) else
                          int(rep["K"].min()), key="val_k")
    r = rep[rep["K"] == kk]
    fig = go.Figure()
    for col, name, color in (("first_day_loss", "rank by day-1 reported loss", ui.GRAY),
                             ("dispatch", "this queue", ui.BLUE), ("oracle", "perfect hindsight", ui.MUTED)):
        fig.add_trace(go.Bar(x=r["outcome"], y=100 * r[col], name=name, marker_color=color,
                             text=[f"{100 * v:.0f}%" for v in r[col]], textposition="outside",
                             hovertemplate=name + ": %{y:.1f}%<extra></extra>"))
    better = bool((r["dispatch"] > r["first_day_loss"]).all())
    fig.update_layout(title=(f"At {kk} reviews a day, this queue catches more of the next 3 days' lost oil than ranking "
                             "by day-1 loss" if better else
                             f"Share of the next 3 days' lost oil caught at {kk} reviews a day"),
                      barmode="group", yaxis=dict(range=[0, 110], title="share of lost oil caught (%)"),
                      xaxis_title="how lost oil is measured")
    ui.show(ui.style(fig, 300))
    ui.explain(f"The queue was fitted on outages up to Dec 28, 2025, then re-run on every day of 2026 "
               f"({info.get('tickets_test', 0):,} outages, {info.get('tickets_per_day', 0):.1f} a day). "
               "Reconstructed exposure uses the well's healthy rate. Recorded loss uses the operator's lost-oil field.")
