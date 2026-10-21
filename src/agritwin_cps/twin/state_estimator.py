"""Independent model prediction and age-weighted observation correction, not a Kalman filter."""

import numpy as np

from agritwin_cps.config import EstimatorConfig, ModelParameters
from agritwin_cps.models.greenhouse import LOWER, UPPER, Action, Disturbance, transition
from agritwin_cps.sensors.virtual_sensor import Observation


class ObservationCache:
    """Reject future, expired, nonfinite, out-of-bounds and out-of-order components."""

    def __init__(self, max_age_steps: int):
        self.max_age_steps = max_age_steps
        self.values = np.full(3, np.nan)
        self.timestamps = np.full(3, -1, dtype=int)
        self.events: list[dict] = []

    def update(self, packets: list[Observation], step: int) -> np.ndarray:
        accepted = np.full(3, np.nan)
        for packet in sorted(packets, key=lambda item: item.generated_step):
            for i, value in enumerate(packet.values):
                timestamp = packet.generated_step
                if timestamp > step:
                    reason = "future"
                elif step - timestamp > self.max_age_steps:
                    reason = "expired"
                elif not np.isfinite(value):
                    reason = "missing_or_nonfinite"
                elif not LOWER[i] <= value <= UPPER[i]:
                    reason = "out_of_bounds"
                elif timestamp <= self.timestamps[i]:
                    reason = "duplicate_or_out_of_order"
                else:
                    reason = "accepted"
                    self.values[i] = value
                    self.timestamps[i] = timestamp
                    accepted[i] = value
                self.events.append(
                    {
                        "received_step": step,
                        "generated_step": timestamp,
                        "channel_index": i,
                        "reason": reason,
                    }
                )
        return accepted

    def ages(self, step: int) -> np.ndarray:
        return np.where(self.timestamps >= 0, step - self.timestamps, step + 1)


class StateEstimator:
    """Receives only observations, known disturbances and applied actuator feedback."""

    def __init__(self, config: EstimatorConfig, parameters: ModelParameters, dt_seconds: int):
        self.config = config
        self.parameters = parameters
        self.dt_seconds = dt_seconds
        self.state = np.array(config.initial_state, dtype=float)
        self.observations = ObservationCache(config.max_observation_age_steps)
        self.missing_steps = np.zeros(3, dtype=int)

    def correct(self, packets: list[Observation], step: int) -> np.ndarray:
        accepted = self.observations.update(packets, step)
        used = np.isfinite(accepted) & (self.config.method == "observation_corrected")
        self.missing_steps = np.where(used, 0, self.missing_steps + 1)
        # A delayed reading is an approximate current-state correction, discounted by age.
        age = self.observations.ages(step)
        gain = np.array(self.config.gain) / (1 + age)
        self.state[used] += gain[used] * (accepted[used] - self.state[used])
        self.state = np.clip(self.state, LOWER, UPPER)
        return self.state.copy()

    def ages(self, step: int) -> np.ndarray:
        if self.config.method == "model_only":
            return np.full(3, step + 1)
        return self.observations.ages(step)

    def predict(self, applied: Action, disturbance: Disturbance) -> None:
        self.state = transition(self.state, applied, disturbance, self.parameters, self.dt_seconds)
