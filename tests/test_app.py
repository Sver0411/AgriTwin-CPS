"""Real-engine UI flows, draft/result separation, persistence and honest failure states."""

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from agritwin_cps.config import SimulationConfig
from agritwin_cps.simulation.runner import run_experiment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("AGRITWIN_RESULTS_DIR", str(tmp_path))
    return tmp_path


def open_app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()


def open_lab(app):
    return app.radio(key="lab_page").set_value("Simulation Lab").run()


def test_interface_runs_real_engine_and_exports(app_workspace):
    app = open_app()
    assert not app.exception
    assert [m.value for m in app.metric[:5]] == ["N/A"] * 5
    assert app.metric[5].value == "Not run"
    open_lab(app)
    app.number_input(key="input_duration").set_value(1.0)
    app.text_input(key="input_seeds").set_value("101, 202")
    app.button(key="run_simulation").click().run()
    assert not app.exception and not app.error
    snapshot = app.session_state["lab_experiment"]
    assert snapshot.config.steps == 12 and snapshot.config.seeds == [101, 202]
    assert {r.controller for r in snapshot.runs} == {"threshold", "twin_assisted"}
    assert len(snapshot.runs) == 4
    assert all(len(r.result.trajectory) == 12 for r in snapshot.runs)
    per_seed = pd.read_csv(snapshot.directory / "per_seed.csv")
    assert len(per_seed) == 4
    assert (snapshot.directory / "paired_summary.csv").exists()

    # Editing and navigating are display operations, never implicit experimental execution.
    app.number_input(key="input_duration").set_value(2.0).run()
    assert app.session_state["lab_experiment"].signature == snapshot.signature
    assert any("Draft changed" in w.value for w in app.warning)
    assert len(list(app_workspace.glob("ui_runs/*/experiment.json"))) == 1
    app.radio(key="lab_page").set_value("State & Fault Analysis").run()
    assert not app.exception
    app.radio(key="analysis_view").set_value("Control Actions").run()
    assert not app.exception
    app.radio(key="lab_page").set_value("Experiment Comparison").run()
    assert not app.exception
    assert app.dataframe
    app.radio(key="lab_page").set_value("Overview").run()
    assert not app.exception and app.metric[5].value == "Complete"

    # A fresh browser session restores persisted, fully completed artifacts, not draft settings.
    refreshed = open_app()
    assert not refreshed.exception
    assert refreshed.session_state["lab_experiment"].directory == snapshot.directory
    assert refreshed.metric[5].value == "Complete"


def test_interface_rejects_invalid_yaml_without_fabricated_results(app_workspace):
    app = open_lab(open_app())
    app.checkbox(key="input_yaml_mode").check().run()
    app.text_area(key="input_yaml").set_value("steps: -1\nunknown_parameter: 10").run()
    assert not app.exception
    assert app.error and app.button(key="run_simulation").disabled
    assert app.session_state["lab_experiment"] is None
    assert not list(app_workspace.glob("ui_runs/*/experiment.json"))


def test_failed_execution_preserves_last_success(monkeypatch, app_workspace):
    app = open_lab(open_app())
    app.number_input(key="input_duration").set_value(0.5)
    app.button(key="run_simulation").click().run()
    successful = app.session_state["lab_experiment"]

    def disk_failure(*args, **kwargs):
        raise OSError("Test disk write failure")

    monkeypatch.setattr("agritwin_cps.ui.workspace.write_run", disk_failure)
    app.button(key="run_simulation").click().run()
    assert not app.exception
    assert app.error
    assert "Test disk write failure" in app.session_state["lab_failure"]["traceback"]
    assert app.session_state["lab_experiment"].directory == successful.directory
    assert len(list(app_workspace.glob("ui_runs/*/experiment.json"))) == 1


def test_preset_reset_and_cli_comparison(app_workspace):
    app = open_lab(open_app())
    app.selectbox(key="input_preset").select("Missing Observations").run()
    assert app.slider(key="input_dropout").value == 0.3
    assert app.number_input(key="input_noise_0").value == 0.3
    app.selectbox(key="input_preset").select("Sensor Drift").run()
    app.selectbox(key="input_sensor_fault").select("No injected sensor fault").run()
    app.selectbox(key="input_sensor_fault").select("Preset faults").run()
    assert len(app.session_state["lab_draft"]["data"]["sensor"]["faults"]) == 2
    app.selectbox(key="input_preset").select("Sensor Noise").run()
    assert not app.exception
    assert app.number_input(key="input_noise_0").value == 1.5
    assert app.number_input(key="input_noise_1").value == 7.5
    assert app.number_input(key="input_noise_2").value == 0.05
    assert app.session_state["lab_experiment"] is None

    cfg = SimulationConfig(steps=8, seeds=[11, 22])
    run_experiment("controller_comparison", cfg, app_workspace / "cli_comparison", plots=False)
    app.radio(key="lab_page").set_value("Experiment Comparison").run()
    assert not app.exception
    app.selectbox(key="comparison_group").select("Reliability & recovery").run()
    assert not app.exception
    assert any("N/A" in message.value for message in app.info)
    assert len(pd.read_csv(app_workspace / "cli_comparison" / "per_seed.csv")) == 4


def test_window_guidance_and_actual_configuration_names(app_workspace):
    app = open_lab(open_app())
    assert any("Actual configuration: nominal (unchanged)" in c.value for c in app.caption)
    app.selectbox(key="input_preset").select("Missing Observations").run()
    app.number_input(key="input_duration").set_value(4.0).run()
    assert any("will not trigger" in w.value for w in app.warning)
    with pytest.warns(UserWarning, match="will not trigger"):
        app.button(key="run_simulation").click().run()
    assert not app.exception
    assert app.session_state["lab_experiment"].config.name == "sensor_dropout_custom"

    app.number_input(key="input_duration").set_value(11.0).run()
    assert any("only part of the window" in w.value for w in app.warning)
    app.number_input(key="input_dt").set_value(60).run()
    assert app.session_state["lab_draft"]["data"]["sensor"]["faults"][0]["start_step"] == 120
    assert any("Preset/YAML fault windows keep step indices" in c.value for c in app.caption)
    app.selectbox(key="input_sensor_fault").select("Missing observations").run()
    app.number_input(key="input_fault_start").set_value(1.0)
    app.number_input(key="input_fault_duration").set_value(1.0).run()
    assert app.session_state["lab_draft"]["data"]["sensor"]["faults"][0]["start_step"] == 60
    app.number_input(key="input_dt").set_value(120).run()
    fault = app.session_state["lab_draft"]["data"]["sensor"]["faults"][0]
    assert (fault["start_step"], fault["end_step"]) == (30, 60)

    # Explicit user names are preserved, including when YAML replaces the base preset.
    app.checkbox(key="input_yaml_mode").check().run()
    app.text_area(key="input_yaml").set_value("name: trial_A\nsteps: 8\nseeds: [7]").run()
    app.button(key="run_simulation").click().run()
    assert not app.exception
    assert app.session_state["lab_experiment"].config.name == "trial_A"
