import numpy as np
import pandas as pd

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
