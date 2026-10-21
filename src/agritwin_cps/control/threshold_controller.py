"""Hysteretic baseline using only last validated observations and their ages."""

import numpy as np

from agritwin_cps.config import ControllerConfig
from agritwin_cps.models.greenhouse import Action


class ThresholdController:
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.previous = Action()

    def command(self, values, ages) -> Action:
        p = self.config
        values, ages = np.asarray(values), np.asarray(ages)
        valid = np.isfinite(values) & (ages <= self.max_age)
        t, h, m = values
        v, r = self.previous.ventilation, self.previous.irrigation
        if valid[0] and valid[1]:
            if t >= p.temperature_on_c or h >= p.humidity_on_pct:
                v = 1.0
            elif t <= p.temperature_off_c and h <= p.humidity_off_pct:
                v = 0.0
        else:
            v = p.fallback_ventilation
        if valid[2]:
            if m <= p.moisture_on:
                r = 1.0
            elif m >= p.moisture_off:
                r = 0.0
        else:
            r = 0.0  # Stop watering when moisture information is too old.
        self.previous = Action(v, r)
        return self.previous

    @property
    def max_age(self) -> int:
        return self.config.max_sensor_age_steps
