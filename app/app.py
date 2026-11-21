"""Entry point.  streamlit run app/app.py

One platform, three decisions on three time horizons:
  Today            -> Today's Queue: which newly reported outage to review first (Dispatch)
  At the pull      -> Well Card + Replacement Program: full string, section, inhibitor (Ideas 1 + 5)
  Between failures -> Field monitor (failure early warning) and the Mechanical Whiplash test
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui  # noqa: E402

st.set_page_config(page_title="Predict the Break, Protect the Barrel", layout="wide", page_icon=":material/oil_barrel:")

HERE = Path(__file__).resolve().parent
ui.PAGES.update({
    "queue": st.Page(str(HERE / "views" / "queue.py"), title="Today's queue", icon=":material/assignment:", default=True),
    "facility": st.Page(str(HERE / "views" / "facility.py"), title="Facility restarts", icon=":material/factory:"),
    "well": st.Page(str(HERE / "views" / "well_card.py"), title="Well card", icon=":material/oil_barrel:"),
    "program": st.Page(str(HERE / "views" / "program.py"), title="Replacement program", icon=":material/construction:"),
    "monitor": st.Page(str(HERE / "dashboard.py"), title="Field monitor", icon=":material/monitoring:"),
    "evidence": st.Page(str(HERE / "views" / "evidence.py"), title="Evidence", icon=":material/science:"),
    "limits": st.Page(str(HERE / "views" / "assumptions.py"), title="Assumptions & limits", icon=":material/rule:"),
})
nav = st.navigation({
    "Today": [ui.PAGES["queue"], ui.PAGES["facility"]],
    "At the pull": [ui.PAGES["well"], ui.PAGES["program"]],
    "Between failures": [ui.PAGES["monitor"]],
    "Proof": [ui.PAGES["evidence"], ui.PAGES["limits"]],
})
ui.sidebar()
nav.run()
