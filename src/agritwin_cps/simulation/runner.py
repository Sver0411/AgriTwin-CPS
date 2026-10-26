"""Artifact writer with resolved configurations, hashes and environment metadata."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yaml

from agritwin_cps.config import SimulationConfig, fault_window_notices
from agritwin_cps.experiments.comparison import paired_differences, summarize
from agritwin_cps.experiments.metrics import compute_metrics
from agritwin_cps.experiments.scenarios import scenarios
from agritwin_cps.simulation.engine import Strategy, simulate
from agritwin_cps.simulation.schema import artifact_schema
from agritwin_cps.visualization.plots import save_comparison, save_trajectory

SCHEMA_VERSION = "2.0"


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def environment_metadata() -> dict:
    def git(*args):
        try:
            result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        except OSError:
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    # Only repository hashes/status are recorded; no local identity, hostname or absolute paths.
    root = Path(__file__).resolve().parents[1]
    source_hashes = {}
    for path in sorted(root.rglob("*.py")):
        source_hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("agritwin-cps", "numpy", "pandas", "pydantic", "matplotlib", "PyYAML")
        },
        "git_commit": git("rev-parse", "HEAD"),
        "git_status": git("status", "--porcelain"),
        "source_sha256": source_hashes,
        "data_origin": "synthetic proxy model",
    }


def reserve_output(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise FileExistsError(f"Output directory must be empty: {path}")


def write_run(
    config: SimulationConfig, seed: int, controller: Strategy, output: Path, plots: bool = True
) -> dict:
    for notice in fault_window_notices(config):
        warnings.warn(notice, UserWarning, stacklevel=2)
    reserve_output(output)
    resolved = config.model_dump(mode="json")
    resolved["seeds"] = [seed]
    (output / "config.yaml").write_text(yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8")
    result = simulate(config, seed, controller)
    metrics, recovery = compute_metrics(result, config)
    result.trajectory.to_csv(output / "trajectory.csv", index=False)
    result.actuator_events.to_csv(output / "actuator_events.csv", index=False)
    result.observation_events.to_csv(output / "observation_events.csv", index=False)
    result.communication_events.to_csv(output / "communication_events.csv", index=False)
    recovery.to_csv(output / "recovery_events.csv", index=False)
    result.health_events.to_csv(output / "health_events.csv", index=False)
    result.estimator_events.to_csv(output / "estimator_events.csv", index=False)
    result.sampling_events.to_csv(output / "sampling_events.csv", index=False)
    write_json(output / "metrics.json", metrics)
    write_json(output / "schema.json", artifact_schema(result.trajectory.columns, metrics))
    write_json(
        output / "terminal_state.json",
        dict(
            zip(
                ("temperature_c", "humidity_pct", "moisture_fraction"),
                result.terminal_state,
                strict=True,
            )
        ),
    )
    write_json(
        output / "metadata.json",
        {
            **environment_metadata(),
            "estimator": config.estimator.method,
            "sampling": config.sampling.strategy,
            "controller": controller,
            "seed": seed,
            "config_sha256": hashlib.sha256((output / "config.yaml").read_bytes()).hexdigest(),
        },
    )
    if plots:
        save_trajectory(result.trajectory, output / "trajectory.png")
    write_json(output / "run.json", {"status": "complete", "seed": seed, "controller": controller})
    return metrics


def run_experiment(
    experiment: str,
    base: SimulationConfig,
    output: Path,
    plots: bool = True,
    run_plots: bool = True,
) -> pd.DataFrame:
    reserve_output(output)
    rows = []
    failure_rows = []
    for case in scenarios(experiment, base):
        for seed in case.seeds:
            for controller in ("threshold", "twin_assisted"):
                target = output / case.name / f"seed_{seed}" / controller
                metrics = write_run(case, seed, controller, target, plots and run_plots)
                identifiers = {
                    "experiment": experiment,
                    "scenario": case.name,
                    "controller": controller,
                    "seed": seed,
                }
                rows.append({**identifiers, **metrics})
                for metric, value in metrics.items():
                    if (
                        value is not None
                        and value > 0
                        and (
                            metric.endswith("violation_seconds")
                            or "censored_count" in metric
                            or metric == "failed_actuator_command_count"
                        )
                    ):
                        failure_rows.append({**identifiers, "metric": metric, "value": value})
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "per_seed.csv", index=False)
    summary = summarize(frame, ["experiment", "scenario", "controller"])
    summary.to_csv(output / "summary.csv", index=False)
    paired = paired_differences(frame)
    paired.to_csv(output / "paired_differences.csv", index=False)
    summarize(paired, ["experiment", "scenario", "controller"]).to_csv(
        output / "paired_summary.csv", index=False
    )
    pd.DataFrame(
        failure_rows, columns=["experiment", "scenario", "controller", "seed", "metric", "value"]
    ).to_csv(output / "failure_cases.csv", index=False)
    write_json(
        output / "metadata.json",
        {
            **environment_metadata(),
            "experiment": experiment,
            "seeds": base.seeds,
            "run_count": len(frame),
        },
    )
    if plots:
        save_comparison(summary, output / "comparison.png")
    return frame
