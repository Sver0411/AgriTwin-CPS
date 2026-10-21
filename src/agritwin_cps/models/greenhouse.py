"""Bounded, explicit Euler proxy model. State units: °C, %RH, water fraction."""

from dataclasses import dataclass

import numpy as np

from agritwin_cps.config import ModelParameters

CHANNELS = ("temperature", "humidity", "moisture")
LOWER = np.array([-10.0, 0.0, 0.0])
UPPER = np.array([60.0, 100.0, 1.0])


@dataclass(frozen=True)
class Action:
    ventilation: float = 0.0
    irrigation: float = 0.0

    def __post_init__(self):
        if not all(np.isfinite(x) and 0 <= x <= 1 for x in (self.ventilation, self.irrigation)):
            raise ValueError("actuator commands must be finite and within [0, 1]")


@dataclass(frozen=True)
class Disturbance:
    temperature: float
    humidity: float
    solar: float
    evapotranspiration: float


def transition(
    state,
    action: Action,
    disturbance: Disturbance,
    params: ModelParameters,
    dt_seconds: int,
    noise=None,
) -> np.ndarray:
    """Pure transition; shared equations do not imply sharing plant state with the twin."""
    x = np.asarray(state, dtype=float)
    if x.shape != (3,) or not np.isfinite(x).all():
        raise ValueError("state must contain three finite components")
    t, h, m = x
    v, r = action.ventilation, action.irrigation
    d, p = disturbance, params
    rates = np.array(
        [
            (p.heat_exchange_per_h + p.ventilation_heat_per_h * v) * (d.temperature - t)
            + p.solar_heat_c_per_h * d.solar,
            (p.humidity_exchange_per_h + p.ventilation_humidity_per_h * v) * (d.humidity - h)
            + p.evaporation_rh_per_h * d.evapotranspiration * (1 - h / 100)
            + p.irrigation_rh_per_h * r,
            p.irrigation_fraction_per_h * r
            - p.moisture_loss_per_h * d.evapotranspiration
            - p.drainage_per_h * max(m - p.drainage_threshold, 0),
        ]
    )
    perturbation = np.zeros(3) if noise is None else np.asarray(noise, dtype=float)
    return np.clip(x + dt_seconds / 3600 * rates + perturbation, LOWER, UPPER)
