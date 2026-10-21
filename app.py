"""Optional Streamlit laboratory; all plotted data come from the same simulation engine."""

import io
import json
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import yaml

from agritwin_cps.config import SimulationConfig, load_config
from agritwin_cps.experiments.metrics import compute_metrics
from agritwin_cps.simulation.engine import simulate
from agritwin_cps.simulation.schema import artifact_schema
from agritwin_cps.visualization.plots import trajectory_figure

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="AgriTwin-CPS", layout="wide")
st.title("AgriTwin-CPS simulation laboratory")
st.caption("Synthetic greenhouse proxy model · No hardware validation · No reinforcement learning")
presets = sorted((ROOT / "configs").glob("*.yaml"))
selected = st.selectbox("Scenario preset", presets, format_func=lambda p: p.stem)
base = load_config(selected)
with st.form("experiment"):
    left, right = st.columns(2)
    seed = left.number_input("Random seed", min_value=0, value=base.seeds[0], step=1)
    steps = right.number_input(
        "Simulation steps", min_value=2, max_value=10000, value=min(base.steps, 10000), step=1
    )
    methods = st.multiselect(
        "Controllers", ["threshold", "twin_assisted"], default=["threshold", "twin_assisted"]
    )
    config_yaml = st.text_area(
        "Resolved configuration (YAML; units in model documentation)",
        yaml.safe_dump(base.model_dump(), sort_keys=False),
        height=280,
    )
    submitted = st.form_submit_button("Run experiment")

if submitted:
    try:
        values = yaml.safe_load(config_yaml)
        values.update(steps=int(steps), seeds=[int(seed)])
        config = SimulationConfig.model_validate(values)
        if not methods:
            raise ValueError("Select at least one controller")
        runs = {}
        with st.status("Running synthetic experiment", expanded=True) as status:
            for method in methods:
                result = simulate(config, int(seed), method)
                metrics, recovery = compute_metrics(result, config)
                runs[method] = (result, metrics, recovery)
                st.write(f"Completed {method}: {config.steps} simulation steps")
            status.update(label="Simulation complete", state="complete")
        st.session_state["experiment_result"] = (config, int(seed), runs)
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
        st.error(f"Invalid experiment configuration: {exc}")

if "experiment_result" in st.session_state:
    config, seed, runs = st.session_state["experiment_result"]
    st.write(f"Completed run: seed={seed}; dt={config.dt_seconds} s; steps={config.steps}")
    rows = [{"controller": method, **metrics} for method, (_, metrics, _) in runs.items()]
    comparison = pd.DataFrame(rows).set_index("controller")
    st.subheader("Computed simulation metrics")
    st.dataframe(
        comparison.astype(object).where(comparison.notna(), "Not measured / Not applicable"),
        width="stretch",
    )
    st.caption(
        "Empty metric cells mean Not measured / Not applicable. Settling time is not defined "
        "for the diurnal scenario. Recovery times may be right-censored; see event tables."
    )
    st.download_button(
        "Download comparison CSV", comparison.to_csv().encode(), "comparison.csv", "text/csv"
    )
    for method, (result, _metrics, recovery) in runs.items():
        with st.expander(f"{method}: trajectories, faults and errors", expanded=True):
            fig = trajectory_figure(result.trajectory)
            st.pyplot(fig)
            plt.close(fig)
            st.dataframe(recovery, width="stretch")
            st.download_button(
                f"Download {method} trajectory CSV",
                result.trajectory.to_csv(index=False).encode(),
                f"{method}_trajectory.csv",
                "text/csv",
            )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.yaml", yaml.safe_dump(config.model_dump(), sort_keys=False))
        archive.writestr("comparison.csv", comparison.to_csv())
        for method, (result, metrics, recovery) in runs.items():
            tables = {
                "trajectory": result.trajectory,
                "actuator_events": result.actuator_events,
                "observation_events": result.observation_events,
                "communication_events": result.communication_events,
                "recovery_events": recovery,
            }
            for name, table in tables.items():
                archive.writestr(f"{method}/{name}.csv", table.to_csv(index=False))
            archive.writestr(
                f"{method}/metrics.json", json.dumps(metrics, allow_nan=False, indent=2)
            )
            archive.writestr(
                f"{method}/schema.json",
                json.dumps(artifact_schema(result.trajectory.columns, metrics), indent=2),
            )
    st.download_button(
        "Download complete experiment ZIP",
        buffer.getvalue(),
        "agritwin_experiment.zip",
        "application/zip",
    )
else:
    st.info("Choose a scenario, review parameters, then select Run experiment.")
