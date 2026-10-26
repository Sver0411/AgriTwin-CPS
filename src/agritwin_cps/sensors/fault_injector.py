"""Deterministic, isolated sensor faults. Windows are [start_step, end_step)."""

import numpy as np

from agritwin_cps.config import SensorFault
from agritwin_cps.models.greenhouse import CHANNELS


class FaultInjector:
    def __init__(self, faults: list[SensorFault], dt_seconds: int):
        self.faults = faults
        self.dt_seconds = dt_seconds

    def apply(self, readings, step: int, standard_noise=None) -> np.ndarray:
        result = np.array(readings, dtype=float, copy=True)
        for fault in self.faults:
            if not fault.active(step):
                continue
            index = CHANNELS.index(fault.channel)
            if fault.kind == "noise":
                if standard_noise is None:
                    raise ValueError("noise injection requires a seeded standard-noise draw")
                result[index] += fault.magnitude * standard_noise[index]
            elif fault.kind == "missing":
                result[index] = np.nan
            elif fault.kind == "bias":
                result[index] += fault.magnitude
            elif fault.kind == "drift":
                elapsed_hours = (step - fault.start_step) * self.dt_seconds / 3600
                result[index] += fault.magnitude * elapsed_hours
            elif fault.kind == "stuck":
                result[index] = fault.magnitude
        # Missing takes precedence even if an overlapping stuck fault was configured later.
        for fault in self.faults:
            if fault.active(step) and fault.kind == "missing":
                result[CHANNELS.index(fault.channel)] = np.nan
        return result
