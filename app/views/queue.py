"""Today's queue: which newly reported equipment outage should an engineer review first?"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

st.title("Today's queue")
ui.intro("Which of today's new equipment outages will cost the most oil if nobody looks at it?",
         ["Pick a <b>day</b> and narrow the list with the <b>filters</b> (your area, a cause, chronic wells only).",
          "Read the <b>chart</b>: each bar is one outage, longest = most oil at risk over the next 3 days. "
          "Blue bars are the ones to review today.",
          "<b>Click a bar</b> (or read the cards below) to see why it ranks there and what to do at the pull."])
if not ui.require("dispatch_tickets.parquet", "dispatch_replay.csv"):
    st.stop()

t = ui.art("dispatch_tickets.parquet")
days = sorted(t["production_date"].dt.date.unique())
recent = t[t["production_date"] > t["production_date"].max() - pd.Timedelta(days=14)]
default_day = recent.groupby(recent["production_date"].dt.date).size().idxmax()   # busiest recent day

with ui.filters():
    c1, c2, c3, c4 = st.columns([1.1, 1.4, 1.4, 1])
    day = c1.date_input("Day", value=default_day, min_value=days[0], max_value=days[-1])
    day_t = t[t["production_date"].dt.date == day]
    areas = c2.multiselect("Area", sorted(day_t["field_operating_area"].unique()), placeholder="All areas")
    causes = c3.multiselect("Cause", sorted(day_t["loss_category"].unique()), placeholder="All causes")
    k = c4.number_input("Reviews per day", 1, 10, 2, help="How many outages your team can look at today. "
                                                           "The top ones are drawn in blue.")
    d1, d2 = st.columns([1, 2.6])
    chronic_only = d1.toggle("Chronic rod wells only", help="Wells with 3+ rod repairs in the past year and no new string.")
    mode = d2.segmented_control("View", ["Decision", "Replay (what actually happened)"], default="Decision",
                                help="Decision shows only what was known at the end of the day. Replay adds the next "
                                     "3 days, to check the ranking after the fact.")
replay = mode == "Replay (what actually happened)"

q = day_t.copy()
if areas:
    q = q[q["field_operating_area"].isin(areas)]
if causes:
    q = q[q["loss_category"].isin(causes)]
if chronic_only:
    q = q[q["chronic"]]
q = q.sort_values("score_m3", ascending=False).reset_index(drop=True)
if q.empty:
    st.info("No new equipment outages match these filters on this day. Try another day or clear a filter.")
    st.stop()
pm3 = ui.price_m3()
q["rank"] = range(1, len(q) + 1)
q["at_risk_cad"] = q["score_m3"] * pm3
top = q.head(k)

m1, m2, m3, m4 = st.columns(4)
m1.metric("New outages", len(q), help="After the filters.")
m2.metric(f"Oil at risk, top {k}", f"{top['score_m3'].sum():,.1f} m³",
          f"{100 * top['score_m3'].sum() / max(q['score_m3'].sum(), 1e-9):.0f}% of the list", delta_arrow="off",
          delta_color="off")
m3.metric(f"Value at risk, top {k}", ui.money(top["at_risk_cad"].sum()))
m4.metric("Chronic rod wells", int(q["chronic"].sum()))

# ---------------------------------------------------------------- the queue as a chart
lab = [f"#{r.rank} {r.uwi} · {r.field_operating_area}" for r in q.itertuples()]
colors = [ui.BLUE if r <= k else ui.GRAY for r in q["rank"]]
txt = [f"{v:.1f} m³ · {c}{' · CHRONIC' if ch else ''}" for v, c, ch in zip(q["score_m3"], q["loss_category"], q["chronic"])]
fig = ui.hbar(lab, q["score_m3"], colors=colors, text=txt, xaxis="oil at risk over the next 3 days (m³)",
              hover="%{y}<br>%{x:.1f} m³ at risk<extra></extra>",
              title=f"Today's outages, most oil at risk first ({len(q)})")
if replay:
    fig.add_trace(go.Scatter(y=lab, x=q["exposure_m3"], mode="markers", name="actually lost over next 3 days",
                             marker=dict(symbol="diamond", size=11, color=ui.ORANGE, line=dict(color="white", width=1.5)),
                             hovertemplate="%{y}<br>actual: %{x:.1f} m³<extra></extra>"))
    fig.update_layout(showlegend=True)
fig.update_xaxes(range=[0, max(q["score_m3"].max(), q["exposure_m3"].max() if replay else 0) * 1.45])
ev = ui.show(fig, on_select="rerun", selection_mode="points", key="queue_chart")
ui.explain("Oil at risk = expected extra hours down (from past outages with the same reason and day-1 hours) × the "
           "well's healthy rate. Filters re-rank the list, so 'top 2' means top 2 of what you can see."
           + (" Orange diamonds show what each outage actually lost; they were not known on the day." if replay else ""))
if replay:
    oc1, oc2 = st.columns(2)
    oc1.metric(f"Top {k} caught this share of the actual loss",
               f"{100 * top['exposure_m3'].sum() / max(q['exposure_m3'].sum(), 1e-9):.0f}%")
    oc2.metric(f"Top {k}, using the operator's recorded loss",
               f"{100 * top['recorded_loss_m3'].sum() / max(q['recorded_loss_m3'].sum(), 1e-9):.0f}%")

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
                a.markdown(f"- {r.uwi} at {r.facility_name}: 75% of its peers back since {pd.Timestamp(r.t75):%d %b}, "
                           f"≈{r.rate_h:.1f} m³/d waiting")
            if b.button("Facility restarts", icon=":material/arrow_forward:"):
                st.switch_page(ui.PAGES["facility"])

# ---------------------------------------------------------------- reason cards
picked = None
if ev and ev.selection and ev.selection.points:
    y = ev.selection.points[0].get("y")
    if y in lab:
        picked = q.iloc[lab.index(y)]
cards = [picked] if picked is not None else [r for _, r in top.iterrows()]
st.subheader("Why it ranks there" if picked is not None else f"Why the top {len(cards)} rank there")
if picked is None:
    st.caption("Click any bar above to see its card instead.")
for r in cards:
    with st.container(border=True):
        a, b = st.columns([3, 1])
        badge = " :red-badge[CHRONIC]" if r["chronic"] else ""
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

# ---------------------------------------------------------------- validation, as a chart
with st.expander("Does this ranking work? (2026 replay)"):
    rep = ui.art("dispatch_replay.csv")
    info = ui.art("dispatch_info.json") or {}
    kk = st.select_slider("Reviews per day", options=sorted(rep["K"].unique()), value=2 if 2 in set(rep["K"]) else
                          int(rep["K"].min()), key="val_k")
    r = rep[rep["K"] == kk]
    fig = go.Figure()
    for col, name, color in (("first_day_loss", "rank by day-1 reported loss", ui.GRAY),
                             ("dispatch", "this queue", ui.BLUE), ("oracle", "perfect hindsight", ui.MUTED)):
        fig.add_trace(go.Bar(x=r["outcome"], y=100 * r[col], name=name, marker_color=color,
                             text=[f"{100 * v:.0f}%" for v in r[col]], textposition="outside",
                             hovertemplate=name + ": %{y:.1f}%<extra></extra>"))
    fig.update_layout(title=f"Share of the next 3 days' lost oil caught by reviewing the top {kk} a day",
                      barmode="group", yaxis=dict(range=[0, 110], title="%"))
    ui.show(ui.style(fig, 300))
    ui.explain(f"Fitted on outages up to Dec 28, 2025, then replayed on every day of 2026 "
               f"({info.get('tickets_test', 0):,} outages, {info.get('tickets_per_day', 0):.1f} a day). "
               "'Reconstructed exposure' uses the healthy rate; 'recorded loss' uses the operator's lost-oil field.")
