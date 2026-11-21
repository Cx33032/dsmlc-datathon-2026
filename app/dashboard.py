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

# Validated reference palette (dataviz skill, light steps). Slots in fixed order.
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GRAY, MUTED = "#a9a8a1", "#898781"
CRITICAL = "#d03b3b"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GROUP_COLORS = {"Equipment failure": BLUE, "Facility & capacity": ORANGE,
                "Other avoidable": AQUA, "Uncoded": YELLOW}


def style(fig: go.Figure, h: int = 360) -> go.Figure:
    # small top margin: the title is drawn by show() above the chart, and plotly grows the
    # margin itself when the legend wraps onto several rows
    top = 36 if fig.layout.annotations else 8  # room for subplot titles
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=top, b=8), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, xanchor="left", title=None,
                                  bgcolor="rgba(0,0,0,0)"),
                      font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif"))
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.25)", zeroline=False)
    return fig


def show(fig, **kw):
    """Render the chart title as page text (it wraps on narrow screens instead of colliding
    with the legend), then the chart itself."""
    title = fig.layout.title.text
    if title:
        st.markdown(f"**{title}**")
        fig.update_layout(title=None)
    st.plotly_chart(fig, use_container_width=True, theme="streamlit", **kw)


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
    st.error("No pipeline outputs found. Run `python run_pipeline.py` first.")
    st.stop()
STAMP = (OUT / "model_info.json").stat().st_mtime + hash(str(OUT)) % 1000
D = load(STAMP)
lm = D["loss_monthly"].copy()
lm["group"] = lm["loss_category"].map(group_of)
avoid = lm[lm["loss_category"] != "Shut-in (Uneconomic/LTSI)"]

# ---------------------------------------------------------------- sidebar
areas = sorted(lm["field_operating_area"].dropna().unique())
sel_areas = st.sidebar.multiselect("Operating areas", areas, placeholder="All areas")
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
    c2.metric("Avoidable loss, bbl", f"{lost12 * M3_TO_BBL / 1e3:,.0f}k", f"≈ ${lost12 * cad_per_m3 / 1e6:,.1f}M",
              delta_color="off", delta_arrow="off",
              help=f"Estimated avoidable lost oil: {lost12 * M3_TO_BBL:,.0f} bbl, valued at the netback in the sidebar.")
    c3.metric("From failures, bbl", f"{fail12 * M3_TO_BBL / 1e3:,.0f}k",
              f"{100 * fail12 / max(lost12, 1):.0f}% of avoidable", delta_color="off", delta_arrow="off",
              help=f"Lost oil from rod, pump and tubing failures: {fail12 * M3_TO_BBL:,.0f} bbl.")
    c4.metric("Failure events", f"{len(ev12):,}", f"${ev12['job_cost'].sum() / 1e6:,.1f}M repairs",
              delta_color="off", delta_arrow="off",
              help="Rod/pump/tubing repair events and their field-estimated job cost.")

    left, right = st.columns(2)
    with left:
        fig = go.Figure(go.Scatter(x=prod["month"], y=prod["bbl_d"], mode="lines", line=dict(color=BLUE, width=2),
                                   hovertemplate="%{x|%b %Y}<br>%{y:,.0f} bbl/d<extra></extra>"))
        fig.update_layout(title="Oil production rate (bbl/d, monthly)")
        show(style(fig))
    with right:
        g = a.groupby(["month", "group"], as_index=False)["est_lost_oil_m3"].sum()
        g["bbl_d"] = g["est_lost_oil_m3"] * M3_TO_BBL / month_days(g["month"])
        fig = px.bar(g, x="month", y="bbl_d", color="group", color_discrete_map=GROUP_COLORS,
                     category_orders={"group": list(GROUP_COLORS)},
                     labels={"bbl_d": "bbl/d", "month": "", "group": ""})
        fig.update_traces(marker_line_width=0, hovertemplate="%{x|%b %Y}<br>%{y:,.0f} bbl/d<extra>%{fullData.name}</extra>")
        fig.update_layout(title="Avoidable lost oil by cause (bbl/d, monthly)", bargap=0.15)
        show(style(fig))
    st.caption("Equipment failure = rod, pump and tubing/packer failures. "
               "Lost oil = the well's trailing 30-day median oil rate × hours down / 24, per downtime day. "
               f"Validated against operator-reported lost oil: totals within "
               f"{abs(1 - D['loss_validation']['sum_est_over_sum_reported']) * 100:.0f}%, rank correlation "
               f"{D['loss_validation']['spearman_r']:.2f}. Economic long-term shut-ins are excluded as a business "
               "decision, not a loss.")

# ================================================================= LOSSES
with tabs[1]:
    years = sorted(avoid["month"].dt.year.unique())
    y0, y1 = st.select_slider("Years", options=years, value=(years[0], years[-1]))
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
        fig.update_layout(title=f"Lost oil by cause, {y0}-{y1} (bbl) - equipment failures in blue",
                          xaxis_title="bbl", bargap=0.25, xaxis_range=[0, cat["bbl"].max() * 1.15])
        show(style(fig, 460))
    with right:
        ac = a.groupby(["field_operating_area", "group"], as_index=False)["est_lost_oil_m3"].sum()
        top_a = ac.groupby("field_operating_area")["est_lost_oil_m3"].sum().nlargest(12).index
        ac = ac[ac["field_operating_area"].isin(top_a)]
        ac["bbl"] = ac["est_lost_oil_m3"] * M3_TO_BBL
        order = ac.groupby("field_operating_area")["bbl"].sum().sort_values().index.tolist()
        fig = px.bar(ac, y="field_operating_area", x="bbl", color="group", orientation="h",
                     color_discrete_map=GROUP_COLORS, category_orders={"group": list(GROUP_COLORS),
                                                                       "field_operating_area": order[::-1]},
                     labels={"bbl": "bbl", "field_operating_area": "", "group": ""})
        fig.update_traces(marker_line_width=0, hovertemplate="%{y}<br>%{x:,.0f} bbl<extra>%{fullData.name}</extra>")
        fig.update_layout(title="Lost oil by area (top 12)", bargap=0.25)
        show(style(fig, 460))

    st.subheader("Bad actors - wells losing the most oil to equipment failures")
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
    t = t.sort_values("failure_loss_bbl", ascending=False).head(25)
    st.dataframe(t[["formatted_uwi", "field_operating_area", "facility_name", "pump_make", "failures",
                    "failures_per_year", "failure_down_days", "failure_loss_bbl", "failure_loss_$", "repair_cost"]],
                 hide_index=True, use_container_width=True,
                 column_config={"formatted_uwi": "Well", "field_operating_area": "Area", "facility_name": "Facility",
                                "pump_make": "Pump make", "failures": st.column_config.NumberColumn("Failures"),
                                "failures_per_year": st.column_config.NumberColumn("Failures / yr", format="%.1f"),
                                "failure_down_days": st.column_config.NumberColumn("Days down (failure codes)",
                                                                                   format="%,.0f"),
                                "failure_loss_bbl": st.column_config.NumberColumn("Lost oil (bbl)", format="%,.0f"),
                                "failure_loss_$": st.column_config.NumberColumn("Lost value ($)", format="$%,.0f"),
                                "repair_cost": st.column_config.NumberColumn("Repair cost ($)", format="$%,.0f")})

    st.caption("Failures = repair-job events. Wells with few failures but many down days sat shut in under a "
               "rods/pump/tubing code waiting for repair - a scheduling opportunity in itself.")

    st.subheader("Failure frequency - failures per running well-year")
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
        fig.update_layout(title=f"{title} (≥15 wells)", xaxis_title="failures per well-year", bargap=0.3)
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
        k = st.slider("Watchlist size (wells/day)", 5, 100, 25, 5)
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
                                ["⛔ ALARM", "⚠ WATCH"], "-")
    with c2:
        st.markdown(f"**{len(today)} highest-risk running wells on {day.date()}** - probability that a "
                    f"failure-driven outage starts within 14 days. Field base rate ≈ {100 * info['base_rate']:.0f}%. "
                    f"WATCH ≥ {info['alert_threshold']:.2f} (top 5% of 2024 validation scores, "
                    f"≈{n_watch:.0f} wells/day field-wide in 2025-26); ALARM ≥ {info['alarm_threshold']:.2f} "
                    f"(top 2%, ≈{n_alarm:.0f} wells/day, {100 * alarm_prec:.0f}% of them fail within 14 days).")
        if day != last:
            st.caption("Driver explanations are precomputed for the latest date only.")
    st.dataframe(today[["risk_rank", "formatted_uwi", "field_operating_area", "facility_name", "pump_make", "risk",
                        "status", "drivers"]],
                 hide_index=True, use_container_width=True,
                 column_config={"risk_rank": "Rank", "formatted_uwi": "Well", "field_operating_area": "Area",
                                "facility_name": "Facility", "pump_make": "Pump",
                                "risk": st.column_config.ProgressColumn("14-day failure risk", min_value=0,
                                                                        max_value=1, format="%.2f"),
                                "status": "Status", "drivers": "Top drivers (SHAP)"})
    m = today.dropna(subset=["surface_latitude"])
    if len(m):
        fig = go.Figure(go.Scattermap(lat=m["surface_latitude"], lon=m["surface_longitude"], mode="markers",
                                      marker=dict(size=12, color=m["risk"], colorscale=SEQ_BLUE, cmin=0,
                                                  cmax=max(0.5, m["risk"].max()), showscale=True,
                                                  colorbar=dict(title="risk")),
                                      text=m["formatted_uwi"] + "<br>" + m["field_operating_area"],
                                      hovertemplate="%{text}<br>risk %{marker.color:.2f}<extra></extra>"))
        fig.update_layout(map=dict(style="open-street-map", center=dict(lat=m["surface_latitude"].mean(),
                                                                         lon=m["surface_longitude"].mean()), zoom=6),
                          height=420, margin=dict(l=0, r=0, t=0, b=0))
        show(fig)
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
                          legend=dict(yanchor="top", y=-0.05, orientation="h", x=0))
        show(fig)
        st.caption("Red vertical lines = failure outages (repair-job events). Risk is the out-of-sample "
                   "model score (trained on data up to 2024).")
        if len(evw):
            st.dataframe(evw[["onset_date", "job_date", "component", "job_type", "job_subtype", "outage_days",
                              "pre_failure_loss_m3", "outage_loss_m3", "job_cost"]].round(1),
                         hide_index=True, use_container_width=True)

# ================================================================= MODEL & VALUE
with tabs[4]:
    mt = D["metrics"].set_index("model")
    info = D["model_info"]
    k = st.radio("Daily watchlist size K", [10, 25, 50], index=1, horizontal=True)
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
        fig.update_layout(title=f"Model vs baselines at K={k}", showlegend=False, bargap=0.3)
        show(style(fig, 340))
        st.caption("Random lists catch failures only by flagging ~7× more wells; per alert they are ~6× worse.")
    with right:
        imp = D["importance"].head(12).iloc[::-1]
        fig = go.Figure(go.Bar(y=imp["label"], x=imp["gain_pct"], orientation="h", marker_color=BLUE,
                               hovertemplate="%{y}: %{x:.1f}% of gain<extra></extra>"))
        fig.update_layout(title="What drives the score (share of model gain)", xaxis_title="%", bargap=0.3)
        show(style(fig, 340))

    st.subheader("Value calculator")
    st.markdown("Estimate from the **held-out test period**, using only the failures the model actually caught at "
                "this K. Each assumption is adjustable; defaults are deliberately conservative.")
    c1, c2, c3 = st.columns(3)
    a_out = c1.slider("Share of outage loss avoided when a failure is caught early", 0, 100, 30, 5,
                      help="Pre-staged rod truck / parts / crew shortens the outage.") / 100
    a_pre = c2.slider("Share of pre-failure decline avoided", 0, 100, 25, 5,
                      help="Earlier intervention while the well is still declining.") / 100
    check_cost = c3.number_input("Cost per proactive check ($)", 0, 5000, 300, 50,
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
    c2.metric("Gross value per year", f"${gross / 1e6:,.2f}M")
    c3.metric("Net of check costs", f"${(gross - checks) / 1e6:,.2f}M", f"checks ≈ ${checks / 1e3:,.0f}k/yr",
              delta_color="off", delta_arrow="off")
    st.caption(f"{len(caught):,} of {info['n_test_events']:,} scorable test-period failure events were flagged "
               f"at K={k}. Repair cost "
               "savings (e.g. a rod truck instead of a workover) are not counted.")

    with st.expander("Full metrics table"):
        st.dataframe(mt.round(3), use_container_width=True)
    with st.expander("Precision-recall curve (well-day level)"):
        pr = D["pr_curve"]
        fig = go.Figure(go.Scatter(x=pr["recall"], y=pr["precision"], mode="lines", line=dict(color=BLUE, width=2),
                                   hovertemplate="recall %{x:.2f}<br>precision %{y:.2f}<extra></extra>"))
        fig.add_hline(y=info["base_rate"], line=dict(color=MUTED, dash="dot"), annotation_text="base rate")
        fig.update_layout(xaxis_title="recall", yaxis_title="precision")
        show(style(fig, 320))

# ================================================================= DATA QUALITY
with tabs[5]:
    st.markdown("Problems found and how the pipeline handles them. Detail: `DATA_SUMMARY.md`.")
    st_ = D["stale_tags"].sort_values("repeat_prev_day_pct")
    fig = go.Figure(go.Bar(y=st_["tag"], x=st_["repeat_prev_day_pct"], orientation="h",
                           marker_color=np.where(st_["repeat_prev_day_pct"] > 90, ORANGE, BLUE),
                           hovertemplate="%{y}: %{x:.1f}% repeat previous day<extra></extra>"))
    fig.update_layout(title="Share of daily readings identical to the previous day (orange = carried-forward "
                            "manual readings)", xaxis_title="%", bargap=0.3)
    show(style(fig, 340))
    dq = D["dq_report"]
    st.dataframe(pd.DataFrame({"check": list(dq), "rows": list(dq.values())}), hide_index=True,
                 use_container_width=True)
    ev = D["event_validation"]
    st.markdown(f"**Failure label check (2025-26):** {ev['pct_failure_records_matched_by_job_event']}% of logged "
                f"failures match a repair-job event within ±{ev['match_window_days']} days; "
                f"{ev['pct_job_events_matched_by_failure_record']}% of repair-job events appear in the failure log "
                "(the log is less complete than the job records).")
    st.markdown("**Recommendation:** automate pressure, torque and motor-current tags into the historian at "
                "≥ hourly resolution. Today these change on <5% of days, which is why they add little "
                "early warning; daily oil and pump efficiency carry most of the signal.")
