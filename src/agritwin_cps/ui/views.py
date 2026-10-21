"""Streamlit workspace views. Simulation, metrics and statistics remain in their core modules."""

import json
import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from agritwin_cps.ui.configuration import configuration, new_draft
from agritwin_cps.ui.diagnostics import STAGES, evidence_timeline, fallback_conditions
from agritwin_cps.ui.workspace import (
    CONTROLLERS,
    ESTIMATORS,
    ExperimentRecord,
    RunRecord,
    comparison_json,
    comparison_sources,
    execute_experiment,
    experiment_archive,
    load_experiment,
    load_run,
    saved_experiments,
)
from agritwin_cps.visualization.plots import (
    control_actions_figure,
    environment_figure,
    estimation_error_figure,
    fault_timeline_figure,
    metric_comparison_figure,
)

PAGES = ("Overview", "Simulation Lab", "State & Fault Analysis", "Experiment Comparison")

# Metric names are the existing metrics.json keys, never newly defined UI calculations.
METRICS = {
    "Environmental control": {
        "temperature_violation_seconds": (
            "Temperature violation duration",
            "s",
            "Lower is preferable",
        ),
        "humidity_violation_seconds": ("Humidity violation duration", "s", "Lower is preferable"),
        "moisture_violation_seconds": (
            "Soil moisture violation duration",
            "s",
            "Lower is preferable",
        ),
        "any_safe_range_violation_seconds": (
            "Any environmental violation",
            "s",
            "Lower is preferable",
        ),
    },
    "State estimation": {
        **{
            f"{metric}_{channel}": (f"{channel.title()} {metric.upper()}", unit, direction)
            for channel, unit in (
                ("temperature", "°C"),
                ("humidity", "%RH"),
                ("moisture", "fraction"),
            )
            for metric, direction in (
                ("mae", "Lower is preferable"),
                ("rmse", "Lower is preferable"),
                ("bias", "Closer to zero is preferable"),
            )
        },
        **{
            f"valid_observation_coverage_{c}": (
                f"{c.title()} observation coverage",
                "fraction",
                "Higher means more accepted observations",
            )
            for c in ("temperature", "humidity", "moisture")
        },
    },
    "Actuation": {
        "irrigation_amount_fraction": (
            "Irrigation input proxy",
            "soil-water fraction input",
            "Lower input is not automatically better; inspect soil safety",
        ),
        "ventilation_effort_hours": (
            "Ventilation effort proxy",
            "equivalent full-action h",
            "Lower effort is not automatically better; inspect safety",
        ),
        **{
            f"{a}_{metric}_count": (
                f"{a.title()} {metric} count",
                "count",
                "Fewer actions are not automatically better; inspect safety",
            )
            for a in ("ventilation", "irrigation")
            for metric in ("activation", "switch")
        },
        "failed_actuator_command_count": (
            "Failed actuator commands",
            "count",
            "Lower is preferable",
        ),
        "limited_actuator_command_count": (
            "Rate-limited commands",
            "count",
            "Constraint events, not faults",
        ),
    },
    "Reliability & recovery": {
        **{
            f"{kind}_estimation_recovery_seconds": (
                f"{kind.title()} estimation recovery",
                "s",
                "Lower is preferable; conditional on observed recovery",
            )
            for kind in ("sensor", "local", "remote")
        },
        "remote_resync_seconds": ("Remote resynchronization delay", "s", "Lower is preferable"),
        "stale_local_data_seconds": ("Stale local data duration", "s", "Lower is preferable"),
        "stale_remote_data_seconds": ("Stale remote data duration", "s", "Lower is preferable"),
        "local_control_continuity": (
            "Local control continuity",
            "fraction",
            "Higher is preferable",
        ),
        **{
            f"{kind}_recovery_censored_count": (
                f"{kind.title()} censored recoveries",
                "count",
                "Events without observed estimation recovery",
            )
            for kind in ("sensor", "local", "remote")
        },
        "remote_resync_censored_count": (
            "Censored remote resynchronizations",
            "count",
            "Events without an observed fresh delivery",
        ),
        "settling_time_seconds": ("Settling time", "s", "N/A for the diurnal model"),
    },
}

STYLE = """
<style>
.lab-kicker {font-size:.72rem;letter-spacing:.15em;font-weight:650;color:#86868B;
             text-transform:uppercase;margin-bottom:.45rem}
.lab-heading {font-size:2.25rem;line-height:1.2;letter-spacing:-.04em;font-weight:700;
              margin:0;color:#1D1D1F}
.lab-intro {font-size:.98rem;color:#6E6E73;max-width:850px;margin:.65rem 0 1rem}
.lab-tag {display:inline-block;border:1px solid #D2D2D7;border-radius:4px;padding:4px 9px;
          font-size:.74rem;font-weight:600;letter-spacing:.02em;background:#F5F5F7;color:#515154}
.lab-empty {padding:2.4rem 1.5rem;border:1px dashed #D2D2D7;border-radius:6px;
            color:#6E6E73;text-align:center;margin:1rem 0}
.lab-empty strong {display:block;font-size:1.12rem;color:#1D1D1F;margin-bottom:.5rem}
</style>
"""

FLOW = """digraph {
 graph [rankdir=LR bgcolor="transparent" pad="0.1" nodesep="0.35" ranksep="0.55"]
 node [shape=box style="rounded,filled" fillcolor="#F5F5F7" color="#D2D2D7"
       fontname="Helvetica" fontsize=11 fontcolor="#1D1D1F" margin="0.13,0.1"]
 edge [color="#86868B" arrowsize=0.7 fontname="Helvetica" fontsize=9 fontcolor="#86868B"]
 plant [label="Greenhouse model\nSimulation truth"]
 sensors [label="Virtual sensors"]
 valid [label="Local sensor link\nInput validation"]
 twin [label="State estimator\nIndependent prediction"]
 control [label="Local controller\nThreshold or twin-assisted"]
 actuator [label="Constrained\nactuators"]
 remote [label="Remote link\nMonitoring cache" fillcolor="#F5F5F7"]
 faults [label="Fault injection" fillcolor="#EEEEF0"]
 evaluation [label="Evaluation\nTruth vs estimate" fillcolor="#F5F5F7"]
 weather [label="Synthetic weather"]
 plant -> sensors -> valid -> twin -> control -> actuator -> plant
 valid -> control [label="threshold baseline"]
 actuator -> twin [label="applied feedback" constraint=false]
 twin -> remote [label="telemetry"]
 weather -> plant
 weather -> twin
 faults -> sensors [style=dashed]
 faults -> valid [style=dashed]
 faults -> remote [style=dashed]
 faults -> actuator [style=dashed constraint=false]
 plant -> evaluation [style=dotted constraint=false]
 twin -> evaluation [style=dotted]
}"""


def show_figure(fig, time_range=None):
    if time_range is not None:
        for axis in fig.axes:
            axis.set_xlim(*time_range)
    st.pyplot(fig, width="stretch")
    plt.close(fig)


def initialize(project_root: Path, results_root: Path):
    if "lab_draft" not in st.session_state:
        st.session_state.lab_draft = new_draft(project_root)
        st.session_state.lab_draft_signature = None
    if "lab_experiment" not in st.session_state:
        saved = saved_experiments(results_root)
        st.session_state.lab_experiment = load_experiment(saved[0]) if saved else None


def header():
    st.html(STYLE)
    left, right = st.columns([5, 1])
    with left:
        st.html(
            '<div class="lab-kicker">Digital Twin Research Laboratory</div>'
            '<h1 class="lab-heading">AgriTwin-CPS</h1>'
            '<p class="lab-intro">An interactive research platform for greenhouse digital twins, '
            "state estimation, closed-loop control, and resilience testing.</p>"
        )
    with right:
        st.html('<span class="lab-tag">SIMULATION ENVIRONMENT</span>')
        st.caption("Local runtime · Ready")
    st.divider()


def sidebar(results_root: Path) -> str:
    with st.sidebar:
        st.html('<div class="lab-kicker">Research workspace</div>')
        page = st.radio("Workspace", PAGES, key="lab_page")
        st.divider()
        snapshot = st.session_state.lab_experiment
        st.caption("LAST SUCCESSFUL EXPERIMENT")
        if snapshot:
            st.write(snapshot.config.name.replace("_", " ").title())
            st.caption(
                f"{len(snapshot.runs)} runs · {len(snapshot.config.seeds)} seed(s)\n\n"
                f"{snapshot.config.steps * snapshot.config.dt_seconds / 3600:g} h per run"
            )
        else:
            st.caption("No completed experiment yet.")
        saved = saved_experiments(results_root)
        if saved:

            def restore():
                selected = st.session_state.restore_experiment
                if selected:
                    st.session_state.lab_experiment = load_experiment(Path(selected))
                    st.session_state.pop("lab_archive", None)
                    st.session_state.restore_experiment = None

            st.selectbox(
                "Restore saved experiment",
                [None, *map(str, saved)],
                format_func=lambda p: (
                    "Choose a saved experiment…" if p is None else Path(p).parent.name
                ),
                key="restore_experiment",
                on_change=restore,
            )
        st.divider()
        st.caption("Synthetic model data only.\n\nNo public-data or physical-hardware validation.")
    return page


def select_run(snapshot: ExperimentRecord, key: str) -> RunRecord:
    preferred = next(
        (i for i, run in enumerate(snapshot.runs) if run.controller == "twin_assisted"), 0
    )
    labels = [run.label for run in snapshot.runs]
    selected = st.selectbox(
        "Inspect run",
        range(len(labels)),
        index=preferred,
        format_func=lambda i: labels[i],
        key=f"{key}_{snapshot.directory.name}",
    )
    return snapshot.runs[selected]


def result_caption(snapshot: ExperimentRecord):
    st.caption(
        f"Saved result: {snapshot.directory.name} · {snapshot.config.name} · "
        f"{snapshot.config.steps} steps × {snapshot.config.dt_seconds} s · "
        f"{ESTIMATORS[snapshot.config.estimator.method]} estimator"
    )
    current = st.session_state.get("lab_draft_signature")
    if current is not None and current != snapshot.signature:
        st.warning("Draft changed. These are the last successful results; run again to apply it.")
    elif st.session_state.get("lab_draft_invalid"):
        st.warning(
            "The draft configuration is invalid. The last successful results remain unchanged."
        )


def key_metrics(run: RunRecord | None):
    row = run.result.trajectory.iloc[-1] if run else None
    values = [
        ("Simulated air temperature", "N/A" if row is None else f"{row.true_temperature:.2f} °C"),
        ("Simulated air humidity", "N/A" if row is None else f"{row.true_humidity:.1f} %RH"),
        ("Simulated soil moisture", "N/A" if row is None else f"{row.true_moisture:.3f}"),
        (
            "Temperature estimation MAE",
            "N/A" if run is None else f"{run.metrics['mae_temperature']:.3f} °C",
        ),
        (
            "Any environmental violation",
            "N/A" if run is None else f"{run.metrics['any_safe_range_violation_seconds']:,.0f} s",
        ),
        ("Simulation status", "Not run" if run is None else "Complete"),
    ]
    for offset in (0, 3):
        for column, (label, value) in zip(st.columns(3), values[offset : offset + 3], strict=True):
            column.metric(label, value)
    if run:
        st.caption(
            f"Latest recorded sample: t = {row.time_seconds / 3600:.3f} h · "
            "soil moisture is a fraction · MAE/violations use the full run."
        )


def safe_bounds(run: RunRecord) -> dict:
    c = run.config.controller
    return {
        "temperature": c.temperature_safe_c,
        "humidity": c.humidity_safe_pct,
        "moisture": c.moisture_safe,
    }


def empty_state():
    st.html(
        '<div class="lab-empty"><strong>No completed simulation</strong>'
        "Open Simulation Lab, choose a preset, and select Run Simulation. "
        "Only computed results will appear here.</div>"
    )


def overview(snapshot: ExperimentRecord | None):
    st.subheader("Research overview")
    st.caption("Greenhouse state estimation and local control under imperfect observations.")
    run = select_run(snapshot, "overview_run") if snapshot else None
    if snapshot:
        result_caption(snapshot)
    key_metrics(run)
    if run:
        show_figure(
            environment_figure(run.result.trajectory, safe_bounds(run), channels=("temperature",))
        )
    else:
        empty_state()
    st.subheader("The experimental loop")
    st.graphviz_chart(FLOW, width="stretch")
    st.caption(
        "Truth feeds virtual sensors and evaluation only. Remote monitoring does not gate "
        "the local controller. The threshold baseline bypasses the twin for control input."
    )
    with st.expander("Read the three state layers"):
        st.markdown(
            "**Simulation truth** — hidden model state used for sensing and evaluation.\n\n"
            "**Virtual observation** — accepted sensor reading; gaps stay missing.\n\n"
            "**Twin estimate** — independent prediction, optionally corrected by observations."
        )


def downloads(snapshot: ExperimentRecord):
    st.download_button(
        "Metrics CSV",
        (snapshot.directory / "per_seed.csv").read_bytes(),
        f"{snapshot.directory.name}_metrics.csv",
        "text/csv",
        key="lab_metrics_download",
    )
    st.download_button(
        "Results JSON",
        comparison_json(snapshot.directory),
        f"{snapshot.directory.name}_results.json",
        "application/json",
        key="lab_json_download",
    )
    if st.button("Prepare complete experiment ZIP", key="prepare_archive"):
        st.session_state.lab_archive = (snapshot.directory, experiment_archive(snapshot.directory))
    archive = st.session_state.get("lab_archive")
    if archive and archive[0] == snapshot.directory:
        st.download_button(
            "Download experiment ZIP",
            archive[1],
            f"{snapshot.directory.name}.zip",
            "application/zip",
            key="lab_archive_download",
        )


def simulation_lab(project_root: Path, results_root: Path):
    st.subheader("Simulation Lab")
    st.caption(
        "Configure a reproducible experiment. Execution begins only when you select Run Simulation."
    )
    settings, results = st.columns([1, 2], gap="large")
    with settings:
        st.markdown("#### Configuration")
        run_button = st.empty()
        config, controllers = configuration(project_root)
        submitted = run_button.button(
            "Run Simulation",
            type="primary",
            width="stretch",
            key="run_simulation",
            disabled=config is None,
        )
    if submitted:
        with results:
            with st.status("Running local simulations…", expanded=True) as status:
                try:

                    def completed(done, total, label):
                        st.write(f"Completed {done} of {total}: {label}")

                    snapshot = execute_experiment(config, controllers, results_root, completed)
                except Exception as exc:
                    # Preserve prior success when execution or disk I/O fails.
                    logging.getLogger(__name__).exception("Interactive experiment failed")
                    st.session_state.lab_failure = {
                        "time_utc": datetime.now(UTC).isoformat(),
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        "configuration": config.model_dump(mode="json"),
                    }
                    status.update(label="Experiment failed", state="error", expanded=False)
                else:
                    st.session_state.lab_experiment = snapshot
                    st.session_state.pop("lab_archive", None)
                    st.session_state.pop("lab_failure", None)
                    status.update(
                        label=f"Complete · {len(snapshot.runs)} saved runs",
                        state="complete",
                        expanded=False,
                    )
    with results:
        if failure := st.session_state.get("lab_failure"):
            st.error("The last attempt failed. Previous successful results are still available.")
            with st.expander("Failure diagnostics"):
                st.code(failure["traceback"])
                st.download_button(
                    "Download failure diagnostics",
                    json.dumps(failure, indent=2),
                    "failure_diagnostics.json",
                    "application/json",
                )
        snapshot = st.session_state.lab_experiment
        if snapshot:
            result_caption(snapshot)
            run = select_run(snapshot, "lab_run")
            key_metrics(run)
            show_figure(environment_figure(run.result.trajectory, safe_bounds(run)))
            st.caption("Use State & Fault Analysis for aligned events, control actions and errors.")
            with st.expander("Export this completed experiment"):
                downloads(snapshot)
        else:
            st.markdown("#### Ready to experiment")
            empty_state()
            st.markdown(
                "**What will be recorded**\n\nThree state layers, timestamped observations, "
                "requested and actual actions, transport/validation events, and computed metrics."
            )
            st.caption("Choose both controllers and multiple seeds to enable paired comparisons.")


def state_analysis(snapshot: ExperimentRecord | None):
    st.subheader("State & Fault Analysis")
    if snapshot is None:
        empty_state()
        return
    result_caption(snapshot)
    run = select_run(snapshot, "analysis_run")
    horizon = run.config.steps * run.config.dt_seconds / 3600
    window = st.slider(
        "Shared time window (h)",
        0.0,
        float(horizon),
        (0.0, float(horizon)),
        key=f"analysis_window_{snapshot.directory.name}_{run.seed}_{run.controller}",
    )
    frame = run.result.trajectory
    selected = frame[
        (frame.time_seconds / 3600 >= window[0]) & (frame.time_seconds / 3600 <= window[1])
    ]
    if selected.empty or window[0] == window[1]:
        st.info("Choose a time window containing at least one recorded sample.")
        return
    section = st.radio(
        "Analysis view",
        ["Environmental State", "Estimation Error", "Fault Timeline", "Control Actions"],
        horizontal=True,
        key="analysis_view",
    )
    if section == "Environmental State":
        show_figure(environment_figure(selected, safe_bounds(run)), window)
        st.caption(
            "Points show accepted readings at reception time. Generation timestamps "
            "remain in the exported trajectory. Missing readings are not connected or filled."
        )
        metric_rows = [
            {
                "State": c.title(),
                "Unit": unit,
                "MAE": run.metrics[f"mae_{c}"],
                "RMSE": run.metrics[f"rmse_{c}"],
                "Bias": run.metrics[f"bias_{c}"],
                "Accepted coverage": run.metrics[f"valid_observation_coverage_{c}"],
            }
            for c, unit in (("temperature", "°C"), ("humidity", "%RH"), ("moisture", "fraction"))
        ]
        st.dataframe(pd.DataFrame(metric_rows), hide_index=True, width="stretch")
        st.caption("Metrics use the full run, independent of the display time window.")
    elif section == "Estimation Error":
        show_figure(estimation_error_figure(selected), window)
        st.caption(
            "Estimate minus simulator truth, in each channel's native unit. "
            "Remote synchronization error is a different quantity and is not plotted here."
        )
    elif section == "Control Actions":
        conditions = fallback_conditions(run)
        mask = frame.index.isin(selected.index)
        show_figure(
            control_actions_figure(
                selected, {label: values[mask] for label, values in conditions.items()}
            ),
            window,
        )
        events = run.result.actuator_events
        in_window = events[
            (events.execution_step * run.config.dt_seconds / 3600 >= window[0])
            & (events.execution_step * run.config.dt_seconds / 3600 <= window[1])
        ]
        st.caption(
            "Command generation and execution times are integer simulation steps. "
            "Fallback shading is derived from recorded input age/validity, not command shape."
        )
        st.dataframe(in_window, height=260, hide_index=True, width="stretch")
    else:
        events = evidence_timeline(run)
        stages = st.multiselect(
            "Evidence layers", list(STAGES), default=list(STAGES), key="timeline_layers"
        )
        visible = events[
            (events.evidence.isin(stages))
            & (events.start_hours <= window[1])
            & (events.end_hours >= window[0])
        ]
        if visible.empty:
            st.info("No events in the selected layers and time window.")
        else:
            show_figure(fault_timeline_figure(visible, window))
            st.dataframe(
                visible[["event", "evidence", "start_hours", "end_hours", "source", "detail"]],
                height=300,
                hide_index=True,
                width="stretch",
            )
        st.caption(
            "Configured windows are not detections. Input validation does not identify drift "
            "or stuck-at causes. No automatic drift/stuck detector is implemented. "
            "Only observed recoveries have markers; censored events remain in the table below."
        )
        with st.expander("Recovery and remote synchronization records"):
            st.dataframe(run.recovery, hide_index=True, width="stretch")
            st.caption(
                "Recovery tolerance dwell and censoring follow the existing metrics definitions. "
                "Remote resynchronization means fresh telemetry delivery, not convergence to truth."
            )
    st.download_button(
        "Download inspected trajectory CSV",
        (run.directory / "trajectory.csv").read_bytes(),
        f"{run.controller}_seed_{run.seed}_trajectory.csv",
        "text/csv",
        key="analysis_csv",
    )
    with st.expander("Reproduction information"):
        st.code((run.directory / "config.yaml").read_text(), language="yaml")
        st.download_button(
            "Download run configuration",
            (run.directory / "config.yaml").read_bytes(),
            "config.yaml",
            "application/yaml",
        )
        st.download_button(
            "Download run metadata",
            (run.directory / "metadata.json").read_bytes(),
            "metadata.json",
            "application/json",
        )


def display_table(frame: pd.DataFrame):
    """Human-readable N/A without changing numeric source data or exported missing values."""
    st.dataframe(
        frame.style.format(precision=4, na_rep="N/A"),
        hide_index=True,
        height=min(360, 38 + 36 * len(frame)),
        width="stretch",
    )


def experiment_comparison(snapshot: ExperimentRecord | None, results_root: Path):
    st.subheader("Experiment Comparison")
    st.caption("Inspect every seed, sample variability and paired differences. No assumed winner.")
    sources = comparison_sources(results_root)
    if not sources:
        empty_state()
        st.caption(
            "Run both controllers in Simulation Lab, or generate a CLI experiment under results/."
        )
        return
    preferred = (
        sources.index(snapshot.directory) if snapshot and snapshot.directory in sources else 0
    )
    source = st.selectbox(
        "Result source",
        sources,
        index=preferred,
        format_func=lambda p: str(p.relative_to(results_root)),
        key="comparison_source",
    )
    per_seed = pd.read_csv(source / "per_seed.csv")
    summary = pd.read_csv(source / "summary.csv")
    cases = per_seed.scenario.drop_duplicates().tolist()
    case = st.selectbox("Scenario", cases, key=f"comparison_scenario_{source.name}")
    per_case = per_seed[per_seed.scenario == case]
    summary_case = summary[summary.scenario == case]
    paired_path = source / "paired_differences.csv"
    paired = pd.read_csv(paired_path) if paired_path.exists() else pd.DataFrame()
    if not paired.empty:
        paired = paired[paired.scenario == case]
    left, right = st.columns([1, 2])
    group = left.selectbox("Metric group", list(METRICS), key="comparison_group")
    registry = {key: value for key, value in METRICS[group].items() if key in per_case}
    metric = right.selectbox(
        "Simulation metric",
        list(registry),
        format_func=lambda k: registry[k][0],
        key=f"comparison_metric_{group}",
    )
    title, unit, direction = registry[metric]
    st.caption(f"Unit: {unit} · {direction}")
    if per_case[metric].notna().any():
        show_figure(metric_comparison_figure(per_case, summary_case, paired, metric, title, unit))
    else:
        st.info("N/A — no eligible measurements for this metric in the selected scenario.")
    stats = summary_case[summary_case.metric == metric][
        ["controller", "mean", "std", "n_valid", "n_total", "n_missing"]
    ]
    st.markdown("#### Summary and sample availability")
    display_table(stats.rename(columns={"mean": f"Mean ({unit})", "std": f"Sample SD ({unit})"}))
    if (stats.n_valid < 2).any():
        st.caption("Sample SD needs two valid seeds. Confidence intervals are not computed.")
    else:
        st.caption(
            "Sample SD uses ddof=1. No confidence interval or significance claim is computed."
        )
    if group == "State estimation":
        st.caption(
            "Estimation errors refer to the twin under each controller's trajectory. The threshold "
            "controller runs the estimator for evaluation but does not use it to choose actions."
        )
    if group == "Reliability & recovery":
        censor_columns = [
            c
            for c in per_case
            if c.endswith("censored_count") or c.endswith("recovery_event_count")
        ]
        st.caption(
            "Recovery means exclude censored events. Inspect censor and event counts together."
        )
        display_table(per_case[["seed", "controller", *censor_columns]])
    st.markdown("#### Individual seeds")
    display_table(
        per_case[["seed", "controller", metric]].rename(columns={metric: f"{title} ({unit})"})
    )
    if not paired.empty:
        st.markdown("#### Paired difference · twin minus threshold")
        display_table(paired[["seed", metric]].rename(columns={metric: f"Difference ({unit})"}))
        st.caption(
            "A negative delta favors the twin only for metrics where lower is preferable. "
            "Effort proxies must be interpreted with environmental safety."
        )
    else:
        st.info("Paired differences require both controllers on the same scenario and seeds.")
    with st.expander("Inspect a source run and its configuration"):
        runs = per_case[["seed", "controller"]].to_records(index=False).tolist()
        selected = st.selectbox(
            "Source run",
            runs,
            format_func=lambda item: f"{CONTROLLERS[item[1]]} · seed {item[0]}",
            key=f"source_run_{source.name}_{case}",
        )
        # Existing CLI groups use scenario/seed/controller; UI groups use runs/seed/controller.
        base = source / ("runs" if (source / "experiment.json").exists() else case)
        run_path = base / f"seed_{selected[0]}" / selected[1]
        run = load_run(run_path)
        st.code((run_path / "config.yaml").read_text(), language="yaml")
        st.dataframe(run.recovery, hide_index=True, width="stretch")
        st.download_button(
            "Download source run configuration",
            (run_path / "config.yaml").read_bytes(),
            "config.yaml",
            "application/yaml",
        )
        st.download_button(
            "Download source run metadata",
            (run_path / "metadata.json").read_bytes(),
            "metadata.json",
            "application/json",
        )
    st.divider()
    st.download_button(
        "Download per-seed CSV",
        (source / "per_seed.csv").read_bytes(),
        f"{source.name}_per_seed.csv",
        "text/csv",
    )
    st.download_button(
        "Download summary CSV",
        (source / "summary.csv").read_bytes(),
        f"{source.name}_summary.csv",
        "text/csv",
    )
    st.download_button(
        "Download comparison JSON",
        comparison_json(source),
        f"{source.name}_comparison.json",
        "application/json",
    )
