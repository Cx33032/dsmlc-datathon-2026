"""Facility restarts: one incident per synchronized facility outage, and the wells that lag the restart."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

st.title("Facility restarts")
st.caption("When a battery trips, many wells go down on the same day. Group them into one facility incident, then "
           "flag the wells still down 3+ days after 75% of their peers are back: they need a restart check, "
           "not a wait.")
if not ui.require("facility_incidents.parquet", "facility_laggards.parquet", "facility_affected.parquet",
                  "facility_info.json"):
    st.stop()
inc = ui.art("facility_incidents.parquet")
lag = ui.art("facility_laggards.parquet")
aff = ui.art("facility_affected.parquet")
info = ui.art("facility_info.json")
if inc is None or inc.empty:
    st.info("No synchronized facility outages in this data.")
    st.stop()
pm3 = ui.price_m3()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Synchronized outage days", info["sync_days"], f"across {info['facilities']} facilities", delta_arrow="off",
          delta_color="off")
m2.metric("Lost oil on onset days", f"{info['onset_lost_oil_m3']:,.0f} m³", ui.money(info["onset_lost_oil_m3"] * pm3),
          delta_arrow="off", delta_color="off")
m3.metric("Restart laggards", info["laggard_cases"],
          f"of {info['cohort_well_outages']:,} affected well-outages", delta_arrow="off", delta_color="off")
m4.metric("Oil lost while lagging", f"{info['lag_loss_m3']:,.0f} m³", ui.money(info["lag_loss_m3"] * pm3),
          delta_arrow="off", delta_color="off",
          help="Days down beyond the 75%-of-peers-back day × the well's healthy rate: what a timely restart check "
               "could have recovered.")

left, right = st.columns([3, 2])
with left:
    st.markdown("**Incidents**")
    v = inc.sort_values("start", ascending=False)
    sel = st.dataframe(v[["start", "facility_name", "area", "wells", "main_cause", "onset_lost_oil_m3",
                          "median_days_down", "laggards"]].rename(columns={
        "start": "Start", "facility_name": "Facility", "area": "Area", "wells": "Wells down", "main_cause": "Cause",
        "onset_lost_oil_m3": "Onset-day loss m³", "median_days_down": "Median days down", "laggards": "Laggards"}),
        hide_index=True, use_container_width=True, height=380, on_select="rerun", selection_mode="single-row",
        column_config={"Start": st.column_config.DateColumn(format="YYYY-MM-DD"),
                       "Onset-day loss m³": st.column_config.NumberColumn(format="%.0f")})
    pick = v.iloc[sel.selection.rows[0]] if sel.selection.rows else v.sort_values("laggards", ascending=False).iloc[0]
with right:
    a = aff[aff["incident"] == pick["incident"]].copy()
    a["days"] = a["days_down"]
    xs = np.arange(0, int(np.nanmax(a["days"].fillna(0))) + 2 if a["days"].notna().any() else 10)
    share = [(a["days"] <= x).mean() * 100 for x in xs]
    fig = go.Figure(go.Scatter(x=xs, y=share, mode="lines", line=dict(color=ui.BLUE, width=2, shape="hv"),
                               name="wells back", hovertemplate="day %{x}: %{y:.0f}% back<extra></extra>"))
    fig.add_hline(y=75, line=dict(color=ui.MUTED, width=1, dash="dot"), annotation_text="75% of peers back")
    if pd.notna(pick["t75"]):
        t75d = (pd.Timestamp(pick["t75"]) - pd.Timestamp(pick["start"])).days
        fig.add_vrect(x0=t75d + 3, x1=max(xs.max(), t75d + 4), fillcolor=ui.CRITICAL, opacity=0.08, line_width=0,
                      annotation_text="laggard zone", annotation_position="top left")
    fig.update_layout(title=f"Restart curve: {pick['facility_name']}, {pd.Timestamp(pick['start']):%d %b %Y} "
                            f"({int(pick['wells'])} wells)", xaxis_title="days after onset",
                      yaxis=dict(range=[0, 102], title="% of affected wells back"))
    ui.show(ui.style(fig, 380))

st.subheader("Restart laggards")
l = lag[lag["incident"] == pick["incident"]] if st.toggle("Only the selected incident", value=False) else lag
l = l.sort_values("lag_loss_m3", ascending=False)
st.dataframe(l.assign(value=l["lag_loss_m3"] * pm3)[["onset", "facility_name", "uwi", "days_after_peers", "rate_h",
                                                     "lag_loss_m3", "value", "cause"]].rename(columns={
    "onset": "Onset", "facility_name": "Facility", "uwi": "Well", "days_after_peers": "Days after peers back",
    "rate_h": "Healthy rate m³/d", "lag_loss_m3": "Lag loss m³", "value": "C$", "cause": "Cause"}),
    hide_index=True, use_container_width=True, height=320,
    column_config={"Onset": st.column_config.DateColumn(format="YYYY-MM-DD"),
                   "C$": st.column_config.NumberColumn(format="$%.0f"),
                   "Lag loss m³": st.column_config.NumberColumn(format="%.1f"),
                   "Healthy rate m³/d": st.column_config.NumberColumn(format="%.1f")})
rep = lag["uwi"].value_counts()
if (rep >= 2).any():
    st.caption(f"{int((rep >= 2).sum())} wells lagged in two or more incidents: restart problems repeat, so these "
               "wells deserve a standing restart checklist.")
d = info["definition"]
st.caption(f"Definitions fixed before looking at results: sync day = ≥{d['min_wells']} wells and ≥{d['min_share']:.0%} "
           f"of the facility's running wells go down the same day; incidents merge sync days ≤{d['merge_days']} days "
           f"apart; laggard = back ≥{d['lag_days']} days after {d['peer_share']:.0%} of affected peers. The live flag on "
           "the queue uses only data up to that day.")
