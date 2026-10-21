"""AgriTwin-CPS Digital Twin Research Laboratory — optional local Streamlit interface."""

import os
from pathlib import Path

import streamlit as st

from agritwin_cps.ui.views import (
    experiment_comparison,
    header,
    initialize,
    overview,
    sidebar,
    simulation_lab,
    state_analysis,
)

ROOT = Path(__file__).resolve().parent
RESULTS = Path(os.environ.get("AGRITWIN_RESULTS_DIR", ROOT / "results"))
st.set_page_config(page_title="AgriTwin-CPS | Digital Twin Research Laboratory", layout="wide")
initialize(ROOT, RESULTS)
page = sidebar(RESULTS)
header()
if page == "Overview":
    overview(st.session_state.lab_experiment)
elif page == "Simulation Lab":
    simulation_lab(ROOT, RESULTS)
elif page == "State & Fault Analysis":
    state_analysis(st.session_state.lab_experiment)
else:
    experiment_comparison(st.session_state.lab_experiment, RESULTS)
