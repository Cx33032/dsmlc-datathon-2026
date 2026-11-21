"""Facility restarts: one incident per synchronized facility outage, and the wells that lag the restart."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

if not ui.require("facility_incidents.parquet", "facility_laggards.parquet", "facility_affected.parquet",
                  "facility_info.json"):
    st.stop()
info = ui.art("facility_info.json")
d = info["definition"]
top_slot = ui.header(
    "Which wells stay down after their facility restarts?",
    how=["Read the sentence under the title. It names the facility whose wells lost the most oil while they waited.",
         "Use the bar chart of lagging wells to plan restart checks, most lost oil first.",
         "Pick an incident in the list, or click a dot on the timeline, to see how that restart went.",
         "Use the filters to show one facility, area, cause or range of years."],
    terms=["Facility", "UWI", "m³", "C$"],
    extra_terms={"Incident": f"At least {d['min_wells']} wells, and at least {d['min_share']:.0%} of the facility's "
                             f"running wells, go down on the same day. Days no more than {d['merge_days']} apart "
                             "count as one incident.",
                 "Laggard": f"A well that comes back {d['lag_days']} or more days after {d['peer_share']:.0%} of the "
                            "other wells in its incident are back. It needs a restart check, not more waiting."})
inc = ui.art("facility_incidents.parquet")
lag = ui.art("facility_laggards.parquet")
aff = ui.art("facility_affected.parquet")
if inc is None or inc.empty:
    ui.empty("This data has no facility incidents (many wells at one facility going down on the same day).",
             "Switch the data mode in the sidebar to check the other data set.")
    st.stop()
pm3 = ui.price_m3()
inc["start"] = pd.to_datetime(inc["start"])
years = sorted(inc["start"].dt.year.unique())

with ui.filters(reset_keys=["f_fac", "f_area", "f_cause", "f_min", "f_years"]):
    c1, c2, c3, c4 = st.columns([1.6, 1.2, 1.2, 1])
    facs = c1.multiselect("Facility", sorted(inc["facility_name"].unique()), placeholder="All facilities", key="f_fac")
    areas = c2.multiselect("Area", sorted(inc["area"].unique()), placeholder="All areas", key="f_area")
    causes = c3.multiselect("Cause", sorted(inc["main_cause"].unique()), placeholder="All causes", key="f_cause")
    min_w = c4.number_input("At least this many wells down", 5, int(inc["wells"].max()), 5, key="f_min")
    y0, y1 = (st.select_slider("Years", options=years, value=(years[0], years[-1]), key="f_years")
              if len(years) > 1 else (years[0], years[0]))

f = inc[inc["start"].dt.year.between(y0, y1) & (inc["wells"] >= min_w)]
if facs:
    f = f[f["facility_name"].isin(facs)]
if areas:
    f = f[f["area"].isin(areas)]
if causes:
    f = f[f["main_cause"].isin(causes)]
if f.empty:
    ui.empty("No facility incidents match these filters.",
             "Lower the number of wells down, widen the years, or press Reset filters.")
    st.stop()
fl = lag[lag["incident"].isin(f["incident"])]
fa = aff[aff["incident"].isin(f["incident"])]
lag_m3 = fl["lag_loss_m3"].sum()

# ---------------------------------------------------------------- the answer
if fl.empty:
    ui.summary(top_slot, f"In these {len(f)} facility incidents, every well came back with the others. "
                         "No well needs a restart check.")
else:
    by_fac = fl.groupby("facility_name")["lag_loss_m3"].agg(["sum", "size"]).sort_values("sum", ascending=False)
    fac1, (fac1_m3, fac1_n) = by_fac.index[0], by_fac.iloc[0]
    ui.summary(top_slot, f"<b>{len(fl)} wells</b> stayed down long after their facility restarted and lost "
                         f"<b>{lag_m3:,.0f} m³</b> ({ui.money(lag_m3 * pm3)}) while they waited. "
                         f"Check <b>{fac1}</b> first: its {int(fac1_n)} lagging wells lost {fac1_m3:,.0f} m³, "
                         "the most of any facility.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Facility incidents", len(f), f"{f['sync_days'].sum()} outage days", delta_arrow="off", delta_color="off")
m2.metric("Lost oil on the first day", f"{f['onset_lost_oil_m3'].sum():,.0f} m³",
          ui.money(f["onset_lost_oil_m3"].sum() * pm3), delta_arrow="off", delta_color="off")
m3.metric("Lagging wells", len(fl), f"of {len(fa):,} wells taken down", delta_arrow="off", delta_color="off")
m4.metric("Oil lost while lagging", f"{lag_m3:,.0f} m³", ui.money(lag_m3 * pm3), delta_arrow="off", delta_color="off",
          help="Days down after 75% of the other wells were back × the well's healthy rate. A timely restart check "
               "could have recovered this oil.")

# ---------------------------------------------------------------- laggards: the action list
st.subheader("Which wells to check first")
if fl.empty:
    st.caption("No well lagged in the selected incidents.")
else:
    s1, s2 = st.columns([1, 3])
    only_pick = s1.toggle("Show only the selected incident", value=False, key="f_only")
    n = s2.slider("Number of wells to show", 5, max(5, min(40, len(fl))), min(15, len(fl)), key="f_n",
                  help="Wells, ranked by oil lost while they lagged.")
pick_holder = st.container()

# ---------------------------------------------------------------- incident timeline + restart curve
st.subheader("How each restart went")
order = f.sort_values(["laggards", "wells"], ascending=False)
inc_ids = list(order["incident"])
inc_label = {r.incident: f"{r.facility_name}, {pd.Timestamp(r.start):%d %b %Y}: {r.wells} wells down, "
                         f"{r.laggards} lagged" for r in order.itertuples()}
if st.session_state.get("f_pick") not in inc_ids:
    st.session_state["f_pick"] = inc_ids[0]


def _from_chart():
    pts = st.session_state["fac_timeline"].selection.points
    if pts and pts[0].get("customdata") in inc_ids:
        st.session_state["f_pick"] = pts[0]["customdata"]


st.selectbox("Incident", inc_ids, key="f_pick", format_func=inc_label.get,
             help="Sorted by the number of lagging wells. You can also click a dot on the timeline.")
pick = f[f["incident"] == st.session_state["f_pick"]].iloc[0]

left, right = st.columns([3, 2])
with left:
    has_lag = f["laggards"] > 0
    fig = go.Figure()
    for mask, name, color in ((~has_lag, "all wells back on time", ui.GRAY), (has_lag, "some wells lagged", ui.BLUE)):
        g = f[mask]
        fig.add_trace(go.Scatter(
            x=g["start"], y=g["facility_name"], mode="markers", name=name, customdata=g["incident"],
            marker=dict(size=np.clip(np.sqrt(g["wells"]) * 3.2, 8, 40), color=color, opacity=0.8,
                        line=dict(color="white", width=1)),
            text=[f"{w} wells down · {lg} lagged · {c}" for w, lg, c in zip(g["wells"], g["laggards"], g["main_cause"])],
            hovertemplate="%{y}<br>%{x|%d %b %Y}<br>%{text}<extra></extra>"))
    fig.update_layout(title=f"{int(has_lag.sum())} of {len(f)} incidents left wells lagging (blue)",
                      yaxis=dict(automargin=True, title="facility"), xaxis_title="date the facility went down")
    ui.show(ui.style(fig, max(320, 30 * f["facility_name"].nunique() + 120)), on_select=_from_chart,
            selection_mode="points", key="fac_timeline")
    ui.explain("Each dot is one incident. Bigger dot = more wells went down together. Click a dot to see its restart.")

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
                      annotation_text="lagging", annotation_position="top left")
    fig.update_layout(title=f"{pick['facility_name']}, {pd.Timestamp(pick['start']):%d %b %Y}: "
                            f"{int(pick['laggards'])} of {int(pick['wells'])} wells lagged",
                      xaxis_title="days after the facility went down", yaxis=dict(range=[0, 102], title="wells back (%)"))
    ui.show(ui.style(fig, 340))
    ui.explain(f"Cause: {pick['main_cause']}. Wells still down in the red zone are lagging.")

# ---------------------------------------------------------------- laggards chart (placed above the timeline)
if not fl.empty:
    with pick_holder:
        g = (fl[fl["incident"] == pick["incident"]] if only_pick else fl).nlargest(n, "lag_loss_m3")
        if g.empty:
            st.caption("No well lagged in the selected incident. Turn off 'Show only the selected incident'.")
        else:
            fig = ui.hbar([f"{u} · {fac}" for u, fac in zip(g["uwi"], g["facility_name"])], g["lag_loss_m3"],
                          text=[f"{d_:.0f} days late · {ui.money(v * pm3)}" for d_, v in
                                zip(g["days_after_peers"], g["lag_loss_m3"])],
                          xaxis="oil lost while lagging (m³)", hover="%{y}<br>%{x:.1f} m³<extra></extra>",
                          title=f"{g.iloc[0]['uwi']} lost the most oil while it waited: "
                                f"{g.iloc[0]['lag_loss_m3']:,.0f} m³")
            fig.update_xaxes(range=[0, g["lag_loss_m3"].max() * 1.5])
            ui.show(fig)
            rep = lag["uwi"].value_counts()
            if (rep >= 2).any():
                ui.explain(f"{int((rep >= 2).sum())} wells lagged in two or more incidents. Restart problems repeat, "
                           "so give these wells a standing restart checklist.")

with st.expander("How incidents and lagging wells are defined"):
    st.markdown(f"- **Incident:** at least {d['min_wells']} wells, and at least {d['min_share']:.0%} of the facility's "
                f"running wells, go down on the same day. Days no more than {d['merge_days']} apart are one incident.\n"
                f"- **Lagging well:** a well that comes back {d['lag_days']} or more days after {d['peer_share']:.0%} "
                "of the other wells in its incident are back.\n"
                "- The 'Restart check needed' box on Today's queue uses only what was known on that day.\n"
                "- These definitions were fixed before looking at the results.")
