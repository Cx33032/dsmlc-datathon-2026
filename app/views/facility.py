"""Facility restarts: one incident per synchronized facility outage, and the wells that lag the restart."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

st.title("Facility restarts")
ui.intro("When a battery trips and many wells go down together, which wells are still down after the others came back?",
         ["A <b>battery</b> is the facility a group of wells send their oil, water and gas to. When it shuts down "
          "('trips'), its wells have nowhere to flow, so they go down together. The cause chart below shows what the "
          "operators logged as the reason.",
          "Use the <b>filters</b> to pick facilities, years or a cause.",
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

onset_m3 = f["onset_lost_oil_m3"].sum()
m1, m2, m3 = st.columns(3)
m1.metric("Facility incidents", len(f), f"{f['sync_days'].sum()} outage days", delta_arrow="off", delta_color="off")
m2.metric("Restart laggards", len(fl), f"of {len(fa):,} wells taken down", delta_arrow="off", delta_color="off")
m3.metric("Total oil lost", f"{onset_m3 + lag_m3:,.0f} m³", ui.money((onset_m3 + lag_m3) * pm3), delta_arrow="off",
          delta_color="off", help="First day + lagging. Days in between, while the facility itself was being "
                                  "restarted, are not counted.")
st.markdown(f"**Total oil lost = {onset_m3:,.0f} m³ on the day the facilities went down ({ui.mmoney(onset_m3 * pm3)}) "
            f"+ {lag_m3:,.0f} m³ while the laggards waited ({ui.mmoney(lag_m3 * pm3)}) = {onset_m3 + lag_m3:,.0f} m³ "
            f"({ui.mmoney((onset_m3 + lag_m3) * pm3)}).**")
ui.explain("Lagging loss = days a well stayed down after 75% of its peers were back × its usual daily rate: what a "
           "timely restart check could have recovered.")

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

# ---------------------------------------------------------------- why facilities go down
st.subheader("Why did the facilities go down?")
c_l, c_r = st.columns([3, 2])
with c_l:
    by = (f.groupby("main_cause").agg(incidents=("incident", "size"), wells=("wells", "sum"),
                                     m3=("onset_lost_oil_m3", "sum")).reset_index().sort_values("incidents", ascending=False))
    fig = ui.hbar(by["main_cause"], by["incidents"],
                  text=[f"{w:,} wells down · {m:,.0f} m³ first day" for w, m in zip(by["wells"], by["m3"])],
                  xaxis="facility incidents", hover="%{y}: %{x} incidents<extra></extra>",
                  title="Facility incidents by the reason operators logged")
    fig.update_xaxes(range=[0, by["incidents"].max() * 1.9])
    ui.show(fig)
with c_r:
    st.markdown("**How to read the reasons**")
    st.markdown("- The reason is the downtime category logged most often for the affected wells on the first day.\n"
                "- **Facility & Turnarounds**: the battery or plant itself stopped, either an unplanned upset or trip "
                "(e.g. a compressor, treater or tank-level shutdown) or a planned turnaround.\n"
                "- **Power**: a power outage on the lease.\n"
                "- **Pipeline/Flowline**: the line taking fluid away was down.\n"
                "- **Facility - Capacity**: the facility could not take more fluid.")
    st.caption("The data records the category only, not which piece of equipment tripped. Finding the root cause "
               "needs the facility's own alarm or SCADA logs.")

# ---------------------------------------------------------------- laggards (replaces the laggards table)
st.subheader("Wells that lagged the restart")
if fl.empty:
    st.caption("No laggards in the selected incidents.")
else:
    s1, s2 = st.columns([1, 3])
    only_pick = s1.toggle("Only the selected incident", value=False)
    n = s2.slider("Show the top", 5, max(5, min(40, len(fl))), min(15, len(fl)), help="Wells, ranked by oil lost "
                                                                                       "while they lagged.")
    pool = fl[fl["incident"] == pick["incident"]] if only_pick else fl
    g = pool.nlargest(n, "lag_loss_m3").copy()
    if g.empty:
        st.caption("No laggards in this incident.")
    else:
        g["onset"] = pd.to_datetime(g["onset"])
        g["label"] = [f"{u} · {o:%d %b %Y}" for u, o in zip(g["uwi"], g["onset"])]
        g["downhole"] = g["cause"].str.startswith("Downhole")
        tot = pool["lag_loss_m3"].sum()
        fig = ui.hbar(g["label"], g["lag_loss_m3"], colors=[ui.ORANGE if d else ui.BLUE for d in g["downhole"]],
                      text=[f"{d:.0f} days late · {ui.money(v * pm3)} · {c}"
                            for d, v, c in zip(g["days_after_peers"], g["lag_loss_m3"], g["cause"])],
                      xaxis="oil lost while lagging (m³)", hover="%{y}<br>%{x:.1f} m³<extra></extra>",
                      title=f"Oil lost while each well waited (click a bar). Total: {tot:,.0f} m³ = "
                            f"{ui.money(tot * pm3)} across {len(pool)} laggards"
                            + (f", top {len(g)} shown" if len(g) < len(pool) else ""))
        fig.update_xaxes(range=[0, g["lag_loss_m3"].max() * 1.9])
        lev = ui.show(fig, on_select="rerun", selection_mode="points", key="fac_lag")
        ui.explain("Orange = the well logged its own downhole problem (rods, pump, tubing), so it likely broke during "
                   "the shutdown and needs a rig. Blue = nothing wrong was logged on the well, so a restart check "
                   "could have brought it back sooner.")
        sel = lev.selection.points[0].get("y") if lev and lev.selection and lev.selection.points else None
        r = g[g["label"] == sel].iloc[0] if sel in set(g["label"]) else g.iloc[0]
        ri = inc[inc["incident"] == r["incident"]].iloc[0]
        t75 = pd.Timestamp(r["t75"])
        back = (f"came back on **{pd.Timestamp(r['restart']):%d %b %Y}**, {r['days_after_peers']:.0f} days after that"
                if pd.notna(r["restart"]) else f"was still down {r['days_after_peers']:.0f} days after that")
        why = ("It logged its own **downhole** problem, so it most likely failed during the shutdown or the restart. "
               "That needs a rig, and the sooner it is found the sooner the rig is booked." if r["downhole"] else
               "Nothing wrong with the well itself was logged, so a restart check (power, valves, pump start-up) "
               f"around {t75 + pd.Timedelta(days=3):%d %b} could have brought it back sooner.")
        with st.container(border=True):
            st.markdown(f"**Why {r['uwi']} is on this list**" + ("" if sel else " (the top bar; click another to switch)"))
            st.markdown(
                f"- It went down on **{r['onset']:%d %b %Y}** with {int(ri['wells']) - 1} other wells at "
                f"**{r['facility_name']}** ({ri['main_cause']}).\n"
                f"- By **{t75:%d %b %Y}** ({(t75 - pd.Timestamp(ri['start'])).days} days in), 75% of those wells were "
                f"running again. This well {back}.\n"
                f"- At its usual rate of **{r['rate_h']:.1f} m³/day**, those {r['days_after_peers']:.0f} days cost "
                f"**{r['lag_loss_m3']:,.1f} m³** ({ui.mmoney(r['lag_loss_m3'] * pm3)}).\n"
                f"- Its own logged downtime reason: **{r['cause']}**. {why}")
            if st.button("Open well card", icon=":material/arrow_forward:", key="fac_open"):
                ui.open_well(str(r["uwi"]))
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
