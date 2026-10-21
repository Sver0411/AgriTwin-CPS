import inspect

import numpy as np
import pytest

from agritwin_cps.config import EstimatorConfig, ModelParameters
from agritwin_cps.models.greenhouse import Action, Disturbance
from agritwin_cps.sensors.virtual_sensor import Observation
from agritwin_cps.twin.state_estimator import ObservationCache, StateEstimator


def test_predict_correct_and_model_only():
    corrected = StateEstimator(EstimatorConfig(gain=(1, 1, 1)), ModelParameters(), 300)
    model = StateEstimator(EstimatorConfig(method="model_only"), ModelParameters(), 300)
    original = model.state.copy()
    obs = [Observation(0, (30, 80, 0.7))]
    assert corrected.correct(obs, 0) == pytest.approx([30, 80, 0.7])
    assert model.correct(obs, 0) == pytest.approx(original)
    model.predict(Action(), Disturbance(10, 30, 0, 0.5))
    assert model.state[0] < original[0]
    assert model.ages(5).tolist() == [6, 6, 6]


def test_timestamp_and_validity_checks():
    c = ObservationCache(2)
    assert np.isnan(c.update([Observation(1, (20, 70, 0.5))], 0)).all()
    c.update([Observation(1, (20, np.nan, 0.5))], 1)
    assert np.isnan(c.values[1])
    c.update([Observation(0, (40, 80, 0.8))], 2)
    assert c.values.tolist() == [20, 80, 0.5]
    assert np.isnan(c.update([Observation(0, (40, 80, 0.8))], 3)).all()
    assert np.isnan(c.update([Observation(3, (80, -2, 2))], 3)).all()


def test_age_discount_missing_and_recovery():
    e = StateEstimator(EstimatorConfig(gain=(1, 1, 1)), ModelParameters(), 300)
    e.correct([], 0)
    assert e.missing_steps.tolist() == [1, 1, 1]
    initial = e.state.copy()
    e.correct([Observation(0, (30, 80, 0.7))], 1)
    assert e.state == pytest.approx((initial + np.array([30, 80, 0.7])) / 2)
    assert e.missing_steps.tolist() == [0, 0, 0]


def test_estimator_has_no_plant_reference_or_truth_input():
    source = inspect.getsource(StateEstimator)
    assert "true_state" not in source and "plant_state" not in source
    e = StateEstimator(EstimatorConfig(), ModelParameters(), 300)
    assert set(vars(e)) == {
        "config",
        "parameters",
        "dt_seconds",
        "state",
        "observations",
        "missing_steps",
    }
