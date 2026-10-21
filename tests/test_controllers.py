import numpy as np

from agritwin_cps.config import ControllerConfig
from agritwin_cps.control.threshold_controller import ThresholdController
from agritwin_cps.models.greenhouse import Action


def test_hysteresis_and_missing_safety():
    c = ThresholdController(ControllerConfig())
    assert c.command([29, 80, 0.3], [0, 0, 0]) == Action(1, 1)
    assert c.command([26, 78, 0.4], [0, 0, 0]) == Action(1, 1)
    assert c.command([24, 70, 0.5], [0, 0, 0]) == Action()
    assert c.command([np.nan] * 3, [100] * 3) == Action(0.5, 0)
