"""Evidence: why each decision is trustworthy, and the idea we tested and rejected. Written for a reader with no
statistics background: every tab says the question, the answer in plain words, how it was tested, and how to read
each chart."""
import numpy as np
import plotly.graph_objects as go
import streamlit as st

import ui

top_slot = ui.header(
    "Can you trust these numbers?",
    how=["Read where the numbers come from, just below.",
         "Read the cards next: one line per claim and whether the data backs it.",
         "Open a tab for the proof behind one claim. Each tab starts with the question, the answer and how we "
         "tested it.",
         "Under every chart, a note says how to read it.",
         "For what the numbers cannot show, open Assumptions & limits."],
    extra_terms={
        "Hazard ratio (HR)": "How much faster something happens in one group than another. 1 = same speed, 0.5 = half "
                             "as often, 2 = twice as often.",
        "Odds ratio (OR)": "The same idea for 'was it higher before a failure?' comparisons. 1 = no difference.",
        "95% range (confidence interval, CI)": "The range the true value very likely sits in. If the range crosses 1, "
                                               "we cannot tell the effect apart from no effect.",
        "Cox model": "A standard way to compare how long things last (here: time to the next rod repair) while "
                     "accounting for other differences between wells, such as how often they failed before.",
        "Permutation test": "Shuffle the data many times so any real pattern is destroyed, and see how often chance "
                            "alone matches what we observed. Rarely = the pattern is real.",
        "p-value": "The chance of seeing a result this strong if there were no real effect. Below 0.05 is the usual "
                   "bar.",
        "Replay (backtest)": "Fit on the past, then run day by day on a later period the method never saw.",
        "K": "The number of outages reviewed per day.",
        "RPM": ui.TERMS["RPM"]})

econ = ui.art("ideas/1/economics.json") or {}
m5 = ui.art("ideas/5/metrics.json") or {}
v = ui.art("ideas/whiplash/verdict.json") or {}
rep = ui.art("dispatch_replay.csv")
dinfo = ui.art("dispatch_info.json") or {}


def answer(question: str, finding: str, how: str, ok: bool = True):
    """The header of every tab: the question, the answer in one sentence, and how it was tested."""
    with st.container(border=True):
        st.markdown(f"**Question.** {question}")
        (st.success if ok else st.warning)(finding, icon=":material/check_circle:" if ok else ":material/cancel:")
        st.markdown(f"**How we tested it.** {how}")


def forest(rows, title, ref=1.0, xlabel="hazard ratio (log scale)"):
    """rows: list of (label, estimate, lo, hi). One dot + range line per row; the dotted line at 1 = no effect."""
    labels = [r[0] for r in rows]
    fig = go.Figure(go.Scatter(
        x=[r[1] for r in rows], y=labels, mode="markers",
        marker=dict(size=11, color=[ui.BLUE if h < ref else ui.ORANGE if lo > ref else ui.GRAY for _, _, lo, h in rows]),
        error_x=dict(type="data", symmetric=False, array=[h - e for (_, e, _, h) in rows],
                     arrayminus=[e - lo for (_, e, lo, _) in rows], color=ui.MUTED, thickness=1.5, width=6),
        text=[f"{e:.2f} (95% range {lo:.2f}–{h:.2f})" for (_, e, lo, h) in rows],
        hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.add_vline(x=ref, line=dict(color=ui.MUTED, width=1, dash="dot"), annotation_text="1 = no effect",
                  annotation_position="top")
    lo_all, hi_all = min(min(r[2] for r in rows), ref), max(max(r[3] for r in rows), ref)
    ticks = [t for t in (0.25, 0.33, 0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 2, 3, 4) if lo_all * 0.9 <= t <= hi_all * 1.1]
    fig.update_layout(title=title, xaxis=dict(type="log", title=xlabel, tickvals=ticks, ticktext=[f"{t:g}" for t in ticks],
                                              range=[np.log10(lo_all * 0.85), np.log10(hi_all * 1.15)]),
                      yaxis=dict(autorange="reversed", automargin=True))
    return ui.style(fig, 90 + 44 * len(rows))


# ---------------------------------------------------------------- overview cards
cards = []
if rep is not None:
    r2 = rep[(rep["outcome"] == "reconstructed exposure") & (rep["K"] == 2)]
    if len(r2):
        r2 = r2.iloc[0]
        cards.append(("Today's queue", True, f"Reviewing the queue's top 2 outages a day catches "
                      f"{100 * r2['dispatch']:.0f}% of the oil at stake, vs {100 * r2['first_day_loss']:.0f}% when "
                      "ranking by the first day's loss."))
if econ:
    cards.append(("New rod string", True, f"After a new string, the next rod repair comes at about "
                  f"{econ['hr_all']:.2f}× the rate seen after a repair: about {1 - econ['hr_all']:.0%} fewer repairs."))
if m5:
    cards.append(("Break depth", True, f"A well's next break lands within 50 m of its last one "
                  f"{100 * m5['share_within_50m']:.0f}% of the time, vs {100 * m5['baseline_share_within_50m']:.0f}% "
                  "by chance."))
if v:
    cards.append(("Whiplash (rejected)", bool(v.get("keep")),
                  "Day-to-day swings in pump speed and torque do not predict rod failures in this data, so we "
                  "left the idea out of the app." if not v.get("keep") else "Kept as a watch signal."))
n_ok = sum(ok for _, ok, _ in cards)
if cards:
    ui.summary(top_slot, f"<b>{n_ok} of {len(cards)}</b> claims hold up in the data. "
               + ("The whiplash idea did not, so the app leaves it out. " if v and not v.get("keep") else "")
               + "Each tab below shows the test behind one claim.")

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
    st.caption("The app reads only tables built by build_artifacts.py --demo." if ui.is_demo() else
               "Source: docs/Dataset_Handbook.md. The app reads only tables built from these files by "
               "build_artifacts.py.")
    st.page_link(ui.PAGES["limits"], label="See what the numbers cannot show: Assumptions & limits",
                 icon=":material/arrow_forward:")

cols = st.columns(len(cards) or 1)
for c, (name, ok, text) in zip(cols, cards):
    with c.container(border=True):
        st.markdown(f"{':material/check_circle:' if ok else ':material/cancel:'} **{name}**")
        st.caption(text)

tab_q, tab_rod, tab_depth, tab_shock, tab_traps = st.tabs(
    ["Today's queue", "New rod string", "Break depth", "Whiplash (rejected)", "Traps we avoided"])

# ---------------------------------------------------------------- dispatch
with tab_q:
    if rep is None:
        ui.require("dispatch_replay.csv")
    else:
        answer("When several outages are reported in a day, does the queue put the costly ones first?",
               f"Yes. Out of about {dinfo.get('tickets_per_day', 0):.0f} new outages a day, the queue's top picks go on to lose more oil than the outages "
               "with the biggest first-day loss.",
               f"We built the queue from outages up to 28 Dec 2025, then replayed it on every day from 1 Jan to "
               f"23 Oct 2026 ({dinfo.get('tickets_test', 0):,} outages it had never seen). Each day we took the top K "
               "and asked: what share of all the oil those outages went on to lose did they account for?")
        c1, c2 = st.columns([1.4, 2])
        outcome = c1.segmented_control(
            "Measure of lost oil", ["reconstructed exposure", "recorded loss"], required=True, default="reconstructed exposure",
            key="ev_outcome", help="Reconstructed exposure = extra hours down × the well's normal rate (our estimate). "
                                   "Recorded loss = the lost-oil number the operator entered.") or "reconstructed exposure"
        kk = c2.select_slider("Outages reviewed per day (K)", options=sorted(rep["K"].unique()), value=2, key="ev_k")
        r = rep[rep["outcome"] == outcome]
        sel = r[r["K"] == kk].iloc[0]
        t1, t2, t3 = st.columns(3)
        t1.metric("This queue catches", f"{100 * sel['dispatch']:.0f}%",
                  f"+{100 * (sel['dispatch'] - sel['first_day_loss']):.1f} points vs day-1 ranking", delta_arrow="off",
                  delta_color="off")
        t2.metric("Ranking by first-day loss", f"{100 * sel['first_day_loss']:.0f}%", "what a person would do today",
                  delta_arrow="off", delta_color="off")
        t3.metric("Perfect hindsight", f"{100 * sel['oracle']:.0f}%", "the best any ranking could do",
                  delta_arrow="off", delta_color="off")
        fig = go.Figure()
        for col, lab, color in (("first_day_loss", "rank by first-day loss", ui.GRAY),
                                ("dispatch", "this queue", ui.BLUE), ("oracle", "perfect hindsight", ui.MUTED)):
            fig.add_trace(go.Scatter(x=r["K"], y=100 * r[col], mode="lines+markers", name=lab,
                                     line=dict(color=color, width=2.5, dash="dot" if col == "oracle" else None),
                                     marker=dict(size=8), hovertemplate=lab + ": %{y:.1f}% at %{x} a day<extra></extra>"))
        fig.add_vline(x=kk, line=dict(color=ui.MUTED, width=1))
        fig.update_layout(title=f"At {kk} a day the queue catches {100 * sel['dispatch']:.0f}% of the oil at stake, "
                                f"against {100 * sel['first_day_loss']:.0f}% for first-day ranking",
                          xaxis=dict(title="outages reviewed per day (K)", tickvals=sorted(rep["K"].unique())),
                          yaxis=dict(range=[0, 100], title="share of the oil at stake caught (%)"))
        ui.show(ui.style(fig, 320))
        ui.explain("Higher is better. Blue above grey = the queue picks costlier outages than ranking by first-day "
                   "loss. The dotted line is the ceiling. Switch the measure: the lead is larger on our exposure "
                   "estimate than on the operator's recorded loss, so read the recorded-loss gap as the cautious one.")
        with st.expander("Technical details"):
            st.markdown("- Score = expected extra downtime for the outage's reason and how long it has been down so "
                        "far (reasons with few cases are pulled toward the average) × the well's normal daily rate.\n"
                        "- The original Dispatch notebook is not in this repo; this is a rebuild from its written "
                        "spec. The original report gave 52.7% vs 43.9% (exposure) and 50.6% vs 48.8% (recorded loss) "
                        "at K = 2. The rebuild lands within 1–2 points with the same lead.")

# ---------------------------------------------------------------- idea 1
with tab_rod:
    if not econ:
        ui.require("ideas/1/economics.json")
    else:
        answer("On a well that keeps breaking rods, does running a whole new rod string reduce the next repairs, "
               "or is it the same as another repair?",
               f"It works. After a new string, the next rod repair comes at {econ['hr_all']:.2f}× the rate seen after "
               f"an ordinary repair (95% range {econ['hr_all_lo']:.2f}–{econ['hr_all_hi']:.2f}), about "
               f"{1 - econ['hr_all']:.0%} fewer repairs. The same holds on the chronic wells alone.",
               f"We followed {econ['n_cox']:,} rod jobs from 2022 to 2026 and timed how long each well ran before its "
               f"next rod repair ({econ['events_cox']:,} repeats). A Cox model compares new strings with repairs on "
               "wells in the same area and year, with the same failure history, pump speed and liquid rate.")
        names = {"is_replace": "new string instead of a repair", "log_prior": "more repairs in the prior year",
                 "rpm100": "pump speed +100 RPM", "log_liq": "more liquid produced"}
        which = st.segmented_control("Wells in the model", ["All rod jobs", "Chronic wells (2+ prior repairs)"],
                                     required=True, default="All rod jobs", key="cox_which") or "All rod jobs"
        t = ui.art("ideas/1/cox_all.csv" if which == "All rod jobs" else "ideas/1/cox_chronic.csv")
        ui.show(forest([(names.get(x.term, x.term), x.HR, x.HR_lo, x.HR_hi) for x in t.itertuples()],
                       f"What speeds up or slows down the next rod repair ({which.lower()})",
                       xlabel="hazard ratio, log scale (left of 1 = fewer repairs, right = more)"))
        ui.explain("Each dot is one factor, the line through it is its 95% range. Blue = clearly fewer repairs, orange = "
                   "clearly more, grey = can't tell. A new string sits well left of 1 (fewer repairs); a history of "
                   "repairs pushes right. Pump speed itself barely matters, which is why the Whiplash test looked at "
                   "speed swings instead.")
        l, r = st.columns(2)
        with l:
            tab = ui.art("ideas/1/rate_by_history.csv")
            fig = go.Figure()
            for k, lab, color in ((0, "after a repair", ui.ORANGE), (1, "after a new string", ui.BLUE)):
                g = tab[tab["is_replace"] == k]
                fig.add_trace(go.Bar(x=g["prior_bin"].astype(str), y=g["rate"], name=lab, marker_color=color,
                                     error_y=dict(type="data", symmetric=False, array=g["hi"] - g["rate"],
                                                  arrayminus=g["rate"] - g["lo"], color=ui.MUTED),
                                     customdata=g["n"], hovertemplate="%{y:.2f} repairs/yr (%{customdata} jobs)<extra></extra>"))
            fig.update_layout(title="Rod repairs in the year after the job", barmode="group",
                              xaxis_title="rod repairs in the year before the job", yaxis_title="repairs per year")
            ui.show(ui.style(fig, 320))
            ui.explain("Wells are grouped by how often they broke before (left = rarely, right = 5+ times). In every "
                       "group the blue bar (new string) is lower than the orange bar (repair). Raw counts, no model.")
        with r:
            km = ui.art("ideas/1/km_chronic.csv")
            fig = go.Figure()
            for g, lab, color in (("repair", "after a repair", ui.ORANGE), ("new rod string", "after a new string", ui.BLUE)):
                d = km[km["group"] == g]
                fig.add_trace(go.Scatter(x=d["t"], y=100 * d["surv"], mode="lines",
                                         line=dict(color=color, width=2, shape="hv"),
                                         name=f"{lab} ({int(d['n'].iloc[0]) if len(d) else 0:,} jobs)",
                                         hovertemplate="day %{x:.0f}: %{y:.0f}% still running<extra></extra>"))
            fig.update_layout(title="Chronic wells: % still running with no new rod repair",
                              xaxis_title="days since the job", yaxis=dict(range=[0, 100], title="% still running"))
            ui.show(ui.style(fig, 320))
            ui.explain("Every line starts at 100% on the day of the job and drops each time a well needs another rod "
                       "repair. The blue line (new string) stays higher for longer: those wells run longer between "
                       "failures.")
        st.caption("Wells that got a new string may differ in ways the data does not record (operators chose them). "
                   "The Assumptions page says how a pilot would confirm the effect.")

# ---------------------------------------------------------------- idea 5
with tab_depth:
    if not m5:
        ui.require("ideas/5/metrics.json")
    else:
        answer("When a rod string breaks again, does it break in the same place? If so, a section of new rods "
               "(plus guides) could replace a whole string.",
               f"Often, yes. Consecutive breaks on a well land within 50 m of each other "
               f"{100 * m5['share_within_50m']:.0f}% of the time, {m5['lift']:.1f}× what chance gives. "
               f"{m5['program_wells_band_le_150']} of the {m5['program_wells_2plus']} program wells with 2+ located "
               "breaks have all of them inside a 150 m band.",
               f"Crew notes often say where the rod broke ('Broken corod @ 247m', 'parted at joint 42'). We read a "
               f"depth out of {m5['located_total']:,} of {m5['rod_failures']:,} rod failures ({m5['located_pct']:.0f}%), "
               "then compared each well's consecutive breaks with random pairs of breaks from the same area.")
        a, b, c = st.columns(3)
        a.metric("Rod failures with a depth", f"{m5['located_total']:,}", f"{m5['located_pct']:.0f}% of {m5['rod_failures']:,}",
                 delta_arrow="off", delta_color="off")
        b.metric("Next break within 50 m", f"{100 * m5['share_within_50m']:.0f}%",
                 f"vs {100 * m5['baseline_share_within_50m']:.0f}% by chance", delta_arrow="off", delta_color="off")
        c.metric("Program wells in one ≤150 m band", m5["program_wells_band_le_150"],
                 f"of {m5['program_wells_2plus']} with 2+ located breaks", delta_arrow="off", delta_color="off")
        l, r = st.columns(2)
        with l:
            perm = ui.art("ideas/5/perm_share.csv")
            fig = go.Figure(go.Histogram(x=100 * perm["share_within_50m"], nbinsx=30, marker_color=ui.GRAY,
                                         hovertemplate="%{x:.0f}%: %{y} shuffles<extra></extra>"))
            fig.add_vline(x=100 * m5["share_within_50m"], line=dict(color=ui.CRITICAL, width=2.5),
                          annotation_text=f"actual wells: {100 * m5['share_within_50m']:.0f}%")
            fig.update_layout(title="Same-place repeats: real wells vs 1,000 random shuffles",
                              xaxis_title="% of consecutive breaks within 50 m", yaxis_title="number of shuffles",
                              showlegend=False)
            ui.show(ui.style(fig, 320))
            ui.explain("Grey = 1,000 shuffles where breaks were paired at random within the same area: chance alone "
                       f"gives about {100 * m5['baseline_share_within_50m']:.0f}%. The red line is what real wells do. "
                       + ("Not one shuffle came close, so the repeats are not chance." if m5.get("perm_p", 1) < 0.01 else
                          f"Shuffle p-value {m5.get('perm_p', 1):.3f}."))
        with r:
            kw = ui.art("ideas/5/keywords_by_cause.csv")
            words = [("kw_pitting", "pitting"), ("kw_corrosion", "corrosion"), ("kw_wear", "wear"),
                     ("kw_guides_centralizers", "guides")]
            fig = go.Figure()
            for cause, color in (("Fatigue", ui.BLUE), ("Corrosion", ui.CRITICAL), ("Load / Excess Stress", ui.ORANGE)):
                row = kw[kw["cause"] == cause]
                if len(row):
                    fig.add_trace(go.Bar(x=[w for _, w in words], y=[row[k].iloc[0] for k, _ in words],
                                         name=f"coded {cause}", marker_color=color,
                                         hovertemplate="%{y:.0f}% mention '%{x}'<extra>coded " + cause + "</extra>"))
            fig.update_layout(title="What crews wrote, by the failure cause that was coded", barmode="group",
                              yaxis_title="% of crew notes mentioning the word")
            ui.show(ui.style(fig, 320))
            ui.explain(f"Each bar = how often crew notes use that word. {m5['fatigue_mention_pit_corr']} failures coded "
                       "'Fatigue' still mention pitting or corrosion, so corrosion may be under-counted. That is why "
                       "the corrosion advice also reads the crew text, not only the code.")
        with st.expander("How depths are read from crew text"):
            st.markdown("- '@ 247m' style depths are read directly; joint numbers on stick rods are converted at 7.62 m "
                        "per joint.\n"
                        "- Job summaries count only when a break word and a metre unit appear together, so pull weights "
                        "('free at 15,000 lbs') are not mistaken for depths.\n"
                        "- Two records of the same break (less than 7 days apart) are counted once.\n"
                        "- So far the parser has been spot-checked on 15 rows; hand-labelling 100 is the next step.")

# ---------------------------------------------------------------- whiplash
with tab_shock:
    if not v:
        st.info("The Mechanical Whiplash test has not been run on this data yet "
                "(`python build_artifacts.py --only whiplash`).")
    else:
        keep = bool(v.get("keep"))
        finding = ("Kept as a watch signal: both tests pointed the same way." if keep else
                   f"No, so we left it out. Before a failure, wells were only slightly more volatile than usual "
                   f"(odds ratio {v.get('cc_or', 0):.2f}), and once the well's failure history is taken into account "
                   f"the volatility adds nothing (hazard ratio {v.get('cox_shock_hr', 0):.2f}, range "
                   f"{v.get('cox_shock_lo', 0):.2f}–{v.get('cox_shock_hi', 0):.2f}, which includes 1).")
        answer("Do sudden day-to-day swings in pump speed, torque, motor current and run hours ('whiplash') warn of a "
               "rod failure?", finding,
               "Before looking at results we wrote down the rule: keep the idea only if (1) wells are clearly more "
               "volatile in the month before a failure than in their own normal months, and (2) volatility still "
               "predicts failures inside the new-string Cox model. Both had to pass.", ok=keep)
        st.markdown("**The shock index.** For each well and day: how far today's swings in RPM, torque, current and run "
                    "hours are from that well's own usual swings, averaged into one number (0 = normal for this well, "
                    "positive = choppier than usual). It uses only data from before the day it describes.")
        if "cc_or" in v:
            rows = [("Test 1: month before a failure vs the same well's normal months", v["cc_or"], v["cc_or_lo"],
                     v["cc_or_hi"])]
            if "cox_shock_hr" in v:
                rows.append(("Test 2: added to the new-string Cox model", v["cox_shock_hr"], v["cox_shock_lo"],
                             v["cox_shock_hi"]))
            ui.show(forest(rows, "Does choppy operation come before rod failures?",
                           xlabel="odds / hazard ratio per step up in the shock index (log scale)"))
            p1 = v["cc_or_lo"] > 1 and v.get("cc_p", 1) < 0.05 and v.get("cc_perm_p", 1) < 0.05
            p2 = v.get("cox_shock_lo", 0) > 1
            ui.explain("To pass, both dots and their full ranges had to sit right of the dotted line. "
                       f"Test 1 {'passes' if p1 else 'fails'}"
                       + (" (just right of it: a weak effect)" if p1 and v["cc_or"] < 1.2 else "") + "; "
                       f"test 2 {'passes' if p2 else 'fails'}"
                       + ("" if p2 else " (no effect once failure history is known)") + ". "
                       + ("Both pass = kept." if keep else "Both must pass, so the idea is rejected."))
        cc = ui.art("ideas/whiplash/case_crossover_pairs.csv")
        perm = ui.art("ideas/whiplash/perm_null.csv")
        l, r = st.columns(2)
        if cc is not None and len(cc):
            with l:
                fig = go.Figure(go.Histogram(x=cc["diff"], nbinsx=40, marker_color=ui.BLUE,
                                             hovertemplate="%{x:.2f}: %{y} failures<extra></extra>"))
                fig.add_vline(x=0, line=dict(color=ui.MUTED, width=1))
                fig.add_vline(x=cc["diff"].mean(), line=dict(color=ui.CRITICAL, width=2),
                              annotation_text=f"average {cc['diff'].mean():+.3f}")
                fig.update_layout(title="Each failure: shock index before it minus the same well's normal",
                                  xaxis_title="difference (right = choppier before the failure)",
                                  yaxis_title="number of failures", showlegend=False)
                ui.show(ui.style(fig, 300))
                ui.explain(f"One count per rod failure ({len(cc):,}). If whiplash warned of failures, the pile would sit "
                           f"clearly right of 0. Here the average difference is {cc['diff'].mean():+.3f}.")
        if perm is not None and len(perm):
            with r:
                fig = go.Figure(go.Histogram(x=perm["mean_diff"], nbinsx=40, marker_color=ui.GRAY,
                                             hovertemplate="%{x:.3f}: %{y} shuffles<extra></extra>"))
                fig.add_vline(x=v.get("cc_mean_diff", 0), line=dict(color=ui.CRITICAL, width=2.5),
                              annotation_text="actual")
                fig.update_layout(title="Actual average vs random shuffles", xaxis_title="average difference",
                                  yaxis_title="number of shuffles", showlegend=False)
                ui.show(ui.style(fig, 300))
                ui.explain("Grey = what the average looks like when 'before' and 'normal' are swapped at random. "
                           + ("The actual value is out at the edge, so the small difference is real, but it is too small "
                              "to act on." if v.get("cc_perm_p", 1) < 0.05 else
                              "The actual value sits inside the grey, so it is what chance gives.")
                           + f" (shuffle p-value {v.get('cc_perm_p', 1):.3f})")
        with st.expander("Why daily data may be too coarse, and the technical summary"):
            st.markdown(f"- {v.get('coverage', '')}\n"
                        "- Stick-slip and torque spikes last seconds; daily manual readings cannot see them. Hourly "
                        "automated tags would be the fair test.\n"
                        "- The 'before' window ends 7 days before each failure, so operators slowing a struggling well "
                        "in its last days cannot create a false signal.")
            st.caption(f"Technical: {v.get('summary', '')}")

# ---------------------------------------------------------------- traps
with tab_traps:
    st.markdown("**Ways this data could have fooled us, and what we did about each.** Each card names a trap in the "
                "data, then (in grey) the fix.")
    traps = [
        ("The failure log only starts mid-2025", "Rod events come from the job records (2021–26), which go back "
                                                 "further; tests that need the failure log start in Jun 2025."),
        ("Old 'Rod Repair' jobs show C$0 cost", "Repair cost = average of jobs with a cost above zero, 2023 onward."),
        ("One pull can appear as several job rows", "Jobs within 3 days on the same well are merged into one event; "
                                                    "if any row is a new string, the event counts as one."),
        ("2021 jobs have no prior history to count", "Prior-repair counts are used only for jobs from 2022 on."),
        ("Wells that got new strings may be different wells", "The model compares wells in the same area and year, "
                                                              "with the same failure history, pump speed and liquid rate."),
        ("Pull weights could be read as depths ('free at 15,000 lbs')", "A depth needs a break word and a metre unit "
                                                                         "together."),
        ("A duplicated failure record looks like a repeat break", "Break pairs on the same well less than 7 days "
                                                                  "apart are dropped."),
        ("Operators slow down wells that are already failing", "The whiplash 'before' window ends 7 days before the "
                                                               "failure, so that slowdown is not counted."),
        ("Tuning on the period you test on", "The queue was fitted up to 28 Dec 2025 and tested on 2026; whiplash "
                                             "windows and keep rule were fixed before running."),
        ("Manual readings carried forward look like steady running", "Repeated RPM / torque values are flagged; "
                                                                     "volatility is only measured where readings change."),
        ("Uneconomic shut-ins inflate 'lost oil'", "Wells shut in on purpose are left out of lost oil and the queue."),
    ]
    cols = st.columns(2)
    for i, (trap, fix) in enumerate(traps):
        with cols[i % 2].container(border=True):
            st.markdown(f"**{trap}**")
            st.caption(fix)
