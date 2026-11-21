"""Facility restarts: one incident per synchronized facility outage, and the wells that lag the restart."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

st.title("Facility restarts")
ui.intro("When a battery trips and many wells go down together, which wells are still down after the others came back?",
         ["Use the <b>filters</b> to pick facilities, years or a cause.",
          "Each dot on the <b>timeline</b> is one facility incident; bigger = more wells down, orange = some wells lagged. "
          "<b>Click a dot</b> to see how that restart went.",
          "The <b>laggard chart</b> lists the wells that stayed down 3+ days after 75% of their peers: they need a "
          "restart check, not a wait."])
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
inc["start"] = pd.to_datetime(inc["start"])
years = sorted(inc["start"].dt.year.unique())

with ui.filters():
    c1, c2, c3, c4 = st.columns([1.6, 1.2, 1.2, 1])
    facs = c1.multiselect("Facility", sorted(inc["facility_name"].unique()), placeholder="All facilities")
    areas = c2.multiselect("Area", sorted(inc["area"].unique()), placeholder="All areas")
    causes = c3.multiselect("Cause", sorted(inc["main_cause"].unique()), placeholder="All causes")
    min_w = c4.number_input("Min. wells down", 5, int(inc["wells"].max()), 5)
    y0, y1 = st.select_slider("Years", options=years, value=(years[0], years[-1])) if len(years) > 1 else (years[0], years[0])

f = inc[inc["start"].dt.year.between(y0, y1) & (inc["wells"] >= min_w)]
if facs:
    f = f[f["facility_name"].isin(facs)]
if areas:
    f = f[f["area"].isin(areas)]
if causes:
    f = f[f["main_cause"].isin(causes)]
if f.empty:
    st.info("No incidents match these filters.")
    st.stop()
fl = lag[lag["incident"].isin(f["incident"])]
fa = aff[aff["incident"].isin(f["incident"])]
lag_m3 = fl["lag_loss_m3"].sum()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Facility incidents", len(f), f"{f['sync_days'].sum()} outage days", delta_arrow="off", delta_color="off")
m2.metric("Lost oil on the first day", f"{f['onset_lost_oil_m3'].sum():,.0f} m³",
          ui.money(f["onset_lost_oil_m3"].sum() * pm3), delta_arrow="off", delta_color="off")
m3.metric("Restart laggards", len(fl), f"of {len(fa):,} wells taken down", delta_arrow="off", delta_color="off")
m4.metric("Oil lost while lagging", f"{lag_m3:,.0f} m³", ui.money(lag_m3 * pm3), delta_arrow="off", delta_color="off",
          help="Days down after 75% of peers were back × the well's healthy rate: what a timely restart check could "
               "have recovered.")

# ---------------------------------------------------------------- incident timeline (replaces the incidents table)
left, right = st.columns([3, 2])
with left:
    has_lag = f["laggards"] > 0
    fig = go.Figure()
    for mask, name, color in ((~has_lag, "all wells back on time", ui.BLUE), (has_lag, "some wells lagged", ui.ORANGE)):
        g = f[mask]
        fig.add_trace(go.Scatter(
            x=g["start"], y=g["facility_name"], mode="markers", name=name, customdata=g["incident"],
            marker=dict(size=np.clip(np.sqrt(g["wells"]) * 3.2, 8, 40), color=color, opacity=0.8,
                        line=dict(color="white", width=1)),
            text=[f"{w} wells down · {lg} laggard(s) · {c}" for w, lg, c in zip(g["wells"], g["laggards"], g["main_cause"])],
            hovertemplate="%{y}<br>%{x|%d %b %Y}<br>%{text}<extra></extra>"))
    fig.update_layout(title="Facility incidents over time (click one)", yaxis=dict(automargin=True, title=None),
                      xaxis_title=None)
    ev = ui.show(ui.style(fig, max(320, 30 * f["facility_name"].nunique() + 120)), on_select="rerun",
                 selection_mode="points", key="fac_timeline")
    ui.explain("Dot size = number of wells that went down together.")
pick_id = None
if ev and ev.selection and ev.selection.points:
    pick_id = ev.selection.points[0].get("customdata")
pick = f[f["incident"] == pick_id].iloc[0] if pick_id in set(f["incident"]) else \
    f.sort_values(["laggards", "wells"], ascending=False).iloc[0]

with right:
    a = fa[fa["incident"] == pick["incident"]]
    days = a["days_down"]
    xs = np.arange(0, int(np.nanmax(days.fillna(0))) + 2 if days.notna().any() else 10)
    share = [(days <= x).mean() * 100 for x in xs]
    fig = go.Figure(go.Scatter(x=xs, y=share, mode="lines", line=dict(color=ui.BLUE, width=2.5, shape="hv"),
                               name="wells back", hovertemplate="day %{x}: %{y:.0f}% back<extra></extra>"))
    fig.add_hline(y=75, line=dict(color=ui.MUTED, width=1, dash="dot"), annotation_text="75% back")
    if pd.notna(pick["t75"]):
        t75d = (pd.Timestamp(pick["t75"]) - pd.Timestamp(pick["start"])).days
        fig.add_vrect(x0=t75d + 3, x1=max(xs.max(), t75d + 4), fillcolor=ui.CRITICAL, opacity=0.08, line_width=0,
                      annotation_text="laggard zone", annotation_position="top left")
    fig.update_layout(title=f"How the restart went: {pick['facility_name']}, {pd.Timestamp(pick['start']):%d %b %Y}",
                      xaxis_title="days after the trip", yaxis=dict(range=[0, 102], title="% of wells back"))
    ui.show(ui.style(fig, 340))
    ui.explain(f"{int(pick['wells'])} wells went down ({pick['main_cause']}). Wells still down in the red zone are "
               f"laggards: {int(pick['laggards'])} here.")

# ---------------------------------------------------------------- laggards (replaces the laggards table)
st.subheader("Wells that lagged the restart")
if fl.empty:
    st.caption("No laggards in the selected incidents.")
else:
    s1, s2 = st.columns([1, 3])
    only_pick = s1.toggle("Only the selected incident", value=False)
    n = s2.slider("Show the top", 5, max(5, min(40, len(fl))), min(15, len(fl)), help="Wells, ranked by oil lost "
                                                                                       "while they lagged.")
    g = (fl[fl["incident"] == pick["incident"]] if only_pick else fl).nlargest(n, "lag_loss_m3")
    if g.empty:
        st.caption("No laggards in this incident.")
    else:
        fig = ui.hbar([f"{u} · {fac}" for u, fac in zip(g["uwi"], g["facility_name"])], g["lag_loss_m3"],
                      text=[f"{d:.0f} days late · {ui.money(v * pm3)}" for d, v in zip(g["days_after_peers"], g["lag_loss_m3"])],
                      xaxis="oil lost while lagging (m³)", hover="%{y}<br>%{x:.1f} m³<extra></extra>",
                      title="Oil lost while each well waited, most first")
        fig.update_xaxes(range=[0, g["lag_loss_m3"].max() * 1.5])
        ui.show(fig)
        rep = lag["uwi"].value_counts()
        if (rep >= 2).any():
            ui.explain(f"{int((rep >= 2).sum())} wells lagged in two or more incidents. Restart problems repeat, so "
                       "these wells deserve a standing restart checklist.")
d = info["definition"]
with st.expander("How incidents and laggards are defined"):
    st.markdown(f"- **Incident:** at least {d['min_wells']} wells, and at least {d['min_share']:.0%} of the facility's "
                f"running wells, go down on the same day. Days no more than {d['merge_days']} apart are one incident.\n"
                f"- **Laggard:** a well that comes back {d['lag_days']}+ days after {d['peer_share']:.0%} of the other "
                f"wells in its incident are back.\n"
                "- The 'restart check needed' box on Today's queue uses only what was known on that day.\n"
                "- These definitions were fixed before looking at the results.")
