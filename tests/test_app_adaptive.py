from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_trust_sampling_and_adaptive_comparison(monkeypatch, tmp_path):
    monkeypatch.setenv("AGRITWIN_RESULTS_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    app.radio(key="lab_page").set_value("Simulation Lab").run()
    app.number_input(key="input_duration").set_value(0.5)
    app.selectbox(key="input_estimator").select("trust_ekf").run()
    app.selectbox(key="input_sampling").select("trust_change")
    app.number_input(key="input_history").set_value(3)
    app.button(key="run_simulation").click().run()
    assert not app.exception and not app.error
    snapshot = app.session_state["lab_experiment"]
    assert snapshot.config.estimator.method == "trust_ekf"
    assert snapshot.config.sampling.strategy == "trust_change"
    assert len(snapshot.runs[0].result.health_events) == 18
    app.radio(key="lab_page").set_value("Sensor Trust & Sampling").run()
    assert not app.exception
    for mode in ("采样与传输", "协方差与历史回放"):
        app.radio(key="trust_view").set_value(mode).run()
        assert not app.exception
    app.radio(key="lab_page").set_value("Adaptive Experiments").run()
    app.checkbox(key="adaptive_use_draft").check().run()
    app.number_input(key="adaptive_duration").set_value(0.5)
    app.text_input(key="adaptive_seeds").set_value("11, 22")
    app.selectbox(key="adaptive_group").select("estimators").run()
    app.button(key="run_adaptive").click().run()
    assert not app.exception and not app.error
    source = next(tmp_path.glob("adaptive_runs/*/adaptive_experiment.json")).parent
    assert len(pd.read_csv(source / "per_seed.csv")) == 8
    app.radio(key="lab_page").set_value("Experiment Comparison").run()
    app.selectbox(key="comparison_source").select(source).run()
    assert not app.exception
    app.selectbox(key="comparison_group").select("Sampling & trust").run()
    assert not app.exception


def test_replay_fixture_export_and_failed_attempt_preserves_success(monkeypatch, tmp_path):
    monkeypatch.setenv("AGRITWIN_RESULTS_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    app.radio(key="lab_page").set_value("Data Replay").run()
    app.button(key="preview_replay").click().run()
    assert not app.exception and not app.error
    app.button(key="run_replay").click().run()
    assert not app.exception and not app.error
    app.text_input(key="measurement_seeds").set_value("11")
    app.button(key="run_measurement_comparison").click().run()
    assert not app.exception and not app.error
    compared = next(tmp_path.glob("replay_comparisons/*/replay_comparison.json")).parent
    assert len(pd.read_csv(compared / "measurement_per_seed.csv")) == 8
    previous = app.session_state["replay_success"]
    assert (Path(previous[0]) / "replay.json").exists()
    app.text_input(key="replay_start_time").set_value("2099-01-01T00:00:00Z").run()
    app.button(key="run_replay").click().run()
    assert not app.exception and app.error
    assert app.session_state["replay_success"] == previous
    app.radio(key="lab_page").set_value("Overview").run()
    app.radio(key="lab_page").set_value("Data Replay").run()
    assert app.text_input(key="replay_start_time").value == "2099-01-01T00:00:00Z"
    refreshed = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    refreshed.radio(key="lab_page").set_value("Data Replay").run()
    assert not refreshed.exception and refreshed.dataframe


def test_replay_stored_upload_has_its_own_identity_and_explicit_units(monkeypatch, tmp_path):
    monkeypatch.setenv("AGRITWIN_RESULTS_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    app.radio(key="lab_page").set_value("Data Replay").run()
    # Exercise the same stored upload bytes used when navigating away from the uploader.
    app.session_state["replay_upload_bytes"] = (
        b"timestamp,temperature\n2025-01-01T00:00:00Z,20\n2025-01-01T00:05:00Z,21\n"
    )
    app.session_state["replay_upload_name"] = "measurements.csv"
    app.radio(key="replay_source").set_value("上传 CSV").run()
    assert not app.exception
    assert app.text_input(key="replay_dataset").value == "measurements"
    app.selectbox(key="replay_column_temperature").select("temperature")
    app.selectbox(key="replay_temperature_unit").select("C")
    app.button(key="preview_replay").click().run()
    assert not app.exception and not app.error
    frame = app.session_state["replay_preview"][1]
    assert frame.temperature.tolist() == [20, 21]
    app.radio(key="replay_source").set_value("手写格式样例（非实测）").run()
    assert app.text_input(key="replay_dataset").value == "synthetic-format-fixture-v1"
