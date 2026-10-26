import numpy as np
import pandas as pd
import pytest

from agritwin_cps.config import SimulationConfig
from agritwin_cps.simulation.engine import simulate


def test_reproducible_closed_loop_and_seed_change():
    cfg = SimulationConfig(steps=40)
    a = simulate(cfg, 7, "twin_assisted").trajectory
    pd.testing.assert_frame_equal(a, simulate(cfg, 7, "twin_assisted").trajectory)
    b = simulate(cfg, 8, "twin_assisted").trajectory
    assert not np.array_equal(a.true_temperature, b.true_temperature)
    assert (a.local_control_executed).all()
    assert len(a) == cfg.steps


def test_independent_prior_when_all_sensors_absent():
    cfg = SimulationConfig(steps=10, sensor={"dropout_probability": 1})
    alternate = cfg.model_copy(update={"initial_state": (40, 90, 0.9)})
    a = simulate(cfg, 2, "twin_assisted").trajectory
    b = simulate(alternate, 2, "twin_assisted").trajectory
    for channel in ("temperature", "humidity", "moisture"):
        # Different hidden plant states cannot alter the twin without observations.
        assert np.array_equal(a[f"estimated_{channel}"], b[f"estimated_{channel}"])
        assert a[f"observed_{channel}"].isna().all()


def test_remote_outage_never_stops_or_changes_local_control():
    cfg = SimulationConfig(steps=60)
    remote_fault = cfg.model_dump()
    remote_fault["communication"]["remote"]["outages"] = [{"start_step": 10, "end_step": 40}]
    a = simulate(cfg, 4, "twin_assisted").trajectory
    b = simulate(SimulationConfig.model_validate(remote_fault), 4, "twin_assisted").trajectory
    for field in ("true_temperature", "estimated_moisture", "command_irrigation"):
        assert np.array_equal(a[field], b[field])
    assert b.local_control_executed.all()
    assert not b.loc[10:39, "remote_received"].any()
    assert b.loc[40, "remote_received"]
    assert b.loc[40, "remote_age_steps"] == 0


def test_delayed_observation_expiry_and_fallback():
    cfg = SimulationConfig(
        steps=50, sensor={"delay_steps": 10}, controller={"max_prediction_age_steps": 3}
    )
    result = simulate(cfg, 2, "twin_assisted")
    f = result.trajectory
    assert f.observed_temperature.isna().all()
    assert (f.loc[3:, "command_irrigation"] == 0).all()
    assert (f.loc[3:, "command_ventilation"] == 0.5).all()
    assert "expired" in set(result.communication_events.status)


def test_controller_comparison_uses_common_random_numbers():
    cfg = SimulationConfig(steps=100, sensor={"dropout_probability": 0.2})
    a = simulate(cfg, 7, "threshold").trajectory
    b = simulate(cfg, 7, "twin_assisted").trajectory
    for field in ("outdoor_temperature_c", "outdoor_humidity_pct", "solar_proxy"):
        assert np.array_equal(a[field], b[field])
    for channel in ("temperature", "humidity", "moisture"):
        noise_a = a[f"sensor_{channel}"] - a[f"true_{channel}"]
        noise_b = b[f"sensor_{channel}"] - b[f"true_{channel}"]
        np.testing.assert_allclose(noise_a, noise_b, atol=1e-12, equal_nan=True)


@pytest.mark.parametrize("sensor_max_age", [1, 4])
def test_threshold_observation_age_is_independent_of_estimator(sensor_max_age):
    data = SimulationConfig(
        steps=12,
        initial_state=(35, 60, 0.2),
        sensor={"delay_steps": 3, "noise_std": (0, 0, 0)},
        controller={"max_sensor_age_steps": sensor_max_age},
    ).model_dump()
    data["estimator"]["max_observation_age_steps"] = 1
    strict = simulate(SimulationConfig.model_validate(data), 7, "threshold").trajectory
    data["estimator"]["max_observation_age_steps"] = 4
    permissive = simulate(SimulationConfig.model_validate(data), 7, "threshold").trajectory
    # An unused estimator setting must not change the baseline's observations or closed loop.
    columns = [
        "observed_temperature",
        "command_ventilation",
        "command_irrigation",
        "true_temperature",
        "true_moisture",
    ]
    pd.testing.assert_frame_equal(strict[columns], permissive[columns])
    assert strict.loc[3, "estimation_age_temperature_steps"] == 4
    assert permissive.loc[3, "estimation_age_temperature_steps"] == 3
    if sensor_max_age == 4:
        assert strict.loc[3, "observed_timestamp_temperature_step"] == 0
        assert strict.loc[3, "command_irrigation"] == 1
    else:
        assert strict.observed_temperature.isna().all()
        assert (strict.command_irrigation == 0).all()
        twin = simulate(SimulationConfig.model_validate(data), 7, "twin_assisted").trajectory
        assert twin.loc[3, "observed_timestamp_temperature_step"] == 0
