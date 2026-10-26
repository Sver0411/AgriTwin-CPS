import inspect

import numpy as np
import pytest

from agritwin_cps.config import EstimatorConfig, HealthConfig, ModelParameters, SimulationConfig
from agritwin_cps.models.greenhouse import Action, Disturbance
from agritwin_cps.sensors.health import SensorHealth
from agritwin_cps.sensors.virtual_sensor import Observation
from agritwin_cps.simulation.engine import simulate
from agritwin_cps.twin.ekf import ExtendedKalmanEstimator, transition_jacobian


def test_jacobian_matches_model_slopes():
    p = ModelParameters()
    a, d = Action(0.5, 0), Disturbance(15, 50, 0.8, 0.5)
    f = transition_jacobian([24, 60, 0.7], a, d, p, 300)
    expected = [
        1 - (0.18 + 1.2 * 0.5) / 12,
        1 - (0.12 + 0.9 * 0.5 + 4 * 0.5 / 100) / 12,
        1 - 0.2 / 12,
    ]
    np.testing.assert_allclose(f, np.diag(expected), atol=1e-8)


def test_covariance_update_prediction_and_missing():
    cfg = EstimatorConfig(method="ekf", process_std_per_sqrt_h=(1, 2, 0.1))
    e = ExtendedKalmanEstimator(cfg, ModelParameters(), 300)
    prior = e.covariance.copy()
    observed = np.array([25, 66, 0.45])
    expected_gain = np.diag(prior) / (np.diag(prior) + np.square(cfg.measurement_std))
    expected = np.array(cfg.initial_state) + expected_gain * (observed - cfg.initial_state)
    assert e.correct([Observation(0, tuple(observed))], 0) == pytest.approx(expected)
    assert (np.diag(e.covariance) < np.diag(prior)).all()
    posterior = e.covariance.copy()
    e.predict(Action(), Disturbance(21, 60, 0, 0))
    assert (np.diag(e.covariance) > np.diag(posterior)).all()
    prediction, covariance = e.state.copy(), e.covariance.copy()
    np.testing.assert_array_equal(e.correct([], 1), prediction)
    np.testing.assert_array_equal(e.covariance, covariance)
    assert np.linalg.eigvalsh(covariance).min() >= 0


def test_replay_matches_chronological_updates_and_bounded_history():
    cfg = EstimatorConfig(method="ekf", replay_history_steps=3, max_observation_age_steps=10)
    timely = ExtendedKalmanEstimator(cfg, ModelParameters(), 300)
    delayed = ExtendedKalmanEstimator(cfg, ModelParameters(), 300)
    a, d = Action(0.5, 1), Disturbance(20, 60, 0.5, 0.6)
    for k in range(6):
        timely.correct([Observation(0, (25, 70, 0.5))] if k == 0 else [], k)
        delayed.correct([Observation(0, (25, 70, 0.5))] if k == 2 else [], k)
        if k >= 2:
            np.testing.assert_allclose(timely.state, delayed.state, atol=1e-10)
            np.testing.assert_allclose(timely.covariance, delayed.covariance, atol=1e-10)
        timely.predict(a, d)
        delayed.predict(a, d)
    assert len(delayed.priors) <= 4 and len(delayed.inputs) <= 3
    old = delayed.state.copy()
    delayed.correct([Observation(0, (35, 80, 0.8)), Observation(7, (40, 80, 0.9))], 6)
    np.testing.assert_allclose(delayed.state, old)
    assert {r["reason"] for r in delayed.events} >= {
        "replayed",
        "ignored_outside_history",
        "ignored_future",
    }
    assert "true_state" not in inspect.getsource(ExtendedKalmanEstimator)


def test_trust_downweights_and_rejects_observations():
    cfg = EstimatorConfig(method="trust_ekf")
    e = ExtendedKalmanEstimator(cfg, ModelParameters(), 300)
    before = e.state.copy()
    e.correct([Observation(0, (35, 80, 0.7))], 0, {0: np.array([0, 0.3, 1])})
    assert e.state[0] == before[0]
    ordinary = ExtendedKalmanEstimator(
        cfg.model_copy(update={"method": "ekf"}), ModelParameters(), 300
    )
    ordinary.correct([Observation(0, (35, 80, 0.7))], 0)
    assert abs(e.state[1] - before[1]) < abs(ordinary.state[1] - before[1])


def test_health_normal_bias_drift_stuck_missing_and_recovery():
    health = SensorHealth(HealthConfig(stuck_steps=3, persistence_steps=2), 300)
    prediction = [24, 60, 0.4]
    health.inspect(Observation(0, (24, 60, 0.4)), prediction, 0)
    assert health.states == ["normal"] * 3
    health.inspect(Observation(1, (29, 61, 0.41)), prediction, 1)
    assert health.states[0] == "suspected" and health.scores[0] < 1
    health.inspect(Observation(2, (30, 62, 0.42)), prediction, 2)
    assert health.states[0] == "confirmed_anomaly"
    for k in range(3, 8):
        health.inspect(Observation(k, (24 + k * 0.1, 62, np.nan)), prediction, k)
    assert "constant_value" in health.reasons[1]
    assert health.scores[2] == 0
    health.inspect(Observation(8, (24.9, 63, 0.44)), [24.9, 63, 0.44], 8)
    assert health.states[2] == "normal"
    health.record(20)
    assert health.events[-1]["state"] == "unknown"
    out = SensorHealth(HealthConfig(), 300)
    out.inspect(Observation(0, (90, 60, 0.4)), prediction, 3)
    assert out.reasons[0].startswith("out_of_range") and out.scores[0] == 0
    assert "delayed" in out.reasons[1]
    drift = SensorHealth(HealthConfig(residual_scale=(0.1, 1, 0.01)), 300)
    for k in range(12):
        drift.inspect(Observation(k, (24 + k * 0.1, 60 + k, 0.4)), prediction, k)
    assert "persistent_residual" in drift.reasons[0]


def test_ekf_no_truth_leak_with_missing_sensors():
    cfg = SimulationConfig(
        steps=12,
        sensor={"dropout_probability": 1},
        estimator={"method": "trust_ekf", "replay_history_steps": 5},
    )
    changed = cfg.model_copy(update={"initial_state": (40, 80, 0.9)})
    a, b = [simulate(c, 7, "twin_assisted").trajectory for c in (cfg, changed)]
    np.testing.assert_array_equal(a.estimated_temperature, b.estimated_temperature)


def test_current_ekf_uses_newest_batch_and_replay_handles_reordering():
    p, a, d = ModelParameters(), Action(), Disturbance(20, 60, 0, 0.25)
    current = ExtendedKalmanEstimator(EstimatorConfig(method="ekf"), p, 300)
    current.correct([], 0)
    current.predict(a, d)
    current.correct([Observation(0, (35, 90, 0.9)), Observation(1, (24, 65, 0.45))], 1)
    reference = ExtendedKalmanEstimator(EstimatorConfig(method="ekf"), p, 300)
    reference.correct([], 0)
    reference.predict(a, d)
    reference.correct([Observation(1, (24, 65, 0.45))], 1)
    np.testing.assert_allclose(current.state, reference.state)
    cfg = EstimatorConfig(method="ekf", replay_history_steps=5)
    timely, reordered = [ExtendedKalmanEstimator(cfg, p, 300) for _ in range(2)]
    o0, o1 = Observation(0, (24, 60, 0.4)), Observation(1, (25, 62, 0.42))
    for k in range(4):
        timely.correct([o0] if k == 0 else [o1] if k == 1 else [], k)
        reordered.correct([o1] if k == 2 else [o0] if k == 3 else [], k)
        if k == 3:
            np.testing.assert_allclose(timely.state, reordered.state, atol=1e-10)
            np.testing.assert_allclose(timely.covariance, reordered.covariance, atol=1e-10)
        timely.predict(a, d)
        reordered.predict(a, d)
    health = SensorHealth(HealthConfig(), 300)
    health.inspect(Observation(100, (35, 60, 0.4)), [24, 60, 0.4], 100)
    assert health.states[0] == "suspected"


def test_covariance_safety_fallback_is_recorded_and_recoverable():
    cfg = SimulationConfig(
        steps=8,
        estimator={"method": "ekf", "max_std": (0.5, 2, 0.02)},
        sensor={
            "faults": [
                {"channel": c, "kind": "missing", "start_step": 0, "end_step": 3}
                for c in ("temperature", "humidity", "moisture")
            ]
        },
    )
    f = simulate(cfg, 7, "twin_assisted").trajectory
    assert f.uncertainty_fallback.iloc[:3].all()
    assert f.command_irrigation.iloc[:3].eq(0).all()
    assert f.command_ventilation.iloc[:3].eq(0.5).all()
    assert not f.uncertainty_fallback.iloc[3]
    assert f.control_valid_temperature.iloc[3]
