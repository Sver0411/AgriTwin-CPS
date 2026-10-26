"""Simulation orchestration. Plant truth is confined to sensing, propagation and evaluation."""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from agritwin_cps.communication.simulator import CommunicationLink
from agritwin_cps.config import SimulationConfig
from agritwin_cps.control.threshold_controller import ThresholdController
from agritwin_cps.control.twin_assisted_controller import TwinAssistedController
from agritwin_cps.models.actuators import Actuator
from agritwin_cps.models.greenhouse import CHANNELS, LOWER, UPPER, transition
from agritwin_cps.models.weather import generate_weather
from agritwin_cps.sampling.scheduler import SamplingScheduler
from agritwin_cps.sensors.health import SensorHealth
from agritwin_cps.sensors.virtual_sensor import Observation, VirtualSensor
from agritwin_cps.twin.ekf import create_estimator
from agritwin_cps.twin.state_estimator import ObservationCache

Strategy = Literal["threshold", "twin_assisted"]


@dataclass
class SimulationResult:
    trajectory: pd.DataFrame
    actuator_events: pd.DataFrame
    observation_events: pd.DataFrame
    terminal_state: list[float]
    communication_events: pd.DataFrame
    sampling_events: pd.DataFrame = field(default_factory=pd.DataFrame)
    health_events: pd.DataFrame = field(default_factory=pd.DataFrame)
    estimator_events: pd.DataFrame = field(default_factory=pd.DataFrame)


def simulate(config: SimulationConfig, seed: int, strategy: Strategy) -> SimulationResult:
    if strategy not in ("threshold", "twin_assisted"):
        raise ValueError("unknown controller strategy")
    streams = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(6)]
    weather = generate_weather(config, streams[0])
    process_noise = streams[1].normal(size=(config.steps, 3))
    process_noise *= np.array(config.process_noise_std_per_sqrt_h) * np.sqrt(
        config.dt_seconds / 3600
    )
    sensor_noise = streams[2].normal(size=(config.steps, 3))
    dropout_draws = streams[3].random((config.steps, 3))
    local_draws = streams[4].random((config.steps, 2))
    remote_draws = streams[5].random((config.steps, 2))
    local = CommunicationLink(config.communication.local, "local")
    remote = CommunicationLink(config.communication.remote, "remote")
    remote_cache = ObservationCache(config.communication.remote.max_age_steps)
    sensor = VirtualSensor(config.sensor)
    estimator = create_estimator(config.estimator, config.twin, config.dt_seconds)
    health = SensorHealth(config.health, config.dt_seconds)
    scheduler = SamplingScheduler(config.sampling)
    safe_bounds = (
        config.controller.temperature_safe_c,
        config.controller.humidity_safe_pct,
        config.controller.moisture_safe,
    )
    # Validate the active observation path independently of the shadow estimator's policy.
    observation_max_age = (
        config.controller.max_sensor_age_steps
        if strategy == "threshold"
        else config.estimator.max_observation_age_steps
    )
    cache = ObservationCache(observation_max_age)
    controller_cls = ThresholdController if strategy == "threshold" else TwinAssistedController
    controller = controller_cls(config.controller)
    actuator = Actuator(config.actuator)
    true_state = np.array(config.initial_state)
    rows = []
    for step, disturbance in enumerate(weather):
        prior_std = (
            np.sqrt(np.diag(estimator.covariance))
            if hasattr(estimator, "covariance")
            else np.full(3, np.nan)
        )
        decision = scheduler.decide(
            step,
            estimator.state,
            prior_std,
            health.trust(step),
            cache.ages(step),
            safe_bounds,
            local.disconnected(step),
        )
        observation = Observation(step, (np.nan, np.nan, np.nan))
        if decision["sampled"]:
            observation = sensor.sample(
                true_state, step, sensor_noise[step], dropout_draws[step], config.dt_seconds
            )
            decision["valid_generated"] = bool(
                (
                    np.isfinite(observation.values)
                    & (np.array(observation.values) >= LOWER)
                    & (np.array(observation.values) <= UPPER)
                ).any()
            )
        if decision["sent"]:
            local.send(observation, step, *local_draws[step], config.sensor.delay_steps)
        packets = local.receive(step)
        accepted = cache.update(packets, step)
        decision["valid_received"] = bool(np.isfinite(accepted).any())
        weights = {}
        for packet in sorted(packets, key=lambda p: p.generated_step):
            prediction = (
                estimator.prediction_at(packet.generated_step)
                if hasattr(estimator, "prediction_at")
                else estimator.state.copy()
            )
            weights[packet.generated_step] = health.inspect(packet, prediction, step)
        health.record(step)
        estimated = estimator.correct(packets, step, weights)
        standard_deviation = (
            np.sqrt(np.diag(estimator.covariance))
            if hasattr(estimator, "covariance")
            else np.full(3, np.nan)
        )
        remote.send(Observation(step, tuple(estimated)), step, *remote_draws[step])
        remote_packets = remote.receive(step)
        remote_accepted = remote_cache.update(remote_packets, step)
        values = cache.values if strategy == "threshold" else estimated
        ages = cache.ages(step) if strategy == "threshold" else estimator.ages(step)
        # Covariance safety is exclusive to the estimator-assisted path.
        uncertain = standard_deviation > config.estimator.max_std
        control_values = (
            np.where(uncertain, np.nan, values) if strategy == "twin_assisted" else values
        )
        command = controller.command(control_values, ages)
        actual = actuator.step(command, step)
        row = {
            "uncertainty_fallback": bool(uncertain.any()) if strategy == "twin_assisted" else False,
            "step": step,
            "time_seconds": step * config.dt_seconds,
            "outdoor_temperature_c": disturbance.temperature,
            "outdoor_humidity_pct": disturbance.humidity,
            "solar_proxy": disturbance.solar,
            "evapotranspiration_proxy": disturbance.evapotranspiration,
            "command_ventilation": command.ventilation,
            "command_irrigation": command.irrigation,
            "actual_ventilation": actual.ventilation,
            "actual_irrigation": actual.irrigation,
            "local_control_executed": True,
            "sensor_generated_step": step if decision["generated"] else -1,
            "sampled": decision["sampled"],
            "sensor_fault_active": (
                any(f.active(step) for f in config.sensor.faults)
                or bool((dropout_draws[step] < config.sensor.dropout_probability).any())
            ),
            "local_outage": local.disconnected(step),
            "remote_outage": remote.disconnected(step),
            "remote_received": bool(np.isfinite(remote_accepted).any()),
            "remote_generated_step": int(remote_cache.timestamps.min()),
            "remote_age_steps": int(remote_cache.ages(step).max()),
        }
        for i, channel in enumerate(CHANNELS):
            # Ground-truth labels are for the evaluator only; no algorithm consumes them.
            row[f"fault_label_{channel}"] = bool(
                any(f.channel == channel and f.active(step) for f in config.sensor.faults)
                or (
                    decision["sampled"]
                    and dropout_draws[step, i] < config.sensor.dropout_probability
                )
                or config.sensor.bias[i] != 0
            )
            row[f"control_valid_{channel}"] = bool(
                np.isfinite(control_values[i]) and ages[i] <= controller.max_age
            )
            row[f"std_{channel}"] = standard_deviation[i]
            row[f"trust_{channel}"] = health.trust(step)[i]
            row[f"true_{channel}"] = true_state[i]
            row[f"sensor_{channel}"] = observation.values[i]
            row[f"observed_{channel}"] = accepted[i]
            row[f"estimated_{channel}"] = estimated[i]
            row[f"remote_{channel}"] = remote_cache.values[i]
            row[f"sync_error_{channel}"] = abs(remote_cache.values[i] - estimated[i])
            row[f"observed_timestamp_{channel}_step"] = int(cache.timestamps[i])
            row[f"observation_age_{channel}_steps"] = cache.ages(step)[i]
            row[f"estimation_age_{channel}_steps"] = estimator.ages(step)[i]
            row[f"missing_{channel}_steps"] = estimator.missing_steps[i]
        rows.append(row)
        true_state = transition(
            true_state, actual, disturbance, config.plant, config.dt_seconds, process_noise[step]
        )
        estimator.predict(actual, disturbance)
    local.finalize(config.steps)
    remote.finalize(config.steps)
    return SimulationResult(
        pd.DataFrame(rows),
        pd.DataFrame(
            actuator.events,
            columns=["generated_step", "execution_step", "status", "ventilation", "irrigation"],
        ),
        pd.DataFrame(
            cache.events, columns=["received_step", "generated_step", "channel_index", "reason"]
        ),
        true_state.tolist(),
        pd.DataFrame(local.events + remote.events),
        pd.DataFrame(scheduler.events),
        pd.DataFrame(health.events),
        pd.DataFrame(
            getattr(estimator, "events", []), columns=["received_step", "generated_step", "reason"]
        ),
    )
