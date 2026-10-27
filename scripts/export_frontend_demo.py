"""Generate a small, labelled simulation record for the offline 3D viewer."""

import argparse
import json
import shutil
from pathlib import Path

from agritwin_cps.config import SimulationConfig
from agritwin_cps.simulation.runner import write_run

FILES = [
    "trajectory.csv",
    "config.yaml",
    "metadata.json",
    "schema.json",
    "health_events.csv",
    "communication_events.csv",
    "actuator_events.csv",
    "sampling_events.csv",
    "recovery_events.csv",
    "estimator_events.csv",
    "run.json",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New empty result directory")
    parser.add_argument("--assets", type=Path, default=Path("frontend/public/demo"))
    args = parser.parse_args()
    config = SimulationConfig(
        name="3d-viewer-synthetic-demo",
        steps=96,
        seeds=[11],
        estimator={"method": "trust_ekf", "replay_history_steps": 4},
        sampling={"fixed_interval_steps": 2},
        sensor={
            "delay_steps": 1,
            "faults": [
                {
                    "channel": "temperature",
                    "kind": "bias",
                    "magnitude": 5,
                    "start_step": 24,
                    "end_step": 40,
                },
                {"channel": "moisture", "kind": "missing", "start_step": 48, "end_step": 56},
            ],
        },
        communication={
            "local": {"outages": [{"start_step": 56, "end_step": 66}]},
            "remote": {"outages": [{"start_step": 70, "end_step": 78}]},
        },
        actuator={"delay_steps": 1, "failures": [{"start_step": 33, "end_step": 37}]},
    )
    write_run(config, 11, "twin_assisted", args.output, plots=True)
    args.assets.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        shutil.copyfile(args.output / filename, args.assets / filename)
    (args.assets / "manifest.json").write_text(json.dumps(FILES, indent=2) + "\n")
    print(f"Exported {len(FILES)} actual simulation artifacts, seed 11; no field measurements")


if __name__ == "__main__":
    main()
