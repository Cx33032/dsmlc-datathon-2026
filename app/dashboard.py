"""Operator dashboard - Topic 2 (where oil is lost) + Topic 1 (which wells fail next).

A page of the app (app/app.py). The data mode and the oil price come from the shared sidebar (app/ui.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))
from src.config import M3_TO_BBL  # noqa: E402
from src.data import FAILURE_CATEGORIES  # noqa: E402
import ui  # noqa: E402

OUT = ui.out_dir()

# One design system: colours and chart style come from ui (app/ui.py).
from ui import AQUA, BLUE, CRITICAL, GRAY, MUTED, ORANGE, SEQ_BLUE, YELLOW, show, style  # noqa: E402

GROUP_COLORS = {"Equipment failure": BLUE, "Facility & capacity": ORANGE,
                "Other avoidable": AQUA, "Uncoded": YELLOW}


# ---------------------------------------------------------------- data
@st.cache_data
def load(stamp: float):  # stamp = outputs mtime, so a pipeline rerun refreshes the cache
    need = ["loss_monthly", "prod_monthly", "loss_by_well_year", "wells", "well_year", "risk_scores",
            "watchlist", "test_events", "events"]
    d = {n: pd.read_parquet(OUT / f"{n}.parquet") for n in need}
    for n in ("metrics", "pr_curve", "importance", "stale_tags"):
        d[n] = pd.read_csv(OUT / f"{n}.csv")
    for n in ("model_info", "loss_summary", "loss_validation", "event_validation", "dq_report"):
        d[n] = json.loads((OUT / f"{n}.json").read_text())
    for n in ("loss_monthly", "loss_by_well_year", "wells", "well_year", "risk_scores", "watchlist"):
        for c in d[n].select_dtypes("category").columns:
            d[n][c] = d[n][c].astype(str)
    return d


@st.cache_data
def well_daily(uwi: str, stamp: float) -> pd.DataFrame:
    return pd.read_parquet(OUT / "well_daily.parquet", filters=[("uwi", "==", uwi)])


def group_of(cat: str) -> str:
    if cat in FAILURE_CATEGORIES:
        return "Equipment failure"
    if cat.startswith("Facility"):
        return "Facility & capacity"
    if cat == "Uncoded":
        return "Uncoded"
    return "Other avoidable"


if not (OUT / "risk_scores.parquet").exists():
    st.warning("This page has no data yet. To build it, run `python run_pipeline.py`.")
    st.stop()
STAMP = (OUT / "model_info.json").stat().st_mtime + hash(str(OUT)) % 1000
D = load(STAMP)
lm = D["loss_monthly"].copy()
lm["group"] = lm["loss_category"].map(group_of)
avoid = lm[lm["loss_category"] != "Shut-in (Uneconomic/LTSI)"]

# ---------------------------------------------------------------- page header + filters
top_slot = ui.header(
    "Where is oil lost, and which wells may fail next?",
    how=["Read the sentence under the title for the last 12 months.",
         "Open the Risk watchlist tab for the running wells most likely to fail in the next 14 days.",
         "Use the other tabs for the causes of lost oil, one well's history, how good the model is, and data quality.",
         "Pick areas and years in the filter bar. Every tab follows them."],
    terms=["Avoidable loss", "Watchlist", "bbl", "m³", "C$", "UWI", "Pump efficiency"],
    extra_terms={"WATCH and ALARM": "Risk levels on the watchlist. WATCH = the top 5% of 2024 validation scores, "
                                    "ALARM = the top 2%.",
                 "K": "The number of wells on the daily watchlist.",
                 "Precision": "The share of listed wells that really had a failure outage within 14 days.",
                 "Recall": "The share of all failure outages that the list flagged in advance."})
areas = sorted(lm["field_operating_area"].dropna().unique())
years = sorted(avoid["month"].dt.year.unique())
with ui.filters(reset_keys=["m_areas", "m_years"]):
    fc1, fc2 = st.columns([1.3, 2])
    sel_areas = fc1.multiselect("Areas", areas, placeholder="All areas", key="m_areas")
    y0, y1 = fc2.select_slider("Years (for the loss and failure charts)", options=years, value=(years[0], years[-1]),
                               key="m_years")
netback = ui.price_bbl()
cad_per_m3 = netback * M3_TO_BBL


MAX_DATE = D["risk_scores"]["production_date"].max()


def month_days(m: pd.Series) -> pd.Series:
    """Days observed in each month (the last month of data is partial)."""
    end = (m + pd.offsets.MonthEnd(0)).clip(upper=MAX_DATE)
    return (end - m).dt.days + 1


def area_filter(df: pd.DataFrame, col: str = "field_operating_area") -> pd.DataFrame:
    return df[df[col].isin(sel_areas)] if sel_areas else df


tabs = st.tabs(["Overview", "Where oil is lost", "Risk watchlist", "Well drill-down", "Model & value", "Data quality"])

# ================================================================= OVERVIEW
with tabs[0]:
    a = area_filter(avoid)
    pm = area_filter(D["prod_monthly"])
    last_m = a["month"].max()
    yr_ago = last_m - pd.DateOffset(months=11)
    last12 = a[a["month"] >= yr_ago]
    fail12 = last12[last12["loss_category"].isin(FAILURE_CATEGORIES)]["est_lost_oil_m3"].sum()
    prod = pm.groupby("month", as_index=False).agg(oil_m3=("oil_m3", "sum"))
    prod["bbl_d"] = prod["oil_m3"] * M3_TO_BBL / month_days(prod["month"])
    recent = prod[prod["month"] >= yr_ago]["bbl_d"].mean()
    prior = prod[(prod["month"] < yr_ago) & (prod["month"] >= yr_ago - pd.DateOffset(months=12))]["bbl_d"].mean()
    ev = area_filter(D["events"].merge(D["wells"][["uwi", "field_operating_area"]], on="uwi", how="left"))
    ev12 = ev[ev["onset_date"] >= yr_ago]

    # short labels and compact values so the four tiles fit side by side without truncation
    lost12 = last12["est_lost_oil_m3"].sum()
    st.caption(f"Last 12 months (to {MAX_DATE:%b %Y})")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Oil rate, bbl/d", f"{recent:,.0f}", f"{100 * (recent / prior - 1):+.1f}% vs prior yr",
              help="Mean daily oil rate over the last 12 months, compared with the 12 months before.")
    ui.summary(top_slot, f"In the 12 months to {MAX_DATE:%b %Y}, avoidable downtime cost <b>{lost12 * M3_TO_BBL / 1e3:,.0f}k "
                         f"bbl</b> of oil (≈ C${lost12 * cad_per_m3 / 1e6:,.1f}M). <b>{100 * fail12 / max(lost12, 1):.0f}%</b> "
                         "of it came from rod, pump and tubing failures. The Risk watchlist tab lists the running wells "
                         "most likely to fail in the next 14 days.")
    c2.metric("Avoidable loss, bbl", f"{lost12 * M3_TO_BBL / 1e3:,.0f}k", f"≈ C${lost12 * cad_per_m3 / 1e6:,.1f}M",
              delta_color="off", delta_arrow="off",
              help=f"Estimated avoidable lost oil: {lost12 * M3_TO_BBL:,.0f} bbl, valued at the netback in the sidebar.")
    c3.metric("From failures, bbl", f"{fail12 * M3_TO_BBL / 1e3:,.0f}k",
              f"{100 * fail12 / max(lost12, 1):.0f}% of avoidable", delta_color="off", delta_arrow="off",
              help=f"Lost oil from rod, pump and tubing failures: {fail12 * M3_TO_BBL:,.0f} bbl.")
    c4.metric("Failure events", f"{len(ev12):,}", f"C${ev12['job_cost'].sum() / 1e6:,.1f}M repairs",
              delta_color="off", delta_arrow="off",
              help="Rod/pump/tubing repair events and their field-estimated job cost.")

    left, right = st.columns(2)
    with left:
        fig = go.Figure(go.Scatter(x=prod["month"], y=prod["bbl_d"], mode="lines", line=dict(color=BLUE, width=2),
                                   hovertemplate="%{x|%b %Y}<br>%{y:,.0f} bbl/d<extra></extra>"))
        chg = 100 * (recent / prior - 1)
        fig.update_layout(title=f"Oil rate is {'down' if chg < 0 else 'up'} {abs(chg):.1f}% on the year before",
                          xaxis_title="month", yaxis_title="oil rate (bbl/d)")
        show(style(fig, 360))
    with right:
        g = a.groupby(["month", "group"], as_index=False)["est_lost_oil_m3"].sum()
        g["bbl_d"] = g["est_lost_oil_m3"] * M3_TO_BBL / month_days(g["month"])
        fig = px.bar(g, x="month", y="bbl_d", color="group", color_discrete_map=GROUP_COLORS,
                     category_orders={"group": list(GROUP_COLORS)},
                     labels={"bbl_d": "lost oil (bbl/d)", "month": "month", "group": ""})
        fig.update_traces(marker_line_width=0, hovertemplate="%{x|%b %Y}<br>%{y:,.0f} bbl/d<extra>%{fullData.name}</extra>")
        eq = 100 * g.loc[g["group"] == "Equipment failure", "bbl_d"].sum() / max(g["bbl_d"].sum(), 1e-9)
        fig.update_layout(title=f"Equipment failures cause about {eq:.0f}% of avoidable lost oil since "
                                f"{g['month'].min():%b %Y}",
                          bargap=0.15, xaxis_title="month", yaxis_title="lost oil (bbl/d)")
        show(style(fig, 360))
    st.caption("Equipment failure = rod, pump and tubing/packer failures. "
               "Lost oil = the well's trailing 30-day median oil rate × hours down / 24, per downtime day. "
               f"Validated against operator-reported lost oil: totals within "
               f"{abs(1 - D['loss_validation']['sum_est_over_sum_reported']) * 100:.0f}%, rank correlation "
               f"{D['loss_validation']['spearman_r']:.2f}. Economic long-term shut-ins are excluded as a business "
               "decision, not a loss.")

# ================================================================= LOSSES
with tabs[1]:
    a = area_filter(avoid)
    a = a[a["month"].dt.year.between(y0, y1)]
    cat = a.groupby("loss_category", as_index=False).agg(m3=("est_lost_oil_m3", "sum"), hours=("hours_down", "sum"))
    cat = cat.sort_values("m3")
    cat["bbl"] = cat["m3"] * M3_TO_BBL
    cat["share"] = 100 * cat["m3"] / cat["m3"].sum()
    cat["color"] = np.where(cat["loss_category"].isin(FAILURE_CATEGORIES), BLUE, GRAY)
    left, right = st.columns([1, 1])
    with left:
        fig = go.Figure(go.Bar(y=cat["loss_category"], x=cat["bbl"], orientation="h", marker_color=cat["color"],
                               customdata=np.c_[cat["share"], cat["hours"], cat["m3"] * cad_per_m3],
                               text=[f"{s:.0f}%" for s in cat["share"]], textposition="outside",
                               hovertemplate="<b>%{y}</b><br>%{x:,.0f} bbl (%{customdata[0]:.1f}%)<br>"
                                             "%{customdata[1]:,.0f} well-hours down<br>"
                                             "≈ $%{customdata[2]:,.0f}<extra></extra>"))
        fig.update_traces(cliponaxis=False)
        fig.update_layout(title=f"{cat.iloc[-1]['loss_category']} loses the most oil, {y0}-{y1}",
                          xaxis_title="lost oil (bbl)", bargap=0.25, xaxis_range=[0, cat["bbl"].max() * 1.15])
        show(style(fig, 460))
        ui.explain("Blue = equipment failures (rod, pump, tubing). Grey = other causes. Labels give the share of all "
                   "avoidable lost oil.")
    with right:
        ac = a.groupby(["field_operating_area", "group"], as_index=False)["est_lost_oil_m3"].sum()
        top_a = ac.groupby("field_operating_area")["est_lost_oil_m3"].sum().nlargest(12).index
        ac = ac[ac["field_operating_area"].isin(top_a)]
        ac["bbl"] = ac["est_lost_oil_m3"] * M3_TO_BBL
        order = ac.groupby("field_operating_area")["bbl"].sum().sort_values().index.tolist()
        fig = px.bar(ac, y="field_operating_area", x="bbl", color="group", orientation="h",
                     color_discrete_map=GROUP_COLORS, category_orders={"group": list(GROUP_COLORS),
                                                                       "field_operating_area": order[::-1]},
                     labels={"bbl": "lost oil (bbl)", "field_operating_area": "", "group": ""})
        fig.update_traces(marker_line_width=0, hovertemplate="%{y}<br>%{x:,.0f} bbl<extra>%{fullData.name}</extra>")
        fig.update_layout(title=f"{order[-1]} loses the most oil of the 12 worst areas", bargap=0.25)
        show(style(fig, 460))

    st.subheader("Wells that lose the most oil to equipment failures")
    bw = D["loss_by_well_year"]
    bw = bw[bw["year"].between(y0, y1)]
    bwf = bw[bw["loss_category"].isin(FAILURE_CATEGORIES)].groupby("uwi")["est_lost_oil_m3"].sum()
    bwd = bw[bw["loss_category"].isin(FAILURE_CATEGORIES)].groupby("uwi")["hours_down"].sum() / 24
    bwa = bw[bw["loss_category"] != "Shut-in (Uneconomic/LTSI)"].groupby("uwi")["est_lost_oil_m3"].sum()
    wy = D["well_year"]
    wy = wy[wy["year"].between(y0, y1)].groupby("uwi").agg(failures=("failures", "sum"), repair_cost=("job_cost", "sum"),
                                                          running_days=("running_days", "sum"))
    t = (D["wells"].set_index("uwi")[["formatted_uwi", "field_operating_area", "facility_name", "pump_make"]]
         .join(bwf.rename("failure_loss_m3")).join(bwd.rename("failure_down_days")).join(bwa.rename("avoidable_loss_m3")).join(wy))
    t = area_filter(t.reset_index()).dropna(subset=["failure_loss_m3"])
    t["failures_per_year"] = t["failures"] / (t["running_days"] / 365).clip(lower=0.25)
    t["failure_loss_bbl"] = t["failure_loss_m3"] * M3_TO_BBL
    t["failure_loss_$"] = t["failure_loss_m3"] * cad_per_m3
    n_bad = st.slider("Number of wells to show", 5, 40, 15, key="bad_n")
    t = t.sort_values("failure_loss_bbl", ascending=False).head(n_bad)
    fig = ui.hbar([f"{w} · {ar}" for w, ar in zip(t["formatted_uwi"].fillna(t["uwi"]), t["field_operating_area"])],
                  t["failure_loss_bbl"],
                  text=[f"{ui.money(v)} · {f:.1f} failures/yr · {int(n)} failures" for v, f, n in
                        zip(t["failure_loss_$"], t["failures_per_year"], t["failures"].fillna(0))],
                  xaxis="oil lost to rod, pump and tubing failures (bbl)", hover="%{y}<br>%{x:,.0f} bbl<extra></extra>",
                  title=f"Wells losing the most oil to equipment failures, {y0}-{y1}")
    fig.update_xaxes(range=[0, t["failure_loss_bbl"].max() * 1.6])
    show(fig)
    ui.explain("Failures = repair-job events. A well with few failures but a long bar sat down for weeks waiting "
               "for a repair, which is a scheduling problem as much as an equipment one.")

    st.subheader("How often wells fail, per running well-year")
    wy2 = D["well_year"][D["well_year"]["year"].between(y0, y1)].merge(
        D["wells"][["uwi", "field_operating_area", "pump_make"]], on="uwi", how="left")
    wy2 = area_filter(wy2)
    c1, c2 = st.columns(2)
    for col_, dim, title in [(c1, "pump_make", "By pump make"), (c2, "field_operating_area", "By area")]:
        r = wy2.groupby(dim).agg(failures=("failures", "sum"), days=("running_days", "sum"), wells=("uwi", "nunique"))
        r = r[r["wells"] >= 15]
        r["rate"] = r["failures"] / (r["days"] / 365)
        r = r.sort_values("rate").tail(12).reset_index()
        fig = go.Figure(go.Bar(y=r[dim], x=r["rate"], orientation="h", marker_color=BLUE,
                               customdata=np.c_[r["wells"], r["failures"]],
                               hovertemplate="<b>%{y}</b><br>%{x:.2f} failures / well-yr<br>"
                                             "%{customdata[0]} wells, %{customdata[1]:,} failures<extra></extra>"))
        fig.update_layout(title=f"{title}: {r.iloc[-1][dim]} has the highest raw rate (groups of 15+ wells)",
                          xaxis_title="failures per well-year", bargap=0.3)
        with col_:
            show(style(fig, 380))
    st.caption("Raw rates, not controlled for area, depth, fluid or well age - pump make and area are correlated. "
               "Treat as a lead for engineering review, not a vendor ranking.")

# ================================================================= WATCHLIST
with tabs[2]:
    rs = D["risk_scores"]
    info = D["model_info"]
    last = rs["production_date"].max()
    c1, c2 = st.columns([1, 3])
    with c1:
        day = st.date_input("Watchlist date", value=last.date(), min_value=rs["production_date"].min().date(),
                            max_value=last.date())
        k = st.slider("Number of wells to list", 5, 100, 25, 5)
    day = pd.Timestamp(day)
    n_days = rs["production_date"].nunique()
    n_watch = (rs["risk"] >= info["alert_threshold"]).sum() / n_days
    n_alarm = (rs["risk"] >= info["alarm_threshold"]).sum() / n_days
    known = rs[rs["label_known"] & (rs["risk"] >= info["alarm_threshold"])]
    alarm_prec = known["y"].mean() if len(known) else float("nan")
    today = area_filter(rs[rs["production_date"] == day])
    today = today.sort_values("risk", ascending=False).head(k).copy()
    wl = D["watchlist"].set_index("uwi")
    today = today.join(D["wells"].set_index("uwi")[["formatted_uwi", "facility_name", "pump_make",
                                                    "surface_latitude", "surface_longitude"]], on="uwi")
    today["drivers"] = today["uwi"].map(wl["drivers"]) if day == last else ""
    today["status"] = np.select([today["risk"] >= info["alarm_threshold"], today["risk"] >= info["alert_threshold"]],
                                ["ALARM", "WATCH"], "-")
    with c2:
        st.markdown(f"**{len(today)} highest-risk running wells on {day.date()}** - probability that a "
                    f"failure-driven outage starts within 14 days. Field base rate ≈ {100 * info['base_rate']:.0f}%. "
                    f"WATCH ≥ {info['alert_threshold']:.2f} (top 5% of 2024 validation scores, "
                    f"≈{n_watch:.0f} wells/day field-wide in 2025-26); ALARM ≥ {info['alarm_threshold']:.2f} "
                    f"(top 2%, ≈{n_alarm:.0f} wells/day, {100 * alarm_prec:.0f}% of them fail within 14 days).")
        if day != last:
            st.caption("Driver explanations are precomputed for the latest date only.")
    col = [CRITICAL if r >= info["alarm_threshold"] else (YELLOW if r >= info["alert_threshold"] else BLUE)
           for r in today["risk"]]
    fig = ui.hbar([f"#{int(r)} {w} · {ar}" for r, w, ar in zip(today["risk_rank"], today["formatted_uwi"].fillna(today["uwi"]),
                                                              today["field_operating_area"])],
                  100 * today["risk"], colors=col,
                  text=[f"{st_} · {d}" if isinstance(d, str) and d else st_ for st_, d in zip(today["status"], today["drivers"])],
                  xaxis="chance a failure outage starts within 14 days (%)", hover="%{y}<br>%{x:.0f}%<extra></extra>",
                  title=f"{int((today['risk'] >= info['alarm_threshold']).sum())} of the {len(today)} listed wells "
                        f"are at ALARM level on {day:%d %b %Y}")
    fig.update_xaxes(range=[0, 100 * today["risk"].max() * 2.2 if len(today) else 100])
    show(fig)
    ui.explain("Red = ALARM, amber = WATCH, blue = on the list but below the WATCH line. The text after each bar "
               "gives the model's top reasons (latest day only).")
    m = today.dropna(subset=["surface_latitude"])
    if len(m):
        fig = go.Figure(go.Scattermap(lat=m["surface_latitude"], lon=m["surface_longitude"], mode="markers",
                                      marker=dict(size=12, color=m["risk"], colorscale=SEQ_BLUE, cmin=0,
                                                  cmax=max(0.5, m["risk"].max()), showscale=True,
                                                  colorbar=dict(title="chance of failure<br>in 14 days")),
                                      text=m["formatted_uwi"] + "<br>" + m["field_operating_area"],
                                      hovertemplate="%{text}<br>risk %{marker.color:.2f}<extra></extra>"))
        fig.update_layout(map=dict(style="open-street-map", center=dict(lat=m["surface_latitude"].mean(),
                                                                         lon=m["surface_longitude"].mean()), zoom=6),
                          height=420, margin=dict(l=0, r=0, t=0, b=0))
        show(fig)
        ui.explain("Map of the listed wells. Darker blue = higher chance of a failure outage in the next 14 days.")
    if day < last - pd.Timedelta(days=14):
        hit = today["y"].fillna(0).astype(int)
        st.success(f"Hindsight check for {day.date()}: {hit.sum()} of these {len(today)} wells actually had a "
                   f"failure outage start within 14 days (random list would average ≈ "
                   f"{len(today) * info['base_rate']:.1f}).")

# ================================================================= DRILL-DOWN
with tabs[3]:
    wells = D["wells"]
    opts = area_filter(wells)
    top_uwis = D["watchlist"]["uwi"].tolist()
    ordered = top_uwis + [u for u in opts["uwi"] if u not in set(top_uwis)]
    labels = wells.set_index("uwi")["formatted_uwi"].fillna("").to_dict()
    uwi = st.selectbox("Well (watchlist wells first)", ordered,
                       format_func=lambda u: f"{labels.get(u, u)}  ({u})")
    wd = well_daily(uwi, STAMP)
    if wd.empty:
        st.info("No daily data from 2024 onward for this well.")
    else:
        evw = D["events"][D["events"]["uwi"] == uwi]
        evw = evw[evw["onset_date"] >= wd["production_date"].min()]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.45, 0.25, 0.30],
                            subplot_titles=("Oil (m³/d) vs baseline", "Pump efficiency", "14-day failure risk"))
        fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["oil_produced_m3"], name="Oil", mode="lines",
                                 line=dict(color=BLUE, width=1.5)), 1, 1)
        fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["baseline_oil_m3d"], name="Baseline (30d median)",
                                 mode="lines", line=dict(color=MUTED, width=1.5, dash="dot")), 1, 1)
        fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["pump_efficiency_pct"], name="Pump efficiency",
                                 mode="lines", line=dict(color=AQUA, width=1.5)), 2, 1)
        fig.add_trace(go.Scatter(x=wd["production_date"], y=wd["risk"], name="Risk", mode="lines",
                                 line=dict(color=ORANGE, width=1.5)), 3, 1)
        fig.add_hline(y=D["model_info"]["alert_threshold"], line=dict(color=MUTED, width=1, dash="dot"),
                      row=3, col=1, annotation_text="watch", annotation_position="top left")
        fig.add_hline(y=D["model_info"]["alarm_threshold"], line=dict(color=CRITICAL, width=1, dash="dash"),
                      row=3, col=1, annotation_text="alarm", annotation_position="top left")
        for _, e in evw.iterrows():
            for r in (1, 2, 3):
                fig.add_vline(x=e["onset_date"], line=dict(color=CRITICAL, width=1), row=r, col=1)
        style(fig, 660)
        fig.update_layout(hovermode="x unified", margin=dict(t=40, b=40),
                          legend=dict(yanchor="top", y=-0.05, orientation="h", x=0),
                          title=f"Oil, pump efficiency and failure risk for {labels.get(uwi, uwi) or uwi}")
        show(fig)
        st.caption("Red vertical lines = failure outages (repair-job events). Risk is the out-of-sample "
                   "model score (trained on data up to 2024).")
        if len(evw):
            fig = go.Figure()
            fig.add_trace(go.Bar(x=evw["onset_date"], y=evw["pre_failure_loss_m3"], name="lost in the 2 weeks before",
                                 marker_color=YELLOW, hovertemplate="%{x|%d %b %Y}: %{y:.1f} m³ before<extra></extra>"))
            fig.add_trace(go.Bar(x=evw["onset_date"], y=evw["outage_loss_m3"], name="lost during the outage",
                                 marker_color=ORANGE, customdata=np.c_[evw["component"].astype(str), evw["outage_days"]],
                                 hovertemplate="%{x|%d %b %Y}: %{y:.1f} m³ during a %{customdata[1]:.0f}-day "
                                               "%{customdata[0]} outage<extra></extra>"))
            fig.update_layout(title="Oil lost before and during each failure", barmode="stack",
                          yaxis_title="lost oil (m³)", xaxis_title="failure date")
            show(style(fig, 280))
            ui.explain("One stack per failure: the decline before it (yellow) and the outage itself (orange).")

# ================================================================= MODEL & VALUE
with tabs[4]:
    mt = D["metrics"].set_index("model")
    info = D["model_info"]
    k = st.radio("Wells on the daily watchlist (K)", [10, 25, 50], index=1, horizontal=True)
    c1, c2, c3, c4 = st.columns(4)
    lg = mt.loc["LightGBM"]
    c1.metric("Precision of watchlist", f"{100 * lg[f'precision@{k}']:.0f}%",
              f"{lg[f'lift@{k}']:.1f}× the {100 * info['base_rate']:.0f}% base rate", delta_color="off", delta_arrow="off")
    c2.metric("Failures caught ahead of time", f"{100 * lg[f'event_recall@{k}']:.0f}%",
              f"of {info['n_test_events']:,} test-period failures", delta_color="off", delta_arrow="off")
    c3.metric("Median warning", f"{lg[f'median_lead_days@{k}']:.0f} days", "before the outage starts",
              delta_color="off", delta_arrow="off")
    c4.metric("New alerts per day", f"{lg[f'alerts_per_day@{k}']:.1f}",
              f"{lg[f'caught_per_100_alerts@{k}']:.0f} failures caught per 100 alerts", delta_color="off", delta_arrow="off")
    st.caption(f"Held-out test: {info['test_period']} - model trained on {info['train_period']} + 2024 "
               "(2024 used to choose tree count). No well-days from the test period were seen in training.")

    left, right = st.columns(2)
    with left:
        cmp = mt[[f"event_recall@{k}", f"caught_per_100_alerts@{k}"]].reset_index()
        cmp["color"] = np.where(cmp["model"] == "LightGBM", BLUE, GRAY)
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Failures caught (%)", "Caught per 100 alerts"),
                            shared_yaxes=True, horizontal_spacing=0.08)
        fig.add_trace(go.Bar(y=cmp["model"], x=100 * cmp[f"event_recall@{k}"], orientation="h",
                             marker_color=cmp["color"], hovertemplate="%{y}: %{x:.0f}%<extra></extra>"), 1, 1)
        fig.add_trace(go.Bar(y=cmp["model"], x=cmp[f"caught_per_100_alerts@{k}"], orientation="h",
                             marker_color=cmp["color"], hovertemplate="%{y}: %{x:.0f}<extra></extra>"), 1, 2)
        best = cmp.loc[cmp[f"caught_per_100_alerts@{k}"].idxmax(), "model"]
        fig.update_layout(title=f"{best} catches the most failures per 100 alerts at K = {k}", showlegend=False,
                          bargap=0.3)
        show(style(fig, 340))
        st.caption("Random lists catch failures only by flagging ~7× more wells; per alert they are ~6× worse.")
    with right:
        imp = D["importance"].head(12).iloc[::-1]
        fig = go.Figure(go.Bar(y=imp["label"], x=imp["gain_pct"], orientation="h", marker_color=BLUE,
                               hovertemplate="%{y}: %{x:.1f}% of gain<extra></extra>"))
        fig.update_layout(title=f"{imp.iloc[-1]['label']} drives the score most", xaxis_title="share of model gain (%)",
                          bargap=0.3)
        show(style(fig, 340))

    st.subheader("Value calculator")
    st.markdown("Estimate from the **held-out test period**, using only the failures the model actually caught at "
                "this K. Each assumption is adjustable; defaults are deliberately conservative.")
    c1, c2, c3 = st.columns(3)
    a_out = c1.slider("Share of outage loss avoided when a failure is caught early", 0, 100, 30, 5,
                      help="Pre-staged rod truck / parts / crew shortens the outage.") / 100
    a_pre = c2.slider("Share of pre-failure decline avoided", 0, 100, 25, 5,
                      help="Earlier intervention while the well is still declining.") / 100
    check_cost = c3.number_input("Cost per proactive check (C$)", 0, 5000, 300, 50,
                                 help="Operator site visit / pump diagnostic for each new alert.")
    te = D["test_events"]
    caught = te[te[f"caught@{k}"]]
    days = (pd.Timestamp(info["test_period"].split("..")[1]) - pd.Timestamp(info["test_period"].split("..")[0])).days
    yrs = days / 365
    saved_m3 = a_out * caught["outage_loss_m3"].fillna(0).sum() + a_pre * caught["pre_failure_loss_m3"].fillna(0).sum()
    gross = saved_m3 * cad_per_m3 / yrs
    checks = lg[f"alerts_per_day@{k}"] * 365 * check_cost
    c1, c2, c3 = st.columns(3)
    c1.metric("Oil protected per year", f"{saved_m3 * M3_TO_BBL / yrs:,.0f} bbl")
    c2.metric("Gross value per year", f"C${gross / 1e6:,.2f}M")
    c3.metric("Net of check costs", f"C${(gross - checks) / 1e6:,.2f}M", f"checks ≈ C${checks / 1e3:,.0f}k/yr",
              delta_color="off", delta_arrow="off")
    st.caption(f"{len(caught):,} of {info['n_test_events']:,} scorable test-period failure events were flagged "
               f"at K={k}. Repair cost "
               "savings (e.g. a rod truck instead of a workover) are not counted.")

    with st.expander("All models at every list size"):
        fig = go.Figure()
        for model_, color in zip(mt.index, [BLUE, GRAY, MUTED, YELLOW, AQUA]):
            fig.add_trace(go.Scatter(x=[10, 25, 50], y=[100 * mt.loc[model_, f"precision@{kk}"] for kk in (10, 25, 50)],
                                     mode="lines+markers", name=model_, line=dict(color=color, width=2.5 if model_ == "LightGBM" else 1.5)))
        fig.update_layout(title="Share of listed wells that fail within 14 days, by list size", xaxis_title="wells on the list",
                          yaxis_title="listed wells that fail (%)", xaxis=dict(tickvals=[10, 25, 50]))
        show(style(fig, 300))
        ui.explain("Higher is better. The blue model line stays above the simple rules at every list size.")
    with st.expander("Precision-recall curve (well-day level)"):
        pr = D["pr_curve"]
        fig = go.Figure(go.Scatter(x=pr["recall"], y=pr["precision"], mode="lines", line=dict(color=BLUE, width=2),
                                   hovertemplate="recall %{x:.2f}<br>precision %{y:.2f}<extra></extra>"))
        fig.add_hline(y=info["base_rate"], line=dict(color=MUTED, dash="dot"), annotation_text="base rate")
        fig.update_layout(title="Precision falls as the model flags more of the failures",
                          xaxis_title="recall (share of failures flagged)",
                          yaxis_title="precision (share of flags that fail)")
        show(style(fig, 320))

# ================================================================= DATA QUALITY
with tabs[5]:
    st.markdown("Problems found and how the pipeline handles them. Detail: `DATA_SUMMARY.md`.")
    st_ = D["stale_tags"].sort_values("repeat_prev_day_pct")
    fig = go.Figure(go.Bar(y=st_["tag"], x=st_["repeat_prev_day_pct"], orientation="h",
                           marker_color=np.where(st_["repeat_prev_day_pct"] > 90, ORANGE, BLUE),
                           hovertemplate="%{y}: %{x:.1f}% repeat previous day<extra></extra>"))
    fig.update_layout(title=f"{int((st_['repeat_prev_day_pct'] > 90).sum())} tags repeat the previous day's reading "
                            "more than 90% of the time (orange)", xaxis_title="readings identical to the previous day (%)",
                      bargap=0.3)
    show(style(fig, 340))
    dq = D["dq_report"]
    dqs = pd.Series({k_: v_ for k_, v_ in dq.items() if isinstance(v_, (int, float)) and k_ != "rows_raw"}).sort_values(
        ascending=False)
    fig = ui.hbar([k_.replace("_", " ") for k_ in dqs.index], dqs.values, text=[f"{v_:,.0f}" for v_ in dqs.values],
                  xaxis="rows affected (log scale)", hover="%{y}: %{x:,.0f} rows<extra></extra>",
                  title=f"Data problems fixed by the pipeline (of {dq.get('rows_raw', 0):,} daily rows)")
    fig.update_xaxes(type="log")
    show(fig)
    ui.explain("Out-of-range values (999,999 placeholders, negative volumes) are set to blank. Duplicates are dropped.")
    ev = D["event_validation"]
    st.markdown(f"**Failure label check (2025-26):** {ev['pct_failure_records_matched_by_job_event']}% of logged "
                f"failures match a repair-job event within ±{ev['match_window_days']} days; "
                f"{ev['pct_job_events_matched_by_failure_record']}% of repair-job events appear in the failure log "
                "(the log is less complete than the job records).")
    st.markdown("**Recommendation:** automate pressure, torque and motor-current tags into the historian at "
                "≥ hourly resolution. Today these change on <5% of days, which is why they add little "
                "early warning; daily oil and pump efficiency carry most of the signal.")
