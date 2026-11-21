"""Evidence: why each decision is trustworthy, and the idea we tested and killed (or kept)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

st.title("Evidence")
tab_q, tab_rod, tab_depth, tab_shock, tab_traps = st.tabs(
    ["Today: dispatch replay", "At the pull: new string", "At the pull: break depth", "Between failures: whiplash",
     "Traps we avoided"])

# ---------------------------------------------------------------- dispatch
with tab_q:
    rep, info = ui.art("dispatch_replay.csv"), ui.art("dispatch_info.json") or {}
    if rep is None:
        ui.require("dispatch_replay.csv")
    else:
        st.markdown(f"Fitted on outages up to Dec 28, 2025; replayed on every day from Jan 1 to Oct 23, 2026 "
                    f"({info.get('tickets_test', 0):,} outages, {info.get('tickets_per_day', 0):.1f} per day). Each "
                    "day the top K tickets are reviewed; capture = their share of what all tickets went on to lose.")
        for outcome in ("reconstructed exposure", "recorded loss"):
            r = rep[rep["outcome"] == outcome]
            fig = go.Figure()
            for col, lab, color in (("first_day_loss", "rank by day-1 reported loss", ui.GRAY),
                                    ("dispatch", "Dispatch score", ui.BLUE), ("oracle", "oracle (hindsight)", ui.MUTED)):
                fig.add_trace(go.Bar(x=[f"K={k}" for k in r["K"]], y=100 * r[col], name=lab, marker_color=color,
                                     text=[f"{100 * v:.1f}" for v in r[col]], textposition="outside",
                                     hovertemplate=lab + ": %{y:.1f}%<extra></extra>"))
            fig.update_layout(title=f"Share of {outcome} captured (%)", barmode="group", bargap=0.25,
                              yaxis=dict(range=[0, 105], title="%"))
            ui.show(ui.style(fig, 300))
        st.caption("Reconstructed from the team's Dispatch spec (the original notebook is not in this repo). The "
                   "original report: 52.7% vs 43.9% exposure and 50.6% vs 48.8% recorded loss at K = 2.")

# ---------------------------------------------------------------- idea 1
with tab_rod:
    econ = ui.art("ideas/1/economics.json")
    if econ is None:
        ui.require("ideas/1/economics.json")
    else:
        st.markdown(f"**A new string halves the hazard of the next rod repair.** Cox model, stratified by area × year, "
                    f"adjusted for prior failures, RPM and liquid rate (n = {econ['n_cox']:,} rod jobs, "
                    f"{econ['events_cox']:,} repeat repairs).")
        c1, c2 = st.columns(2)
        for c, f, lab in ((c1, "ideas/1/cox_all.csv", "All rod jobs"), (c2, "ideas/1/cox_chronic.csv",
                                                                        "Chronic wells (≥2 prior repairs)")):
            t = ui.art(f)
            c.markdown(f"**{lab}**")
            c.dataframe(t.assign(term=t["term"].map({"is_replace": "new string (vs repair)", "log_prior": "log prior repairs",
                                                     "rpm100": "RPM / 100", "log_liq": "log liquid rate"})),
                        hide_index=True, use_container_width=True,
                        column_config={k: st.column_config.NumberColumn(format="%.3f") for k in ["HR", "HR_lo", "HR_hi", "p"]})
        st.caption("RPM level has almost no adjusted effect (HR ≈ 0.97 per 100 rpm), which is why the Whiplash test "
                   "asks about RPM *volatility* instead.")
        l, r = st.columns(2)
        with l:
            tab = ui.art("ideas/1/rate_by_history.csv")
            fig = go.Figure()
            for k, lab, color in ((0, "after a repair", ui.ORANGE), (1, "after a new string", ui.BLUE)):
                g = tab[tab["is_replace"] == k]
                fig.add_trace(go.Bar(x=g["prior_bin"].astype(str), y=g["rate"], name=lab, marker_color=color,
                                     error_y=dict(type="data", symmetric=False, array=g["hi"] - g["rate"],
                                                  arrayminus=g["rate"] - g["lo"], color=ui.MUTED),
                                     customdata=g["n"], hovertemplate="%{y:.2f}/yr (n=%{customdata})<extra></extra>"))
            fig.update_layout(title="Rod repairs per producing year, next 365 d", barmode="group",
                              xaxis_title="rod repairs in the 365 d before the job", yaxis_title="repairs / yr")
            ui.show(ui.style(fig, 320))
        with r:
            km = ui.art("ideas/1/km_chronic.csv")
            fig = go.Figure()
            for g, color in (("repair", ui.ORANGE), ("new rod string", ui.BLUE)):
                d = km[km["group"] == g]
                fig.add_trace(go.Scatter(x=d["t"], y=d["surv"], mode="lines", line=dict(color=color, width=2, shape="hv"),
                                         name=f"{g} (n={int(d['n'].iloc[0]) if len(d) else 0})"))
            fig.update_layout(title="Chronic wells: share with no further rod repair", xaxis_title="days since the job",
                              yaxis=dict(range=[0, 1], title="share"))
            ui.show(ui.style(fig, 320))

# ---------------------------------------------------------------- idea 5
with tab_depth:
    m = ui.art("ideas/5/metrics.json")
    if m is None:
        ui.require("ideas/5/metrics.json")
    else:
        a, b, c = st.columns(3)
        a.metric("Rod failures located from crew text", f"{m['located_total']:,}", f"{m['located_pct']:.0f}% of {m['rod_failures']:,}",
                 delta_arrow="off", delta_color="off")
        b.metric("Consecutive breaks within 50 m", f"{100 * m['share_within_50m']:.1f}%",
                 f"vs {100 * m['baseline_share_within_50m']:.1f}% by chance ({m['lift']:.1f}×)", delta_arrow="off",
                 delta_color="off")
        c.metric("Program wells breaking in a ≤150 m band", m["program_wells_band_le_150"],
                 f"of {m['program_wells_2plus']} with ≥2 located breaks", delta_arrow="off", delta_color="off")
        l, r = st.columns(2)
        with l:
            perm = ui.art("ideas/5/perm_share.csv")
            fig = go.Figure(go.Histogram(x=100 * perm["share_within_50m"], nbinsx=30, marker_color=ui.GRAY,
                                         name="random pairing within area"))
            fig.add_vline(x=100 * m["share_within_50m"], line=dict(color=ui.CRITICAL, width=2.5),
                          annotation_text=f"observed {100 * m['share_within_50m']:.1f}%")
            fig.update_layout(title=f"Same-depth repeats vs 1,000 permutations (p = {m['perm_p']:.3f})",
                              xaxis_title="% of consecutive pairs within 50 m", yaxis_title="permutations",
                              showlegend=False)
            ui.show(ui.style(fig, 320))
        with r:
            kw = ui.art("ideas/5/keywords_by_cause.csv")
            cols = [("kw_pitting", "pitting"), ("kw_corrosion", "corrosion"), ("kw_wear", "wear"),
                    ("kw_guides_centralizers", "guides")]
            fig = go.Figure()
            for cause, color in (("Fatigue", ui.BLUE), ("Corrosion", ui.CRITICAL), ("Load / Excess Stress", ui.ORANGE)):
                row = kw[kw["cause"] == cause]
                if len(row):
                    fig.add_trace(go.Bar(x=[l2 for _, l2 in cols], y=[row[c].iloc[0] for c, _ in cols],
                                         name=f"coded {cause}", marker_color=color))
            fig.update_layout(title=f"Crew text vs coded cause: {m['fatigue_mention_pit_corr']} 'Fatigue' breaks "
                                    "mention pitting/corrosion", barmode="group",
                              yaxis_title="% of linked crew notes")
            ui.show(ui.style(fig, 320))
        st.caption("Depth comes from 'Broken corod @ 247m', joint numbers × 7.62 m on stick rods, and job summaries "
                   "only when a break word and a metre unit appear together (so pull weights are not read as depths).")

# ---------------------------------------------------------------- whiplash
with tab_shock:
    v = ui.art("ideas/whiplash/verdict.json")
    if v is None:
        st.info("The Mechanical Whiplash test has not been run on this data yet "
                "(`python build_artifacts.py --only whiplash`).")
    else:
        head = "Kept as a watch signal" if v.get("keep") else "Idea we tested and rejected"
        (st.success if v.get("keep") else st.warning)(f"**{head}.** {v.get('summary', '')}")
        st.markdown(f"**Question.** {v.get('question', '')}  \n**Expected direction (stated before running).** "
                    f"{v.get('expected', '')}")
        res = ui.art("ideas/whiplash/results_table.csv")
        if res is not None:
            st.dataframe(res, hide_index=True, use_container_width=True)
        cc = ui.art("ideas/whiplash/case_crossover_pairs.csv")
        perm = ui.art("ideas/whiplash/perm_null.csv")
        l, r = st.columns(2)
        if cc is not None and len(cc):
            with l:
                fig = go.Figure(go.Histogram(x=cc["diff"], nbinsx=40, marker_color=ui.BLUE))
                fig.add_vline(x=0, line=dict(color=ui.MUTED, width=1))
                fig.add_vline(x=cc["diff"].mean(), line=dict(color=ui.CRITICAL, width=2),
                              annotation_text=f"mean {cc['diff'].mean():+.3f}")
                fig.update_layout(title="Hazard window minus the same well's control windows (shock index)",
                                  xaxis_title="difference in shock index (z)", yaxis_title="failures", showlegend=False)
                ui.show(ui.style(fig, 300))
        if perm is not None and len(perm):
            with r:
                fig = go.Figure(go.Histogram(x=perm["mean_diff"], nbinsx=40, marker_color=ui.GRAY))
                fig.add_vline(x=v.get("cc_mean_diff", 0), line=dict(color=ui.CRITICAL, width=2.5),
                              annotation_text="observed")
                fig.update_layout(title="Observed vs sign-flip permutation null", xaxis_title="mean difference",
                                  yaxis_title="permutations", showlegend=False)
                ui.show(ui.style(fig, 300))
        st.caption(v.get("coverage", ""))

# ---------------------------------------------------------------- traps
with tab_traps:
    st.dataframe(pd.DataFrame([
        ("Failure log only covers mid-2025 on", "Rod events come from job records (2021-26); failure-log tests start Jun 2025"),
        ("Old 'Rod Repair' jobs carry $0 cost", "Repair cost = mean of cost > 0, 2023 onward"),
        ("Duplicate job rows for one pull", "Jobs within 3 days on a well merged into one event; replace wins"),
        ("2021 events have no prior history", "Prior-repair counts only for events from 2022"),
        ("Replaced wells are different wells", "Cox adjusted for prior failures, RPM, liquid; stratified by area × year"),
        ("Pull weights read as depths ('free at 15,000 lbs')", "Summaries need a break word AND a metre unit"),
        ("Duplicate failure records look like repeats", "Same-well break pairs < 7 days apart dropped"),
        ("Operators slow struggling wells (reverse causation)", "Whiplash hazard window ends 7 days before the failure"),
        ("Tuning on the test period", "Dispatch fitted to Dec 28, 2025; tested on 2026. Whiplash windows fixed in advance"),
        ("Carried-forward manual readings look like steady operation", "RPM/torque repeats flagged; volatility tested "
                                                                       "only where tags change"),
        ("Uneconomic shut-ins inflate 'lost oil'", "Excluded from lost oil and from the queue"),
    ], columns=["Trap", "What we did"]), hide_index=True, use_container_width=True)
