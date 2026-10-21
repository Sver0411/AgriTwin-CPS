"""Virtual sensor interface: the only observation producer allowed to sample plant state."""

from dataclasses import dataclass

import numpy as np

from agritwin_cps.config import SensorConfig


@dataclass(frozen=True)
class Observation:
    generated_step: int
    values: tuple[float, float, float]


class VirtualSensor:
    def __init__(self, config: SensorConfig):
        self.config = config

    def sample(
        self, plant_state, step: int, standard_noise, uniform_dropout, dt_seconds: int
    ) -> Observation:
        values = np.array(plant_state, copy=True, dtype=float)
        values += np.array(self.config.noise_std) * standard_noise + np.array(self.config.bias)
        values[np.asarray(uniform_dropout) < self.config.dropout_probability] = np.nan
        return Observation(step, tuple(values))
