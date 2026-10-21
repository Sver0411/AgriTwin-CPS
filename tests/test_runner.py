import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from agritwin_cps.config import SimulationConfig
from agritwin_cps.experiments.scenarios import EXPERIMENTS, scenarios
from agritwin_cps.simulation.runner import run_experiment, write_run


def test_run_artifacts_and_no_accidental_overwrite(tmp_path):
    target = tmp_path / "run"
    write_run(SimulationConfig(steps=8), 0, "threshold", target, plots=False)
    assert {p.name for p in target.iterdir()} >= {
        "config.yaml",
        "trajectory.csv",
        "metadata.json",
        "metrics.json",
        "communication_events.csv",
        "actuator_events.csv",
        "observation_events.csv",
        "recovery_events.csv",
        "terminal_state.json",
    }
    cfg = yaml.safe_load((target / "config.yaml").read_text())
    assert cfg["seeds"] == [0]
    assert json.loads((target / "metadata.json").read_text())["source_sha256"]
    frame = pd.read_csv(target / "trajectory.csv")
    assert frame.time_seconds.tolist() == list(range(0, 8 * 300, 300))
    with pytest.raises(FileExistsError):
        write_run(SimulationConfig(steps=8), 0, "threshold", target, plots=False)


def test_all_sweeps_valid_and_paired_experiment(tmp_path):
    cfg = SimulationConfig(steps=12, seeds=[1, 2])
    for name in EXPERIMENTS:
        assert scenarios(name, cfg)
    f = run_experiment("controller_comparison", cfg, tmp_path / "comparison", plots=False)
    assert len(f) == 4
    for _, subset in f.groupby(["scenario", "seed"]):
        assert set(subset.controller) == {"threshold", "twin_assisted"}
    assert (tmp_path / "comparison" / "paired_summary.csv").exists()


@pytest.mark.parametrize(
    "script,args",
    [
        ("run_simulation.py", []),
        ("run_experiment.py", ["--name", "controller_comparison"]),
        ("run_all_experiments.py", []),
    ],
)
def test_cli_scripts(script, args, tmp_path):
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / script),
            "--steps",
            "8",
            "--seeds",
            "7",
            "--output",
            str(tmp_path / "cli"),
            "--no-plots",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
