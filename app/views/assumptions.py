"""Assumptions & limits: what a judge or an operator should doubt, and how we would check it."""
import streamlit as st

import ui

st.title("Assumptions & limits")
econ = ui.art("ideas/1/economics.json") or {}
m5 = ui.art("ideas/5/metrics.json") or {}
v = ui.art("ideas/whiplash/verdict.json") or {}

rows = [
    ("The new-string effect is observational",
     f"HR {econ.get('hr_chronic', 0.495):.3f} comes from wells that operators chose to re-string. We adjust for prior "
     "failures, RPM, liquid rate, area and year, but unmeasured reasons for the choice could remain.",
     "Pilot: randomise 70 of the 145 program wells to a new string at the next pull, compare repair rates after 12 months."),
    ("Break depth covers 45% of rod failures",
     f"{m5.get('located_total', 983):,} of {m5.get('rod_failures', 2186):,} rod failures have a parsable depth. "
     "Only a 15-row spot check of the parser so far.",
     "Hand-label 100 random rows; report parser precision and recall before acting on a depth band."),
    ("Section replacement saves 40%", "The saving of a section job vs a full string is an assumption, not in the data.",
     "Get the actual cost split from a rod supplier or from three recent section jobs."),
    ("15% field-gate haircut on WCS", "No Strathcona netback was provided. The default price is WCS Hardisty less 15%.",
     "Every $ figure follows the sidebar price slider."),
    ("Revenue, not margin", "Lost oil is valued at the field-gate price, not at the margin after operating cost.",
     "Use the slider at a margin price for a conservative case; the program still pays back (see sensitivity)."),
    ("Posting lag", "Downtime and jobs are entered after the fact; the queue assumes day D is complete at its close.",
     "Run the queue on the morning of D+1, which is how the replay is set up."),
    ("Daily data cannot see short shocks",
     "The shock index uses day-to-day changes in daily readings; stick-slip and torque spikes last seconds. "
     + (f"Whiplash verdict: {'kept' if v.get('keep') else 'not supported at daily resolution'}." if v else ""),
     "Hourly torque and current from automated tags (the data-quality recommendation)."),
    ("Dispatch queue is a reconstruction",
     "The original Dispatch notebook is not in this repo; the queue was rebuilt from its written spec and lands within "
     "about 1-2 points of the reported capture.", "Swap in the original code when available; the page reads one table."),
    ("Chronic list is a snapshot", f"As of {econ.get('asof', '2026-10-27')}. Wells move on and off as repairs age out.",
     "Rebuild artifacts weekly (`build_artifacts.py`)."),
]
for title, what, check in rows:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.write(what)
        st.caption(f"How we would check it: {check}")
