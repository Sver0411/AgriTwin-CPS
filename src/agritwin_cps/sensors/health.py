"""Causal per-channel anomaly evidence; heuristic trust is not a fault probability."""

import numpy as np

from agritwin_cps.config import HealthConfig
from agritwin_cps.models.greenhouse import CHANNELS, LOWER, UPPER
from agritwin_cps.sensors.virtual_sensor import Observation


class SensorHealth:
    def __init__(self, config: HealthConfig, dt_seconds: int):
        self.config = config
        self.dt_seconds = dt_seconds
        self.values = np.full(3, np.nan)
        self.predicted = np.full(3, np.nan)
        self.residual = np.full(3, np.nan)
        self.timestamps = np.full(3, -1, dtype=int)
        self.last_valid = np.full(3, -1, dtype=int)
        self.scores = np.zeros(3)
        self.states = ["unknown"] * 3
        self.reasons = ["no_observation"] * 3
        self.abnormal_steps = np.zeros(3, dtype=int)
        self.anomaly_count = np.zeros(3, dtype=int)
        self.sample_times = np.full(3, np.nan)
        self.constant_steps = np.zeros(3, dtype=int)
        self.ewma = np.zeros(3)
        self.events: list[dict] = []

    def inspect(
        self, packet: Observation, prediction, step: int, generated_time_seconds=None
    ) -> np.ndarray:
        """Inspect only information delivered by now; older packets cannot reset health."""
        weights = np.zeros(3)
        c = self.config
        for i, value in enumerate(packet.values):
            timestamp = packet.generated_step
            if timestamp > step:
                continue
            age = step - timestamp
            if timestamp <= self.timestamps[i]:
                # Reordered data may update EKF history without rewinding current health memory.
                if np.isfinite(value) and LOWER[i] <= value <= UPPER[i]:
                    abnormal = (
                        abs(value - prediction[i]) > c.residual_scale[i] * c.residual_threshold
                    )
                    weights[i] = (0.3 if abnormal else 1.0) / (1 + age)
                continue
            sample_time = (
                timestamp * self.dt_seconds
                if generated_time_seconds is None
                else generated_time_seconds
            )
            previous, previous_time = self.values[i], self.timestamps[i]
            self.timestamps[i] = timestamp
            self.values[i], self.predicted[i] = value, prediction[i]
            self.residual[i] = value - prediction[i]
            reasons = []
            structural = not np.isfinite(value) or not LOWER[i] <= value <= UPPER[i]
            if structural:
                reasons.append("missing_or_nonfinite" if not np.isfinite(value) else "out_of_range")
                self.constant_steps[i] = 0
            else:
                self.last_valid[i] = timestamp
                elapsed = timestamp - previous_time
                if np.isfinite(previous) and previous_time >= 0:
                    elapsed_seconds = sample_time - self.sample_times[i]
                    rate = abs(value - previous) / (elapsed_seconds / 3600)
                    if rate > c.max_rate_per_h[i]:
                        reasons.append("rate_change")
                    self.constant_steps[i] = (
                        self.constant_steps[i] + elapsed
                        if abs(value - previous) <= c.stuck_tolerance[i]
                        else 0
                    )
                if c.method != "basic":
                    normalized = self.residual[i] / c.residual_scale[i]
                    if abs(normalized) > c.residual_threshold:
                        reasons.append("model_residual")
                    self.ewma[i] += c.ewma_alpha * (normalized - self.ewma[i])
                if c.method == "persistent":
                    if abs(self.ewma[i]) > c.residual_threshold:
                        reasons.append("persistent_residual")
                    if self.constant_steps[i] >= c.stuck_steps:
                        reasons.append("constant_value")
            self.sample_times[i] = sample_time
            # A first observation after a gap is not evidence of persistence.
            self.abnormal_steps[i] = (
                self.abnormal_steps[i] + max(1, timestamp - previous_time)
                if reasons and self.anomaly_count[i]
                else 1
                if reasons
                else 0
            )
            self.anomaly_count[i] = self.anomaly_count[i] + 1 if reasons else 0
            confirmed = structural or (
                c.method == "persistent" and self.anomaly_count[i] >= c.persistence_steps
            )
            self.states[i] = (
                "confirmed_anomaly" if confirmed else "suspected" if reasons else "normal"
            )
            score = 0.0 if structural else 0.05 if confirmed else 0.3 if reasons else 1.0
            if age > c.delay_warning_steps:
                reasons.append("delayed")
                score /= 1 + age
                if self.states[i] == "normal":
                    self.states[i] = "suspected"
            self.scores[i] = weights[i] = score
            self.reasons[i] = ";".join(reasons) or "within_checks"
        return weights

    def trust(self, step: int) -> np.ndarray:
        age = np.where(self.last_valid >= 0, step - self.last_valid, step + 1)
        return np.where(age > self.config.missing_age_steps, 0.0, self.scores)

    def record(self, step: int) -> None:
        for i, channel in enumerate(CHANNELS):
            age = step - self.timestamps[i] if self.timestamps[i] >= 0 else step + 1
            stale = age > self.config.missing_age_steps
            self.events.append(
                {
                    "step": step,
                    "channel": channel,
                    "value": self.values[i],
                    "generated_step": int(self.timestamps[i]),
                    "age_steps": int(age),
                    "prediction": self.predicted[i],
                    "residual": self.residual[i],
                    "trust": float(self.trust(step)[i]),
                    "state": "unknown" if stale else self.states[i],
                    "reason": "no_recent_observation" if stale else self.reasons[i],
                    "abnormal_duration_steps": int(self.abnormal_steps[i]),
                    "last_valid_step": int(self.last_valid[i]),
                }
            )
