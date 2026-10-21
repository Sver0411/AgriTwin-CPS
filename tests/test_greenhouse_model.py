import numpy as np
import pytest

from agritwin_cps.config import ModelParameters, SimulationConfig
from agritwin_cps.models.actuators import Actuator
from agritwin_cps.models.greenhouse import Action, Disturbance, transition
from agritwin_cps.models.weather import generate_weather


def test_model_directions_and_hour_units():
    p = ModelParameters()
    d = Disturbance(20, 50, 0, 0)
    x = np.array([30, 70, 0.4])
    no_action = transition(x, Action(), d, p, 300)
    ventilated = transition(x, Action(1, 0), d, p, 300)
    watered = transition(x, Action(0, 1), d, p, 300)
    assert no_action[0] == pytest.approx(30 + (300 / 3600) * 0.18 * (20 - 30))
    assert ventilated[0] < no_action[0] < x[0]
    assert ventilated[1] < no_action[1] < x[1]
    assert watered[2] > no_action[2]
    assert watered[1] > no_action[1]


def test_bounds_under_extreme_noise():
    x = [24, 65, 0.45]
    rng = np.random.default_rng(7)
    for _ in range(3000):
        x = transition(
            x,
            Action(1, 1),
            Disturbance(50, 100, 1, 1),
            ModelParameters(),
            300,
            rng.normal(0, 100, 3),
        )
        assert (-10 <= x[0] <= 60) and (0 <= x[1] <= 100) and (0 <= x[2] <= 1)


def test_weather_reproducible_and_seed_sensitive():
    cfg = SimulationConfig(steps=12)
    a = generate_weather(cfg, np.random.default_rng(8))
    assert a == generate_weather(cfg, np.random.default_rng(8))
    assert a != generate_weather(cfg, np.random.default_rng(9))


def test_actuator_delay_limits_and_failures():
    from agritwin_cps.config import ActuatorConfig, Window

    a = Actuator(
        ActuatorConfig(
            delay_steps=1, min_interval_steps=3, failures=[Window(start_step=4, end_step=5)]
        )
    )
    assert a.step(Action(1, 1), 0) == Action()
    assert a.step(Action(), 1) == Action(1, 1)
    assert a.step(Action(), 2) == Action(1, 1)
    a.step(Action(), 3)
    assert a.step(Action(), 4) == Action(1, 1)
    assert a.events[-1]["status"] == "failed"
    assert a.step(Action(), 5) == Action()
    with pytest.raises(ValueError):
        Action(1.1, 0)


def test_config_rejects_bad_rates_and_fields():
    with pytest.raises(ValueError):
        SimulationConfig(dt_seconds=301)
    with pytest.raises(ValueError):
        SimulationConfig(unknown=1)
