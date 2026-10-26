"""Validated configuration. Rates use hours; event times use integer simulation steps."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Channel = Literal["temperature", "humidity", "moisture"]
Triple = tuple[float, float, float]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Window(Settings):
    start_step: int = Field(ge=0)
    end_step: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_step <= self.start_step:
            raise ValueError("end_step must exceed start_step (half-open interval)")
        return self

    def active(self, step: int) -> bool:
        return self.start_step <= step < self.end_step


class ModelParameters(Settings):
    # Demonstration coefficients, not calibrated greenhouse parameters.
    heat_exchange_per_h: float = Field(default=0.18, ge=0, le=5)
    solar_heat_c_per_h: float = Field(default=4.0, ge=0, le=20)
    ventilation_heat_per_h: float = Field(default=1.2, ge=0, le=5)
    humidity_exchange_per_h: float = Field(default=0.12, ge=0, le=5)
    ventilation_humidity_per_h: float = Field(default=0.9, ge=0, le=5)
    evaporation_rh_per_h: float = Field(default=4.0, ge=0, le=30)
    irrigation_rh_per_h: float = Field(default=2.0, ge=0, le=30)
    irrigation_fraction_per_h: float = Field(default=0.14, ge=0, le=1)
    moisture_loss_per_h: float = Field(default=0.012, ge=0, le=1)
    drainage_per_h: float = Field(default=0.2, ge=0, le=5)
    drainage_threshold: float = Field(default=0.65, ge=0, le=1)


class WeatherConfig(Settings):
    mean_temperature_c: float = 21.0
    amplitude_temperature_c: float = Field(default=7.0, ge=0, le=20)
    mean_humidity_pct: float = Field(default=65.0, ge=0, le=100)
    temperature_noise_c: float = Field(default=0.3, ge=0, le=5)
    humidity_noise_pct: float = Field(default=1.0, ge=0, le=20)


class SensorFault(Window):
    channel: Channel
    kind: Literal["missing", "bias", "drift", "stuck", "noise"]
    magnitude: float = 0.0  # Drift: units/hour; noise: extra SD; bias/stuck: channel units.

    @model_validator(mode="after")
    def noise_scale(self):
        if self.kind == "noise" and self.magnitude < 0:
            raise ValueError("noise fault magnitude must be nonnegative")
        return self


class SensorConfig(Settings):
    noise_std: Triple = (0.3, 1.5, 0.01)
    bias: Triple = (0.0, 0.0, 0.0)
    dropout_probability: float = Field(default=0.0, ge=0, le=1)
    delay_steps: int = Field(default=0, ge=0, le=10000)
    faults: list[SensorFault] = Field(default_factory=list)

    @model_validator(mode="after")
    def nonnegative_noise(self):
        if min(self.noise_std) < 0:
            raise ValueError("noise_std must be nonnegative")
        return self


class LinkConfig(Settings):
    packet_loss: float = Field(default=0, ge=0, le=1)
    delay_steps: int = Field(default=0, ge=0, le=10000)
    jitter_steps: int = Field(default=0, ge=0, le=10000)
    max_age_steps: int = Field(default=5, ge=0, le=10000)
    outages: list[Window] = Field(default_factory=list)


class CommunicationConfig(Settings):
    local: LinkConfig = Field(default_factory=LinkConfig)
    remote: LinkConfig = Field(default_factory=LinkConfig)


class ActuatorConfig(Settings):
    delay_steps: int = Field(default=0, ge=0, le=10000)
    min_interval_steps: int = Field(default=3, ge=0, le=10000)
    failures: list[Window] = Field(default_factory=list)


class ControllerConfig(Settings):
    temperature_on_c: float = 28.0
    temperature_off_c: float = 25.0
    humidity_on_pct: float = 85.0
    humidity_off_pct: float = 75.0
    moisture_on: float = Field(default=0.34, ge=0, le=1)
    moisture_off: float = Field(default=0.48, ge=0, le=1)
    max_sensor_age_steps: int = Field(default=5, ge=0)
    max_prediction_age_steps: int = Field(default=30, ge=0)
    fallback_ventilation: float = Field(default=0.5, ge=0, le=1)
    temperature_safe_c: tuple[float, float] = (16.0, 32.0)
    humidity_safe_pct: tuple[float, float] = (35.0, 90.0)
    moisture_safe: tuple[float, float] = (0.25, 0.75)
    recovery_dwell_steps: int = Field(default=3, ge=1)
    recovery_tolerance: Triple = (1.0, 5.0, 0.03)

    @model_validator(mode="after")
    def thresholds(self):
        if not self.temperature_off_c < self.temperature_on_c:
            raise ValueError("temperature hysteresis must be ordered")
        if not self.humidity_off_pct < self.humidity_on_pct:
            raise ValueError("humidity hysteresis must be ordered")
        if not self.moisture_on < self.moisture_off:
            raise ValueError("moisture hysteresis must be ordered")
        for bounds in (self.temperature_safe_c, self.humidity_safe_pct, self.moisture_safe):
            if bounds[0] >= bounds[1]:
                raise ValueError("safe bounds must be ordered")
        if min(self.recovery_tolerance) <= 0:
            raise ValueError("recovery tolerances must be positive")
        return self


class HealthConfig(Settings):
    method: Literal["basic", "residual", "persistent"] = "persistent"
    residual_scale: Triple = (1.0, 5.0, 0.03)
    residual_threshold: float = Field(default=3.0, gt=0)
    persistence_steps: int = Field(default=3, ge=2)
    ewma_alpha: float = Field(default=0.2, gt=0, le=1)
    max_rate_per_h: Triple = (30.0, 100.0, 0.5)
    stuck_tolerance: Triple = (0.001, 0.005, 0.00001)
    stuck_steps: int = Field(default=8, ge=2)
    missing_age_steps: int = Field(default=6, ge=1)
    delay_warning_steps: int = Field(default=2, ge=0)

    @model_validator(mode="after")
    def positive_scales(self):
        if min(self.residual_scale + self.max_rate_per_h + self.stuck_tolerance) <= 0:
            raise ValueError("health scales, rates and tolerances must be positive")
        return self


class SamplingConfig(Settings):
    strategy: Literal["fixed", "change", "uncertainty", "trust_change", "event"] = "fixed"
    fixed_interval_steps: int = Field(default=1, ge=1)
    min_interval_steps: int = Field(default=1, ge=1)
    max_interval_steps: int = Field(default=12, ge=1)
    change_scale: Triple = (1.0, 5.0, 0.03)
    change_threshold: float = Field(default=1.0, gt=0)
    uncertainty_scale: Triple = (1.0, 5.0, 0.03)
    uncertainty_threshold: float = Field(default=1.0, gt=0)
    trust_threshold: float = Field(default=0.5, gt=0, le=1)
    max_valid_age_steps: int = Field(default=12, ge=1)
    sample_budget: int | None = Field(default=None, ge=0)
    local_byte_budget: int | None = Field(default=None, ge=0)
    suppress_send_during_outage: bool = False

    @model_validator(mode="after")
    def intervals(self):
        if not self.min_interval_steps <= self.fixed_interval_steps <= self.max_interval_steps:
            raise ValueError("sampling requires min_interval <= fixed_interval <= max_interval")
        if min(self.change_scale + self.uncertainty_scale) <= 0:
            raise ValueError("sampling normalization scales must be positive")
        return self


class EstimatorConfig(Settings):
    method: Literal["model_only", "observation_corrected", "ekf", "trust_ekf"] = (
        "observation_corrected"
    )
    initial_state: Triple = (23.0, 62.0, 0.43)  # Independent prior, never read from the plant.
    gain: Triple = (0.35, 0.3, 0.4)
    max_observation_age_steps: int = Field(default=5, ge=0)

    initial_std: Triple = (2.0, 8.0, 0.08)
    process_std_per_sqrt_h: Triple = (0.12, 0.4, 0.001)
    measurement_std: Triple = (0.3, 1.5, 0.01)
    max_std: Triple = (5.0, 20.0, 0.2)
    replay_history_steps: int = Field(default=0, ge=0, le=10000)
    too_old_policy: Literal["ignore", "current"] = "ignore"
    min_update_trust: float = Field(default=0.1, gt=0, le=1)

    @model_validator(mode="after")
    def valid_gain(self):
        if min(self.gain) < 0 or max(self.gain) > 1:
            raise ValueError("gain must lie in [0, 1]")
        validate_state(self.initial_state)
        if min(self.initial_std + self.measurement_std + self.max_std) <= 0:
            raise ValueError("EKF standard deviations must be positive")
        if min(self.process_std_per_sqrt_h) < 0:
            raise ValueError("EKF process standard deviations must be nonnegative")
        if self.replay_history_steps and self.method not in ("ekf", "trust_ekf"):
            raise ValueError("historical replay requires an EKF method")
        return self


def validate_state(state: Triple) -> None:
    for value, (low, high) in zip(state, ((-10, 60), (0, 100), (0, 1)), strict=True):
        if not low <= value <= high:
            raise ValueError("initial state outside simulation bounds")


class SimulationConfig(Settings):
    name: str = "nominal"
    steps: int = Field(default=576, ge=2, le=100000)
    dt_seconds: int = Field(default=300, ge=1, le=300)
    seeds: list[int] = Field(default_factory=lambda: [101, 202, 303, 404, 505])
    initial_state: Triple = (24.0, 65.0, 0.45)
    process_noise_std_per_sqrt_h: Triple = (0.12, 0.4, 0.001)
    plant: ModelParameters = Field(default_factory=ModelParameters)
    twin: ModelParameters = Field(default_factory=ModelParameters)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    sensor: SensorConfig = Field(default_factory=SensorConfig)
    communication: CommunicationConfig = Field(default_factory=CommunicationConfig)
    actuator: ActuatorConfig = Field(default_factory=ActuatorConfig)
    controller: ControllerConfig = Field(default_factory=ControllerConfig)
    estimator: EstimatorConfig = Field(default_factory=EstimatorConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)

    @model_validator(mode="after")
    def stable(self):
        validate_state(self.initial_state)
        if not self.seeds or len(set(self.seeds)) != len(self.seeds) or min(self.seeds) < 0:
            raise ValueError("seeds must be distinct nonnegative integers")
        if min(self.process_noise_std_per_sqrt_h) < 0:
            raise ValueError("process noise must be nonnegative")
        for model in (self.plant, self.twin):
            rate = max(
                model.heat_exchange_per_h + model.ventilation_heat_per_h,
                model.humidity_exchange_per_h + model.ventilation_humidity_per_h,
                model.drainage_per_h,
            )
            if rate * self.dt_seconds / 3600 > 1:
                raise ValueError("Euler exchange coefficients require dt*rate <= 1")
        return self


def load_config(path: str | Path) -> SimulationConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return SimulationConfig.model_validate(yaml.safe_load(handle) or {})


def fault_window_notices(config: SimulationConfig) -> list[str]:
    """Describe unobserved/truncated windows without moving or rejecting research scenarios."""
    windows = [(f"Sensor {fault.kind} ({fault.channel})", fault) for fault in config.sensor.faults]
    windows += [
        (f"{link.title()} communication outage", window)
        for link in ("local", "remote")
        for window in getattr(config.communication, link).outages
    ]
    windows += [("Actuator failure", window) for window in config.actuator.failures]
    notices = []
    hours_per_step = config.dt_seconds / 3600
    for label, window in windows:
        interval = (
            f"{label}: [{window.start_step}, {window.end_step}) steps "
            f"({window.start_step * hours_per_step:g}–{window.end_step * hours_per_step:g} h)"
        )
        if window.start_step >= config.steps:
            notices.append(
                f"{interval} starts at/after the simulation horizon; it will not trigger."
            )
        elif window.end_step > config.steps:
            notices.append(
                f"{interval} extends beyond the simulation horizon; only part of the window "
                "will run and recovery cannot be observed within this run."
            )
    return notices
