import numpy as np
import pandas as pd
import pytest

from agritwin_cps.config import SimulationConfig
from agritwin_cps.experiments.comparison import paired_differences, summarize
from agritwin_cps.experiments.metrics import compute_metrics, dwell_recovery, error_statistics
from agritwin_cps.simulation.engine import simulate


def test_error_formulas_and_null_conditionals():
    stats = error_statistics([-1, 0, 2])
    assert stats["mae"] == 1
    assert stats["rmse"] == pytest.approx(np.sqrt(5 / 3))
    assert stats["bias"] == pytest.approx(1 / 3)
    assert error_statistics([])["mae"] is None
    assert error_statistics([np.nan])["rmse"] is None


def test_dwell_recovery_censoring_and_event_at_horizon():
    assert dwell_recovery([False, True, False, True, True, True], 1, 3) == 2
    assert dwell_recovery([False, True], 0, 3) is None
    cfg = SimulationConfig(
        steps=10, communication={"remote": {"outages": [{"start_step": 3, "end_step": 12}]}}
    )
    metrics, events = compute_metrics(simulate(cfg, 3, "threshold"), cfg)
    assert metrics["remote_recovery_censored_count"] is None
    assert metrics["remote_resync_censored_count"] == 1
    assert metrics["remote_resync_seconds"] is None
    assert events.estimation_recovery_censored.isna().all()
    assert not events.estimation_recovery_applicable.any()
    assert events.remote_resync_censored.all()


def test_violation_duration_effort_and_activations():
    cfg = SimulationConfig(steps=4, dt_seconds=60)
    result = simulate(cfg, 3, "threshold")
    f = result.trajectory
    f["true_temperature"] = [10, 20, 40, 25]
    f["estimated_temperature"] = [11, 20, 38, 25]
    f["actual_irrigation"] = [0, 1, 1, 0]
    f["actual_ventilation"] = [0, 0.5, 1, 0]
    metrics, _ = compute_metrics(result, cfg)
    assert metrics["temperature_violation_seconds"] == 120
    assert metrics["irrigation_activation_count"] == 1
    assert metrics["irrigation_switch_count"] == 2
    assert metrics["irrigation_amount_fraction"] == pytest.approx(2 * 60 / 3600 * 0.14)
    assert metrics["ventilation_effort_hours"] == pytest.approx(1.5 * 60 / 3600)
    assert metrics["mae_temperature"] == 0.75
    assert metrics["mae_temperature_during_communication_outage"] is None


def test_paired_delta_and_sample_standard_deviation():
    rows = pd.DataFrame(
        [
            {"experiment": "x", "scenario": "a", "seed": s, "controller": c, "mae": v}
            for s, c, v in [
                (1, "threshold", 3),
                (2, "threshold", 5),
                (1, "twin_assisted", 2),
                (2, "twin_assisted", 1),
            ]
        ]
    )
    delta = paired_differences(rows)
    assert delta.mae.tolist() == [-1, -4]
    summary = summarize(delta, ["experiment", "scenario", "controller"])
    assert summary.iloc[0]["mean"] == -2.5
    assert summary.iloc[0]["std"] == pytest.approx(np.sqrt(4.5))
    assert summary.iloc[0].n_valid == 2
