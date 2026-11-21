"""Evidence: why each decision is trustworthy, and the idea we tested and killed (or kept)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ui

top_slot = ui.header(
    "Can you trust these numbers?",
    how=["Read where the numbers come from, just below.",
         "Pick a tab: one per decision, plus the idea we tested and the traps we avoided.",
         "Use the selectors above a chart to switch the measure or the scenario.",
         "Read the note under each chart. It says how to read the chart and what it shows.",
         "For what the numbers cannot show, open Assumptions & limits."],
    terms=["Replay", "Exposure", "Recorded loss", "HR", "CI", "Cox model", "Chronic rod well"],
    extra_terms={"K": "The number of outages reviewed per day.",
                 "Permutation test": "Shuffle the data many times to see what chance alone produces, then compare "
                                     "the real result with that range.",
                 "OR and SD": "Odds ratio and standard deviation.",
                 "Mechanical Whiplash": "The idea that volatile pump operation comes before rod failures."})

rep0, econ0 = ui.art("dispatch_replay.csv"), ui.art("ideas/1/economics.json")
parts = []
if rep0 is not None and len(r0 := rep0[(rep0["K"] == 2) & (rep0["outcome"] == "reconstructed exposure")]):
    parts.append(f"Re-run on every day of 2026, the queue caught {100 * r0['dispatch'].iloc[0]:.0f}% of the next 3 days' "
                 f"lost oil at 2 reviews a day, against {100 * r0['first_day_loss'].iloc[0]:.0f}% for ranking by day-1 "
                 "loss.")
if econ0 is not None:
    parts.append(f"On wells with 2 or more prior rod repairs, the next rod repair after a new string comes at about {econ0['hr_chronic']:.2f} times the rate "
                 f"after a repair (95% CI {econ0['hr_chronic_lo']:.2f} to {econ0['hr_chronic_hi']:.2f}).")
if parts:
    ui.summary(top_slot, " ".join(parts))

# ---------------------------------------------------------------- where the numbers come from
with st.container(border=True):
    st.markdown("**Where the numbers come from**")
    if ui.is_demo():
        st.markdown("Demo mode: synthetic wells, outages, rod jobs and crew-style notes with the same columns as the "
                    "real files. The numbers are examples only.")
    else:
        st.markdown("Three operator files, Jan 2021 to Oct 2026, for 2,905 heavy-oil wells in Western Canada:\n"
                    "- **Daily production:** one row per well per day, with downtime hours, reasons and pump readings.\n"
                    "- **Well jobs:** one row per job (15,610), with job type and cost.\n"
                    "- **Production failures:** one row per logged failure (2,873), with cause and crew comments.")
    st.caption("Source: docs/Dataset_Handbook.md. The app reads only tables built from these files by "
               "build_artifacts.py.")
    st.page_link(ui.PAGES["limits"], label="See what the numbers cannot show: Assumptions & limits",
                 icon=":material/arrow_forward:")


def forest(rows, title, ref=1.0, xlabel="hazard ratio (log scale)"):
    """rows: list of (label, estimate, lo, hi). One dot + CI line per row; the reference line at 1 = no effect."""
    labels = [r[0] for r in rows]
    est = [r[1] for r in rows]
    fig = go.Figure(go.Scatter(
        x=est, y=labels, mode="markers", marker=dict(size=11, color=[ui.BLUE if h < ref else ui.ORANGE for _, _, _, h in rows]),
        error_x=dict(type="data", symmetric=False, array=[h - e for (_, e, _, h) in rows],
                     arrayminus=[e - lo for (_, e, lo, _) in rows], color=ui.MUTED, thickness=1.5, width=6),
        text=[f"{e:.2f} ({lo:.2f}–{h:.2f})" for (_, e, lo, h) in rows], hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.add_vline(x=ref, line=dict(color=ui.MUTED, width=1, dash="dot"))
    fig.update_layout(title=title, xaxis=dict(type="log", title=xlabel), yaxis=dict(autorange="reversed", automargin=True))
    return ui.style(fig, 70 + 44 * len(rows))


tab_q, tab_rod, tab_depth, tab_shock, tab_traps = st.tabs(
    ["Today's queue: 2026 replay", "At the pull: new string", "At the pull: break depth",
     "Between failures: whiplash test", "Traps we avoided"])

# ---------------------------------------------------------------- dispatch
with tab_q:
    rep, info = ui.art("dispatch_replay.csv"), ui.art("dispatch_info.json") or {}
    if rep is None:
        ui.require("dispatch_replay.csv")
    else:
        st.markdown(f"The queue was fitted on outages up to Dec 28, 2025, then re-run on every day from Jan 1 to "
                    f"Oct 23, 2026 ({info.get('tickets_test', 0):,} outages, {info.get('tickets_per_day', 0):.1f} per "
                    "day). Each day the top K outages are reviewed. The chart shows their share of the oil that all "
                    "outages went on to lose.")
        c1, c2 = st.columns([1.4, 2])
        outcome = c1.segmented_control("Measure", ["reconstructed exposure", "recorded loss"],
                                       default="reconstructed exposure", key="ev_outcome",
                                       help="Exposure = extra hours down × healthy rate. Recorded loss = the operator's "
                                            "own lost-oil field.") or "reconstructed exposure"
        kk = c2.select_slider("Outages reviewed per day (K)", options=sorted(rep["K"].unique()), value=2, key="ev_k")
        r = rep[rep["outcome"] == outcome]
        sel = r[r["K"] == kk].iloc[0]
        fig = go.Figure()
        for col, lab, color in (("first_day_loss", "rank by day-1 reported loss", ui.GRAY),
                                ("dispatch", "this queue", ui.BLUE), ("oracle", "perfect hindsight", ui.MUTED)):
            fig.add_trace(go.Scatter(x=r["K"], y=100 * r[col], mode="lines+markers", name=lab,
                                     line=dict(color=color, width=2.5, dash="dot" if col == "oracle" else None),
                                     marker=dict(size=8), hovertemplate=lab + ": %{y:.1f}% at %{x} a day<extra></extra>"))
        fig.add_vline(x=kk, line=dict(color=ui.MUTED, width=1))
        fig.update_layout(title=f"At {kk} a day this queue catches {100 * sel['dispatch']:.0f}% of the {outcome}, "
                                f"against {100 * sel['first_day_loss']:.0f}% for ranking by day-1 loss",
                          xaxis=dict(title="outages reviewed per day (K)", tickvals=sorted(rep["K"].unique())),
                          yaxis=dict(range=[0, 100], title=f"share of {outcome} caught (%)"))
        ui.show(ui.style(fig, 320))
        ui.explain(f"At {kk} a day this queue catches {100 * sel['dispatch']:.0f}%, ranking by day-1 loss "
                   f"{100 * sel['first_day_loss']:.0f}%, perfect hindsight {100 * sel['oracle']:.0f}%. The gap between the "
                   "blue and grey lines is the oil the queue saves.")
        st.caption("This queue was rebuilt from the team's written Dispatch spec. The original notebook is not in "
                   "this repo. The original report gave 52.7% vs 43.9% exposure and 50.6% vs 48.8% recorded loss "
                   "at K = 2.")

# ---------------------------------------------------------------- idea 1
with tab_rod:
    econ = ui.art("ideas/1/economics.json")
    if econ is None:
        ui.require("ideas/1/economics.json")
    else:
        st.markdown(f"**A new string halves the hazard of the next rod repair.** Cox model, stratified by area × year, "
                    f"adjusted for prior failures, pump speed (RPM) and liquid rate ({econ['n_cox']:,} rod jobs, "
                    f"{econ['events_cox']:,} repeat repairs).")
        names = {"is_replace": "new string (vs repair)", "log_prior": "prior repairs (log)",
                 "rpm100": "pump speed, per 100 RPM", "log_liq": "liquid rate (log)"}
        which = st.segmented_control("Wells in the model", ["All rod jobs", "Chronic wells (2+ prior repairs)"],
                                     default="All rod jobs", key="cox_which") or "All rod jobs"
        t = ui.art("ideas/1/cox_all.csv" if which == "All rod jobs" else "ideas/1/cox_chronic.csv")
        hr_new = t.loc[t["term"] == "is_replace", "HR"]
        ui.show(forest([(names.get(r.term, r.term), r.HR, r.HR_lo, r.HR_hi) for r in t.itertuples()],
                       (f"A new string has a hazard ratio of {hr_new.iloc[0]:.2f} for the next rod repair "
                        f"({which.lower()})" if len(hr_new) else
                        f"What changes the hazard of the next rod repair ({which.lower()})"),
                       xlabel="hazard ratio, log scale (below 1 = fewer repairs)"))
        ui.explain("Each dot is a hazard ratio with its 95% confidence interval. Left of the dotted line = fewer "
                   "repairs. The new string sits far to the left; prior repairs push the hazard up.")
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
            fig.update_layout(title="Rod repairs per producing year in the 365 days after the job", barmode="group",
                              xaxis_title="rod repairs in the 365 days before the job",
                              yaxis_title="rod repairs per year")
            ui.show(ui.style(fig, 320))
            ui.explain("Group wells by how often they failed before. In every group, wells that got a new string "
                       "(blue) failed less the following year.")
        with r:
            km = ui.art("ideas/1/km_chronic.csv")
            fig = go.Figure()
            for g, color in (("repair", ui.ORANGE), ("new rod string", ui.BLUE)):
                d = km[km["group"] == g]
                fig.add_trace(go.Scatter(x=d["t"], y=d["surv"], mode="lines", line=dict(color=color, width=2, shape="hv"),
                                         name=f"{g} (n={int(d['n'].iloc[0]) if len(d) else 0})"))
            fig.update_layout(title="Chronic rod wells: share still running without another rod repair",
                              xaxis_title="days since the job",
                              yaxis=dict(range=[0, 1], title="share of wells with no repair yet"))
            ui.show(ui.style(fig, 320))
            ui.explain("Higher line = more wells still running without another rod repair. The blue line stays higher.")

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
                              xaxis_title="consecutive breaks within 50 m (%)", yaxis_title="number of random runs",
                              showlegend=False)
            ui.show(ui.style(fig, 320))
            ui.explain("Grey = how often two breaks land within 50 m by chance (random pairs from the same area). "
                       "Red = how often it happens on the same well. Far outside the grey means it is not chance.")
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
            ui.explain("How often crews mention each word, by the cause that was coded. Some 'Fatigue' failures still "
                       "mention pitting, which points to corrosion fatigue.")
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
        if "cc_or" in v:
            rows = [("Shock index, before failure vs normal times (OR per SD)", v["cc_or"], v["cc_or_lo"], v["cc_or_hi"])]
            if "cox_shock_hr" in v:
                rows.append(("Shock index in the Cox model (HR per SD)", v["cox_shock_hr"], v["cox_shock_lo"], v["cox_shock_hi"]))
            ui.show(forest(rows, "Does volatile operation come before rod failures?", xlabel="odds / hazard ratio (log scale)"))
            ui.explain("A real signal would sit clearly right of the dotted line in both rows. The first is only just "
                       "right of it, the second straddles it, so the idea fails the rule we set before running it.")
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
                                  xaxis_title="difference in shock index (standard deviations)",
                                  yaxis_title="number of failures", showlegend=False)
                ui.show(ui.style(fig, 300))
        if perm is not None and len(perm):
            with r:
                fig = go.Figure(go.Histogram(x=perm["mean_diff"], nbinsx=40, marker_color=ui.GRAY))
                fig.add_vline(x=v.get("cc_mean_diff", 0), line=dict(color=ui.CRITICAL, width=2.5),
                              annotation_text="observed")
                fig.update_layout(title="Observed difference against random sign flips (what chance produces)",
                                  xaxis_title="mean difference in shock index (standard deviations)",
                                  yaxis_title="number of random runs", showlegend=False)
                ui.show(ui.style(fig, 300))
        st.caption(v.get("coverage", ""))

# ---------------------------------------------------------------- traps
with tab_traps:
    traps = [
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
    ]
    st.caption("Ways this data could have fooled us, and what we did about each.")
    cols = st.columns(2)
    for i, (trap, fix) in enumerate(traps):
        with cols[i % 2].container(border=True):
            st.markdown(f"**{trap}**")
            st.caption(fix)
