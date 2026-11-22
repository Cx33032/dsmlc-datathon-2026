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
    how=["Read the sentence under the title. It names the facility whose wells lost the most oil that a restart "
         "check could have recovered.",
         "Use the bar chart of lagging wells to plan restart checks. Blue bars are wells with nothing wrong logged, "
         "so a restart check could bring them back. Orange bars logged a downhole problem and need a rig.",
         "Click a bar, or pick a well in the list under the chart, to see why that well is on the list.",
         "Pick an incident, or click a dot on the timeline, to see how that restart went.",
         "Use the filters to show one facility, area, cause or range of years."],
    terms=["Facility", "UWI", "m³", "C$"],
    extra_terms={"Battery": "The facility a group of wells send their oil, water and gas to.",
                 "Trip": "A facility shutdown. When a battery trips, its wells have nowhere to flow, so they go down "
                         "together.",
                 "Incident": f"At least {d['min_wells']} wells, and at least {d['min_share']:.0%} of the facility's "
                             f"running wells, go down on the same day. Days no more than {d['merge_days']} apart "
                             "count as one incident.",
                 "Lagging well (laggard)": f"A well that comes back {d['lag_days']} or more days after "
                                           f"{d['peer_share']:.0%} of the other wells in its incident are back."})
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
onset_m3 = f["onset_lost_oil_m3"].sum()

# ---------------------------------------------------------------- the answer
if fl.empty:
    ui.summary(top_slot, f"In these {len(f)} facility incidents, every well came back with the others. "
                         "No well needs a restart check.")
else:
    rec = fl[~fl["cause"].str.startswith("Downhole")]   # nothing wrong logged on the well itself
    text = (f"<b>{len(fl)} wells</b> stayed down long after their facility restarted and lost <b>{lag_m3:,.0f} m³</b> "
            f"({ui.money(lag_m3 * pm3)}) while they waited. ")
    if len(rec):
        by_fac = rec.groupby("facility_name")["lag_loss_m3"].agg(["sum", "size"]).sort_values("sum", ascending=False)
        fac1, (fac1_m3, fac1_n) = by_fac.index[0], by_fac.iloc[0]
        text += (f"{rec['lag_loss_m3'].sum():,.0f} m³ of that was on wells with nothing wrong logged, which a restart "
                 f"check could have recovered. Check <b>{fac1}</b> first: {int(fac1_n)} of its wells lost "
                 f"{fac1_m3:,.0f} m³ that way, the most of any facility.")
    ui.summary(top_slot, text)

m1, m2, m3 = st.columns(3)
m1.metric("Facility incidents", len(f), f"{f['sync_days'].sum()} outage days", delta_arrow="off", delta_color="off")
m2.metric("Lagging wells", len(fl), f"of {len(fa):,} wells taken down", delta_arrow="off", delta_color="off")
m3.metric("Total oil lost", f"{onset_m3 + lag_m3:,.0f} m³", ui.money((onset_m3 + lag_m3) * pm3), delta_arrow="off",
          delta_color="off", help="First day + lagging. Days in between, while the facility itself was being "
                                  "restarted, are not counted.")
ui.explain(f"Total oil lost = {onset_m3:,.0f} m³ on the day the facilities went down ({ui.mmoney(onset_m3 * pm3)}) "
           f"+ {lag_m3:,.0f} m³ while the lagging wells waited ({ui.mmoney(lag_m3 * pm3)}) = "
           f"**{onset_m3 + lag_m3:,.0f} m³ ({ui.mmoney((onset_m3 + lag_m3) * pm3)})**.\n\n"
           "Lagging loss = days a well stayed down after 75% of the other wells were back × its usual daily rate.",
           label="How the total is worked out")

# ---------------------------------------------------------------- the incident to look at (set here, shown below)
order = f.sort_values(["laggards", "wells"], ascending=False)
inc_ids = list(order["incident"])
inc_label = {r.incident: f"{r.facility_name}, {pd.Timestamp(r.start):%d %b %Y}: {r.wells} wells down, "
                         f"{r.laggards} lagged" for r in order.itertuples()}
if st.session_state.get("f_pick") not in inc_ids:
    st.session_state["f_pick"] = inc_ids[0]
pick = f[f["incident"] == st.session_state["f_pick"]].iloc[0]

# ---------------------------------------------------------------- lagging wells: the action list
st.header("Which wells to check first")
if fl.empty:
    st.caption("No well lagged in the selected incidents.")
else:
    s1, s2 = st.columns([1, 3])
    only_pick = s1.toggle("Show only the selected incident", value=False, key="f_only")
    n = s2.slider("Number of wells to show", 5, max(5, min(40, len(fl))), min(15, len(fl)), key="f_n",
                  help="Wells, ranked by oil lost while they lagged.")
    pool = fl[fl["incident"] == pick["incident"]] if only_pick else fl
    g = pool.nlargest(n, "lag_loss_m3").copy()
    if g.empty:
        st.caption("No well lagged in the selected incident. Turn off 'Show only the selected incident'.")
    else:
        g["onset"] = pd.to_datetime(g["onset"])
        g["label"] = [f"{u} · {o:%d %b %Y}" for u, o in zip(g["uwi"], g["onset"])]
        g["downhole"] = g["cause"].str.startswith("Downhole")
        tot = pool["lag_loss_m3"].sum()
        dh = pool["cause"].str.startswith("Downhole")
        dh_m3, rs_m3 = pool.loc[dh, "lag_loss_m3"].sum(), pool.loc[~dh, "lag_loss_m3"].sum()
        t1, t2, t3 = st.columns(3)
        t1.metric("Total lost while lagging", f"{tot:,.0f} m³", f"{ui.money(tot * pm3)} · {len(pool)} wells",
                  delta_arrow="off", delta_color="off",
                  help=f"{pool['days_after_peers'].sum():,.0f} well-days down after 75% of the other wells were back, "
                       "× each well's usual daily rate." + (" All lagging wells in the selection, not only the bars "
                                                           "shown." if len(g) < len(pool) else ""))
        t2.metric("Recoverable by a restart check", f"{rs_m3:,.0f} m³", f"{ui.money(rs_m3 * pm3)} · {int((~dh).sum())} wells",
                  delta_arrow="off", delta_color="off",
                  help="Blue bars: nothing wrong was logged on the well, so a timely restart check could have "
                       "recovered this oil.")
        t3.metric("Downhole (needed a rig)", f"{dh_m3:,.0f} m³", f"{ui.money(dh_m3 * pm3)} · {int(dh.sum())} wells",
                  delta_arrow="off", delta_color="off", help="Orange bars: the well logged its own downhole problem.")
        fig = ui.hbar(g["label"], g["lag_loss_m3"], colors=[ui.ORANGE if x else ui.BLUE for x in g["downhole"]],
                      text=[f"{dd:.0f} days late · {ui.money(v * pm3)} · {c}"
                            for dd, v, c in zip(g["days_after_peers"], g["lag_loss_m3"], g["cause"])],
                      xaxis="oil lost while lagging (m³)", hover="%{y}<br>%{x:.1f} m³<extra></extra>",
                      title=f"{g.iloc[0]['uwi']} lost the most oil while it waited: {g.iloc[0]['lag_loss_m3']:,.0f} m³"
                            + (f" (top {len(g)} of {len(pool)} shown)" if len(g) < len(pool) else ""))
        fig.update_xaxes(range=[0, g["lag_loss_m3"].max() * 1.9])
        labels = list(g["label"])

        def _from_lag_chart():
            pts = st.session_state["fac_lag"].selection.points
            if pts and pts[0].get("y") in labels:
                st.session_state["f_lag_pick"] = pts[0]["y"]

        ui.show(fig, on_select=_from_lag_chart, selection_mode="points", key="fac_lag")
        ui.explain("Blue = nothing wrong was logged on the well, so a restart check could have brought it back sooner. "
                   "Orange = the well logged its own downhole problem (rods, pump, tubing), so it likely broke during "
                   "the shutdown and needs a rig.")
        if st.session_state.get("f_lag_pick") not in labels:
            st.session_state["f_lag_pick"] = labels[0]
        st.selectbox("Explain why this well is on the list", labels, key="f_lag_pick",
                     help="You can also click a bar in the chart.")
        r = g[g["label"] == st.session_state["f_lag_pick"]].iloc[0]
        ri = inc[inc["incident"] == r["incident"]].iloc[0]
        t75 = pd.Timestamp(r["t75"])
        back = (f"came back on **{pd.Timestamp(r['restart']):%d %b %Y}**, {r['days_after_peers']:.0f} days after that"
                if pd.notna(r["restart"]) else f"was still down {r['days_after_peers']:.0f} days after that")
        why = ("It logged its own **downhole** problem, so it most likely failed during the shutdown or the restart. "
               "That needs a rig. The sooner the crew finds it, the sooner they can book the rig." if r["downhole"] else
               "Nothing wrong with the well itself was logged, so a restart check (power, valves, pump start-up) "
               f"around {t75 + pd.Timedelta(days=3):%d %b} could have brought it back sooner.")
        with st.expander(f"Why {r['uwi']} is on this list"):
            st.markdown(
                f"- It went down on **{r['onset']:%d %b %Y}** with {int(ri['wells']) - 1} other wells at "
                f"**{r['facility_name']}** ({ri['main_cause']}).\n"
                f"- By **{t75:%d %b %Y}** ({(t75 - pd.Timestamp(ri['start'])).days} days in), 75% of those wells were "
                f"running again. This well {back}.\n"
                f"- At its usual rate of **{r['rate_h']:.1f} m³/day**, those {r['days_after_peers']:.0f} days cost "
                f"**{r['lag_loss_m3']:,.1f} m³** ({ui.mmoney(r['lag_loss_m3'] * pm3)}).\n"
                f"- Its own logged downtime reason: **{r['cause']}**. {why}")
        if st.button(f"Open the well card for {r['uwi']}", icon=":material/arrow_forward:", key="fac_open"):
            ui.open_well(str(r["uwi"]))
        rep = lag["uwi"].value_counts()
        if (rep >= 2).any():
            ui.explain(f"{int((rep >= 2).sum())} wells lagged in two or more incidents. Restart problems repeat, so "
                       "give these wells a standing restart checklist.")

# ---------------------------------------------------------------- incident timeline + restart curve
st.header("How each restart went")


def _from_timeline():
    pts = st.session_state["fac_timeline"].selection.points
    if pts and pts[0].get("customdata") in inc_ids:
        st.session_state["f_pick"] = pts[0]["customdata"]


st.selectbox("Incident", inc_ids, key="f_pick", format_func=inc_label.get,
             help="Sorted by the number of lagging wells. You can also click a dot on the timeline.")
left, right = st.columns([3, 2])
with left:
    has_lag = f["laggards"] > 0
    fig = go.Figure()
    for mask, name, color in ((~has_lag, "all wells back on time", ui.BLUE), (has_lag, "some wells lagged", ui.ORANGE)):
        gg = f[mask]
        fig.add_trace(go.Scatter(
            x=gg["start"], y=gg["facility_name"], mode="markers", name=name, customdata=gg["incident"],
            marker=dict(size=np.clip(np.sqrt(gg["wells"]) * 3.2, 8, 40), color=color, opacity=0.8,
                        line=dict(color="white", width=1)),
            text=[f"{w} wells down · {lg} lagged · {c}" for w, lg, c in zip(gg["wells"], gg["laggards"], gg["main_cause"])],
            hovertemplate="%{y}<br>%{x|%d %b %Y}<br>%{text}<extra></extra>"))
    fig.update_layout(title=f"{int(has_lag.sum())} of {len(f)} incidents left wells lagging (orange)",
                      yaxis=dict(automargin=True, title="facility"), xaxis_title="date the facility went down")
    ui.show(ui.style(fig, max(320, 30 * f["facility_name"].nunique() + 120)), on_select=_from_timeline,
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

# ---------------------------------------------------------------- why facilities go down
st.header("Why did the facilities go down?")
by = (f.groupby("main_cause").agg(incidents=("incident", "size"), wells=("wells", "sum"),
                                 m3=("onset_lost_oil_m3", "sum")).reset_index().sort_values("incidents", ascending=False))
fig = ui.hbar(by["main_cause"], by["incidents"],
              text=[f"{w:,} wells down · {m:,.0f} m³ first day" for w, m in zip(by["wells"], by["m3"])],
              xaxis="facility incidents", hover="%{y}: %{x} incidents<extra></extra>",
              title=f"{by.iloc[0]['main_cause']} is the most common logged reason")
fig.update_xaxes(range=[0, by["incidents"].max() * 1.9])
ui.show(fig)
ui.explain("- The reason is the downtime category logged most often for the affected wells on the first day.\n"
           "- **Facility & Turnarounds**: the battery or plant itself stopped. This is either an unplanned upset "
           "or trip (for example a compressor, treater or tank-level shutdown) or a planned turnaround.\n"
           "- **Power**: a power outage on the lease.\n"
           "- **Pipeline/Flowline**: the line taking fluid away was down.\n"
           "- **Facility - Capacity**: the facility could not take more fluid.\n\n"
           "The data records the category only, not which piece of equipment tripped. To find the root cause, "
           "use the facility's own alarm and control-system logs.", label="How to read the reasons")

with st.expander("How incidents and lagging wells are defined"):
    st.markdown(f"- **Incident:** at least {d['min_wells']} wells, and at least {d['min_share']:.0%} of the facility's "
                f"running wells, go down on the same day. Days no more than {d['merge_days']} apart are one incident.\n"
                f"- **Lagging well:** a well that comes back {d['lag_days']} or more days after {d['peer_share']:.0%} "
                "of the other wells in its incident are back.\n"
                "- The 'Restart check needed' box on Today's queue uses only what was known on that day.\n"
                "- These definitions were fixed before looking at the results.")
