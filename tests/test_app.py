"""Optional interface verification; core tests do not require Streamlit."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_interface_runs_real_engine_and_exports():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
    assert not app.exception
    app.number_input[1].set_value(12)
    app.button[0].click().run()
    assert not app.exception
    config, seed, runs = app.session_state["experiment_result"]
    assert config.steps == 12
    assert set(runs) == {"threshold", "twin_assisted"}
    assert len(runs["threshold"][0].trajectory) == 12
    assert seed >= 0


def test_interface_rejects_invalid_yaml_without_fabricated_results():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
    app.text_area[0].set_value("steps: -1\nunknown_parameter: 10")
    app.button[0].click().run()
    assert not app.exception
    assert app.error
    assert "experiment_result" not in app.session_state
