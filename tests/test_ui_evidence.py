"""Presentation evidence must agree with recorded events and exported source artifacts."""

import io
import json
import zipfile

import numpy as np
import pandas as pd

from agritwin_cps.config import SimulationConfig
from agritwin_cps.simulation.engine import simulate
from agritwin_cps.ui.diagnostics import evidence_timeline, fallback_conditions
from agritwin_cps.ui.workspace import (
    RunRecord,
    comparison_json,
    comparison_sources,
    execute_experiment,
    experiment_archive,
)
from agritwin_cps.visualization.plots import environment_figure


def test_exports_match_artifacts_and_existing_metric_values(tmp_path):
    snapshot = execute_experiment(
        SimulationConfig(steps=12, seeds=[1, 2]), ["threshold", "twin_assisted"], tmp_path
    )
    exported = json.loads(comparison_json(snapshot.directory))
    disk = pd.read_csv(snapshot.directory / "per_seed.csv")
    assert len(exported["per_seed"]) == 4
    assert exported["per_seed"][0]["mae_temperature"] == disk.iloc[0].mae_temperature
    assert exported["per_seed"][0]["settling_time_seconds"] is None
    archive = zipfile.ZipFile(io.BytesIO(experiment_archive(snapshot.directory)))
    run = snapshot.runs[0]
    relative = str(run.directory.relative_to(snapshot.directory))
    assert (
        archive.read(f"{relative}/trajectory.csv")
        == (run.directory / "trajectory.csv").read_bytes()
    )
    assert json.loads(archive.read(f"{relative}/metrics.json")) == run.metrics
    assert json.loads(archive.read(f"{relative}/metadata.json"))["seed"] == run.seed


def test_event_layers_do_not_claim_configured_fault_detection(tmp_path):
    cfg = SimulationConfig(
        steps=48,
        sensor={
            "faults": [
                {"channel": c, "kind": "missing", "start_step": 2, "end_step": 12}
                for c in ("temperature", "humidity", "moisture")
            ]
        },
        communication={
            "local": {"delay_steps": 1},
            "remote": {"outages": [{"start_step": 14, "end_step": 18}]},
        },
        actuator={"delay_steps": 2, "failures": [{"start_step": 20, "end_step": 25}]},
        controller={"max_prediction_age_steps": 2},
    )
    snapshot = execute_experiment(cfg, ["twin_assisted"], tmp_path)
    run = snapshot.runs[0]
    events = evidence_timeline(run)
    assert {"Configured", "Recorded", "Validation rejection", "Derived condition"} <= set(
        events.evidence
    )
    assert "Missing sensor samples" in set(events.event)
    assert "Delayed local delivery" in set(events.event)
    assert "Actuator command failed" in set(events.event)
    assert "Remote resynchronization" in set(events.event)
    assert not events.event.str.contains("detected", case=False).any()
    missing = events[events.event == "Missing sensor samples"].iloc[0]
    assert (missing.start_step, missing.end_step) == (2, 12)
    fallback = fallback_conditions(run)
    assert fallback["Irrigation fallback"][6:12].all()
    assert (
        run.result.trajectory.command_irrigation.to_numpy()[fallback["Irrigation fallback"]] == 0
    ).all()


def test_no_fault_events_or_missing_observation_lines_are_invented(tmp_path):
    cfg = SimulationConfig(steps=12, sensor={"noise_std": [0, 0, 0], "dropout_probability": 1})
    result = simulate(cfg, 1, "threshold")
    run = RunRecord(tmp_path, cfg, 1, "threshold", result, {}, pd.DataFrame())
    timeline = evidence_timeline(run)
    assert not (timeline.evidence == "Configured").any()
    assert not (timeline.evidence == "Recovery observed").any()
    figure = environment_figure(result.trajectory, channels=("temperature",))
    ax = figure.axes[0]
    assert len(ax.lines) == 2  # Only truth/estimate are lines; observations remain discrete points.
    assert np.ma.getmaskarray(ax.collections[0].get_offsets()).all()
    import matplotlib.pyplot as plt

    plt.close(figure)


def test_comparison_sources_require_ui_completion_but_preserve_cli_discovery(tmp_path):
    cli = tmp_path / "cli_experiment"
    ui = tmp_path / "ui_runs" / "interrupted"
    for directory in (cli, ui):
        directory.mkdir(parents=True)
        # Discovery fixtures only: no simulated outcomes are asserted by these empty files.
        (directory / "per_seed.csv").touch()
        (directory / "summary.csv").touch()
    assert comparison_sources(tmp_path) == [cli]
    (ui / "experiment.json").write_text("{}")
    assert set(comparison_sources(tmp_path)) == {cli, ui}
