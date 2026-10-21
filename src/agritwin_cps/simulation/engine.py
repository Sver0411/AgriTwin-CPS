"""Simulation orchestration. Plant truth is confined to sensing, propagation and evaluation."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from agritwin_cps.config import SimulationConfig
from agritwin_cps.control.threshold_controller import ThresholdController
from agritwin_cps.control.twin_assisted_controller import TwinAssistedController
from agritwin_cps.models.actuators import Actuator
from agritwin_cps.models.greenhouse import CHANNELS, transition
from agritwin_cps.models.weather import generate_weather
from agritwin_cps.sensors.virtual_sensor import VirtualSensor
from agritwin_cps.twin.state_estimator import ObservationCache, StateEstimator

Strategy = Literal["threshold", "twin_assisted"]


@dataclass
class SimulationResult:
    trajectory: pd.DataFrame
    actuator_events: pd.DataFrame
    observation_events: pd.DataFrame
    terminal_state: list[float]


def simulate(config: SimulationConfig, seed: int, strategy: Strategy) -> SimulationResult:
    if strategy not in ("threshold", "twin_assisted"):
        raise ValueError("unknown controller strategy")
    streams = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(4)]
    weather = generate_weather(config, streams[0])
    process_noise = streams[1].normal(size=(config.steps, 3))
    process_noise *= np.array(config.process_noise_std_per_sqrt_h) * np.sqrt(
        config.dt_seconds / 3600
    )
    sensor_noise = streams[2].normal(size=(config.steps, 3))
    dropout_draws = streams[3].random((config.steps, 3))
    sensor = VirtualSensor(config.sensor)
    estimator = StateEstimator(config.estimator, config.twin, config.dt_seconds)
    cache = ObservationCache(config.estimator.max_observation_age_steps)
    controller_cls = ThresholdController if strategy == "threshold" else TwinAssistedController
    controller = controller_cls(config.controller)
    actuator = Actuator(config.actuator)
    true_state = np.array(config.initial_state)
    rows = []
    for step, disturbance in enumerate(weather):
        observation = sensor.sample(
            true_state, step, sensor_noise[step], dropout_draws[step], config.dt_seconds
        )
        accepted = cache.update([observation], step)
        estimated = estimator.correct([observation], step)
        values = cache.values if strategy == "threshold" else estimated
        ages = cache.ages(step) if strategy == "threshold" else estimator.ages(step)
        command = controller.command(values, ages)
        actual = actuator.step(command, step)
        row = {
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
        }
        for i, channel in enumerate(CHANNELS):
            row[f"true_{channel}"] = true_state[i]
            row[f"sensor_{channel}"] = observation.values[i]
            row[f"observed_{channel}"] = accepted[i]
            row[f"estimated_{channel}"] = estimated[i]
            row[f"observation_age_{channel}_steps"] = cache.ages(step)[i]
            row[f"estimation_age_{channel}_steps"] = estimator.ages(step)[i]
            row[f"missing_{channel}_steps"] = estimator.missing_steps[i]
        rows.append(row)
        true_state = transition(
            true_state, actual, disturbance, config.plant, config.dt_seconds, process_noise[step]
        )
        estimator.predict(actual, disturbance)
    return SimulationResult(
        pd.DataFrame(rows),
        pd.DataFrame(actuator.events),
        pd.DataFrame(cache.events),
        true_state.tolist(),
    )
