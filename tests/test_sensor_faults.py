import numpy as np
import pytest

from agritwin_cps.config import SensorConfig, SensorFault
from agritwin_cps.sensors.fault_injector import FaultInjector
from agritwin_cps.sensors.virtual_sensor import VirtualSensor


@pytest.mark.parametrize("kind,value", [("bias", 26), ("stuck", 2), ("drift", 24.5)])
def test_fault_window_and_units(kind, value):
    fault = SensorFault(channel="temperature", kind=kind, magnitude=2, start_step=1, end_step=5)
    injector = FaultInjector([fault], 300)
    assert injector.apply([24, 60, 0.4], 0)[0] == 24
    assert injector.apply([24, 60, 0.4], 4)[0] == pytest.approx(value)
    assert injector.apply([24, 60, 0.4], 5)[0] == 24


def test_missing_and_random_dropout_precede_stuck():
    cfg = SensorConfig(
        noise_std=(0, 0, 0),
        dropout_probability=1,
        faults=[
            SensorFault(channel="temperature", kind="stuck", magnitude=20, start_step=0, end_step=4)
        ],
    )
    sensor = VirtualSensor(cfg)
    assert np.isnan(sensor.sample([24, 60, 0.4], 1, np.zeros(3), np.zeros(3), 300).values).all()
    injector = FaultInjector(
        [
            SensorFault(channel="humidity", kind="missing", start_step=0, end_step=4),
            SensorFault(channel="humidity", kind="stuck", magnitude=10, start_step=0, end_step=4),
        ],
        300,
    )
    assert np.isnan(injector.apply([24, 60, 0.4], 2)[1])


def test_noise_fault_is_a_seeded_sd_increment_with_window():
    cfg = SensorConfig(
        noise_std=(0.3, 0, 0),
        faults=[
            SensorFault(channel="temperature", kind="noise", magnitude=2, start_step=1, end_step=3)
        ],
    )
    sensor = VirtualSensor(cfg)
    assert sensor.sample([24, 60, 0.4], 1, np.array([2, 0, 0]), np.ones(3), 300).values[
        0
    ] == pytest.approx(28.6)
    assert sensor.sample([24, 60, 0.4], 3, np.array([2, 0, 0]), np.ones(3), 300).values[
        0
    ] == pytest.approx(24.6)
