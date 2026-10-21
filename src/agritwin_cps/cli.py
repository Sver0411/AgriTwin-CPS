"""Command-line entry points, independent of the optional interface."""

import argparse
from pathlib import Path

from agritwin_cps.config import load_config
from agritwin_cps.simulation.engine import simulate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["simulate"])
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--output", default="results/simulation")
    parser.add_argument(
        "--controller", choices=["threshold", "twin_assisted"], default="twin_assisted"
    )
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    result = simulate(
        config, args.seed if args.seed is not None else config.seeds[0], args.controller
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result.trajectory.to_csv(output / "trajectory.csv", index=False)
    result.actuator_events.to_csv(output / "actuator_events.csv", index=False)
    print(output.resolve())
