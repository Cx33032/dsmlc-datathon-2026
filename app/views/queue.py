"""Today's queue: which newly reported equipment outage should an engineer review first?"""
import pandas as pd
import streamlit as st

import ui

st.title("Today's queue")
st.caption("Newly reported equipment outages, ranked by the oil expected to be lost over the next 3 days if nobody "
           "looks: shrunk estimate of remaining down hours (by reason × first-day hours) × the well's healthy rate.")
if not ui.require("dispatch_tickets.parquet", "dispatch_replay.csv"):
    st.stop()

t = ui.art("dispatch_tickets.parquet")
shock = ui.art("ideas/whiplash/verdict.json")
shock_kept = bool(shock and shock.get("keep"))
days = sorted(t["production_date"].dt.date.unique())

c1, c2, c3 = st.columns([1.2, 1.4, 1])
# default: the busiest queue day of the last two weeks of data (a quiet Sunday makes a poor first screen)
recent = t[t["production_date"] > t["production_date"].max() - pd.Timedelta(days=14)]
default_day = recent.groupby(recent["production_date"].dt.date).size().idxmax()
day = c1.date_input("Queue day", value=default_day, min_value=days[0], max_value=days[-1])
mode = c2.segmented_control("Mode", ["Decision", "Replay (retrospective)"], default="Decision",
                            help="Decision mode shows only what was known at the close of the day. Replay adds what "
                                 "actually happened over the next 3 days.")
k = c3.number_input("Reviews per day (K)", 1, 10, 2)
replay = mode == "Replay (retrospective)"

q = t[t["production_date"].dt.date == day].sort_values("score_m3", ascending=False).reset_index(drop=True)
if q.empty:
    st.info("No new equipment outages were reported on this day.")
    st.stop()
pm3 = ui.price_m3()
q["rank"] = range(1, len(q) + 1)
q["at_risk_cad"] = q["score_m3"] * pm3

m1, m2, m3, m4 = st.columns(4)
m1.metric("New outages today", len(q))
m2.metric(f"Oil at risk in top {k}", f"{q.head(k)['score_m3'].sum():,.1f} m³",
          f"{100 * q.head(k)['score_m3'].sum() / max(q['score_m3'].sum(), 1e-9):.0f}% of today's", delta_arrow="off",
          delta_color="off")
m3.metric(f"Value at risk, top {k}", ui.money(q.head(k)["at_risk_cad"].sum()), delta_arrow="off")
m4.metric("Chronic rod wells in queue", int(q["chronic"].sum()))

cols = {"rank": "#", "uwi": "Well", "field_operating_area": "Area", "loss_category": "Cause", "reason": "Reported reason",
        "first_day_hours": "Day-1 h down", "rate_h": "Healthy rate m³/d", "est_down_h": "Exp. down h (3 d)",
        "score_m3": "Oil at risk m³", "at_risk_cad": "C$ at risk", "chronic": "Chronic", "rod_repairs_365": "Rod repairs 365 d"}
if shock_kept and "shock_pct" in q:
    cols["shock_pct"] = "Shock pct"
if replay:
    cols.update({"future_down_h": "Actual down h (3 d)", "exposure_m3": "Actual exposure m³",
                 "recorded_loss_m3": "Recorded loss m³"})
view = q[list(cols)].rename(columns=cols)
view["Chronic"] = view["Chronic"].map({True: "CHRONIC", False: ""})
st.dataframe(view, hide_index=True, use_container_width=True, height=min(38 * (len(view) + 1), 420),
             column_config={"C$ at risk": st.column_config.NumberColumn(format="$%.0f"),
                            "Oil at risk m³": st.column_config.NumberColumn(format="%.1f"),
                            "Healthy rate m³/d": st.column_config.NumberColumn(format="%.1f"),
                            "Exp. down h (3 d)": st.column_config.NumberColumn(format="%.1f")})
if replay:
    picked = q.head(k)
    oc1, oc2 = st.columns(2)
    oc1.metric(f"Retrospective: exposure captured by top {k}",
               f"{100 * picked['exposure_m3'].sum() / max(q['exposure_m3'].sum(), 1e-9):.0f}%")
    oc2.metric(f"Retrospective: recorded loss captured by top {k}",
               f"{100 * picked['recorded_loss_m3'].sum() / max(q['recorded_loss_m3'].sum(), 1e-9):.0f}%")
    st.caption("Retrospective columns use days D+1..D+3 and were not available on the queue day.")

lagq = ui.art("facility_laggards.parquet")
if lagq is not None and len(lagq):
    D = pd.Timestamp(day)
    end = lagq["restart"].fillna(pd.to_datetime(lagq["t75"]) + pd.Timedelta(days=30))
    live = lagq[(pd.to_datetime(lagq["t75"]) + pd.Timedelta(days=3) <= D) & (D < end)]
    if len(live):
        with st.container(border=True):
            st.markdown(f"**Restart check needed: {len(live)} well(s) still down after their facility restarted**")
            for r in live.itertuples():
                st.markdown(f"- {r.uwi} at {r.facility_name}: 75% of peers back since {pd.Timestamp(r.t75):%d %b}, "
                            f"≈{r.rate_h:.1f} m³/d waiting")
            if st.button("Facility restarts", icon=":material/arrow_forward:"):
                st.switch_page(ui.PAGES["facility"])

st.subheader(f"Reason cards: top {min(k, len(q))}")
for r in q.head(k).itertuples():
    with st.container(border=True):
        a, b = st.columns([3, 1])
        badge = " :red-badge[CHRONIC]" if r.chronic else ""
        a.markdown(f"**#{r.rank} · {r.uwi}** · {r.field_operating_area}{badge}")
        a.markdown(f"Reported **{r.reason}** ({r.loss_category}) with **{r.first_day_hours:.0f} h** down on day 1. "
                   f"Outages like this stayed down **{r.est_down_h:.1f} h** more over the next 3 days on average "
                   f"(n = {r.cell_n} training cases, shrunk toward the {r.hours_bin} mean). Healthy rate "
                   f"**{r.rate_h:.1f} m³/d** → **{r.score_m3:.1f} m³** (≈ {ui.money(r.at_risk_cad)}) at risk.")
        a.caption(f"{r.rod_repairs_365} rod repairs in the 365 days before this outage.")
        if r.pull_recommendation:
            a.success(r.pull_recommendation, icon=":material/build:")
        if b.button("Well card", key=f"wc_{r.uwi}_{r.rank}", icon=":material/arrow_forward:"):
            ui.open_well(r.uwi)

with st.expander("How the queue was validated"):
    rep = ui.art("dispatch_replay.csv")
    info = ui.art("dispatch_info.json") or {}
    st.write(f"2026 holdout (Jan 1 – Oct 23, {info.get('tickets_test', 0):,} outages, "
             f"{info.get('tickets_per_day', 0):.1f} per day). Model fitted on outages up to Dec 28, 2025.")
    show = rep[rep["K"] == k] if (rep["K"] == k).any() else rep
    st.dataframe(show.assign(**{c: (100 * show[c]).round(1) for c in ["dispatch", "first_day_loss", "oracle"]})
                 .rename(columns={"dispatch": "Dispatch %", "first_day_loss": "Rank by day-1 loss %",
                                  "oracle": "Oracle %"}), hide_index=True, use_container_width=True)
