"""Command-line entry points, independent of the optional interface."""

import argparse
from pathlib import Path

import pandas as pd

from agritwin_cps.config import load_config
from agritwin_cps.control.threshold_controller import ThresholdController
from agritwin_cps.models.actuators import Actuator
from agritwin_cps.models.greenhouse import CHANNELS, transition
from agritwin_cps.models.weather import generate_weather
from agritwin_cps.sensors.virtual_sensor import VirtualSensor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["simulate"])
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--output", default="results/phase1")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    import numpy as np

    rng = np.random.default_rng(config.seeds[0])
    weather = generate_weather(config, rng)
    sensor = VirtualSensor(config.sensor)
    controller = ThresholdController(config.controller)
    actuator = Actuator(config.actuator)
    state = np.array(config.initial_state)
    rows = []
    for step, disturbance in enumerate(weather):
        obs = sensor.sample(state, step, rng.normal(size=3), rng.random(3), config.dt_seconds)
        command = controller.command(obs.values, np.zeros(3))
        actual = actuator.step(command, step)
        rows.append(
            {
                "step": step,
                **dict(zip(CHANNELS, state, strict=True)),
                "ventilation": actual.ventilation,
                "irrigation": actual.irrigation,
            }
        )
        state = transition(state, actual, disturbance, config.plant, config.dt_seconds)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output / "trajectory.csv", index=False)
    print(output.resolve())
