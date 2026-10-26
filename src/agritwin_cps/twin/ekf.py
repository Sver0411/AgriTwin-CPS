"""Three-state EKF with bounded out-of-sequence measurement replay (identity sensing)."""

import numpy as np

from agritwin_cps.config import EstimatorConfig, ModelParameters
from agritwin_cps.models.greenhouse import LOWER, UPPER, Action, Disturbance, transition
from agritwin_cps.sensors.virtual_sensor import Observation


def transition_jacobian(state, action, disturbance, parameters, dt_seconds) -> np.ndarray:
    """Central differences include the clipped proxy transition; kinks use symmetric slopes."""
    jacobian = np.zeros((3, 3))
    for i, epsilon in enumerate((1e-4, 1e-4, 1e-6)):
        offset = np.zeros(3)
        offset[i] = epsilon
        plus = transition(np.asarray(state) + offset, action, disturbance, parameters, dt_seconds)
        minus = transition(np.asarray(state) - offset, action, disturbance, parameters, dt_seconds)
        jacobian[:, i] = (plus - minus) / (2 * epsilon)
    return jacobian


class ExtendedKalmanEstimator:
    """Receives timestamped measurements, known forcing and actual actuator feedback only."""

    def __init__(self, config: EstimatorConfig, parameters: ModelParameters, dt_seconds: int):
        self.config, self.parameters, self.dt_seconds = config, parameters, dt_seconds
        self.state = np.asarray(config.initial_state, dtype=float)
        self.covariance = np.diag(np.square(config.initial_std))
        self.step = 0
        self.timestamps = np.full(3, -1, dtype=int)
        self.missing_steps = np.zeros(3, dtype=int)
        self.priors = {0: (self.state.copy(), self.covariance.copy())}
        self.updates: dict[int, dict[int, tuple[float, float]]] = {}
        self.inputs: dict[int, tuple[Action, Disturbance, float]] = {}
        self.events: list[dict] = []

    def prediction_at(self, step: int) -> np.ndarray:
        return self.priors.get(step, (self.state, self.covariance))[0].copy()

    def _predict(self, state, covariance, applied, disturbance, elapsed_seconds=None):
        remaining = self.dt_seconds if elapsed_seconds is None else elapsed_seconds
        while remaining > 0:
            dt = min(300, remaining)
            f = transition_jacobian(state, applied, disturbance, self.parameters, dt)
            q = np.diag(np.square(self.config.process_std_per_sqrt_h)) * dt / 3600
            state = transition(state, applied, disturbance, self.parameters, dt)
            covariance = f @ covariance @ f.T + q
            remaining -= dt
        return state, covariance

    def _update(self, state, covariance, updates):
        state, covariance = state.copy(), covariance.copy()
        for i, (value, variance) in sorted(updates.items()):
            h = np.eye(3)[i]
            gain = covariance[:, i] / (covariance[i, i] + variance)
            state += gain * (value - state[i])
            # Joseph form preserves positive semidefiniteness under numerical roundoff.
            a = np.eye(3) - np.outer(gain, h)
            covariance = a @ covariance @ a.T + variance * np.outer(gain, gain)
        return np.clip(state, LOWER, UPPER), (covariance + covariance.T) / 2

    def correct(self, packets: list[Observation], step: int, weights=None) -> np.ndarray:
        if step != self.step:
            raise ValueError("EKF correction must follow chronological prediction steps")
        earliest = step
        used = np.zeros(3, dtype=bool)
        for packet in sorted(packets, key=lambda p: p.generated_step):
            timestamp = packet.generated_step
            target = timestamp if self.config.replay_history_steps else step
            reason = "replayed" if target < step else "updated_current"
            if timestamp > step:
                reason = "ignored_future"
            elif step - timestamp > self.config.max_observation_age_steps:
                reason = "ignored_expired"
            elif target not in self.priors:
                if self.config.too_old_policy == "current":
                    target, reason = step, "approximated_current_outside_history"
                else:
                    reason = "ignored_outside_history"
            if reason.startswith("ignored"):
                self.events.append(
                    dict(received_step=step, generated_step=timestamp, reason=reason)
                )
                continue
            accepted = False
            for i, value in enumerate(packet.values):
                if not np.isfinite(value) or not LOWER[i] <= value <= UPPER[i]:
                    continue
                existing = self.updates.setdefault(target, {})
                # For replay, older observations can improve history without replacing newer ages.
                if (target != step and i in existing) or (
                    target == step and timestamp <= self.timestamps[i]
                ):
                    continue
                trust = 1.0
                if self.config.method == "trust_ekf":
                    trust = (weights or {}).get(timestamp, np.ones(3))[i]
                if trust < self.config.min_update_trust:
                    self.events.append(
                        dict(received_step=step, generated_step=timestamp, reason=f"low_trust_{i}")
                    )
                    continue
                variance = self.config.measurement_std[i] ** 2 / trust**2
                if target == step and timestamp < step:
                    variance *= (1 + step - timestamp) ** 2
                existing[i] = (value, variance)
                self.timestamps[i] = max(self.timestamps[i], timestamp)
                used[i] = accepted = True
            if accepted:
                earliest = min(earliest, target)
                self.events.append(
                    dict(received_step=step, generated_step=timestamp, reason=reason)
                )
        state, covariance = self.priors[earliest]
        for historical in range(earliest, step + 1):
            state, covariance = self._update(state, covariance, self.updates.get(historical, {}))
            if historical < step:
                state, covariance = self._predict(state, covariance, *self.inputs[historical])
                self.priors[historical + 1] = (state.copy(), covariance.copy())
        self.state, self.covariance = state, covariance
        self.missing_steps = np.where(used, 0, self.missing_steps + 1)
        return state.copy()

    def ages(self, step: int) -> np.ndarray:
        return np.where(self.timestamps >= 0, step - self.timestamps, step + 1)

    def predict(self, applied: Action, disturbance: Disturbance, elapsed_seconds=None) -> None:
        elapsed = self.dt_seconds if elapsed_seconds is None else elapsed_seconds
        self.inputs[self.step] = (applied, disturbance, elapsed)
        self.state, self.covariance = self._predict(
            self.state, self.covariance, applied, disturbance, elapsed
        )
        self.step += 1
        self.priors[self.step] = (self.state.copy(), self.covariance.copy())
        oldest = self.step - self.config.replay_history_steps
        for mapping in (self.priors, self.updates, self.inputs):
            for key in list(mapping):
                if key < oldest:
                    del mapping[key]


def create_estimator(config, parameters, dt_seconds):
    from agritwin_cps.twin.state_estimator import StateEstimator

    cls = ExtendedKalmanEstimator if config.method in ("ekf", "trust_ekf") else StateEstimator
    return cls(config, parameters, dt_seconds)
