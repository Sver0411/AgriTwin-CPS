"""Synthetic diurnal weather generated before the control loop."""

import numpy as np

from agritwin_cps.config import SimulationConfig
from agritwin_cps.models.greenhouse import Disturbance


def generate_weather(config: SimulationConfig, rng: np.random.Generator) -> list[Disturbance]:
    hours = np.arange(config.steps) * config.dt_seconds / 3600
    solar = np.maximum(0, np.sin(2 * np.pi * (hours % 24 - 6) / 24))
    phase = np.sin(2 * np.pi * (hours - 8) / 24)
    w = config.weather
    temperature = (
        w.mean_temperature_c
        + w.amplitude_temperature_c * phase
        + rng.normal(0, w.temperature_noise_c, config.steps)
    )
    humidity = np.clip(
        w.mean_humidity_pct - 15 * phase + rng.normal(0, w.humidity_noise_pct, config.steps), 0, 100
    )
    return [
        Disturbance(float(t), float(h), float(s), float(0.25 + 0.75 * s))
        for t, h, s in zip(temperature, humidity, solar, strict=True)
    ]
