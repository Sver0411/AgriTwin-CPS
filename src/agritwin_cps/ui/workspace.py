"""UI experiment snapshots and exports, backed by the existing artifact runner.

Draft settings live separately in Streamlit session state. Only complete runs get a manifest,
so a refresh can restore the most recent successful experiment without inventing results.
"""

import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import yaml

from agritwin_cps.config import SimulationConfig, load_config
from agritwin_cps.experiments.comparison import paired_differences, summarize
from agritwin_cps.simulation.engine import SimulationResult
from agritwin_cps.simulation.runner import environment_metadata, write_json, write_run

CONTROLLERS = {"threshold": "Threshold control", "twin_assisted": "Twin-assisted control"}
ESTIMATORS = {"observation_corrected": "Observation-corrected", "model_only": "Model-only"}
PRESETS = {
    "Nominal Operation": "nominal.yaml",
    "Sensor Noise": "sensor_noise.yaml",
    "Missing Observations": "sensor_dropout.yaml",
    "Sensor Drift": "sensor_drift.yaml",
    "Communication Outage": "communication_outage.yaml",
    "Model Mismatch": "model_mismatch.yaml",
}


def request_signature(config: SimulationConfig, controllers: list[str]) -> str:
    payload = {"configuration": config.model_dump(mode="json"), "controllers": sorted(controllers)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass
class RunRecord:
    directory: Path
    config: SimulationConfig
    seed: int
    controller: str
    result: SimulationResult
    metrics: dict
    recovery: pd.DataFrame

    @property
    def label(self) -> str:
        return f"{CONTROLLERS[self.controller]} · seed {self.seed}"


@dataclass
class ExperimentRecord:
    directory: Path
    config: SimulationConfig
    controllers: list[str]
    signature: str
    created_utc: str
    runs: list[RunRecord]

    @property
    def per_seed(self) -> pd.DataFrame:
        # Statistics remain defined by experiments.comparison, not by the interface.
        return pd.read_csv(self.directory / "per_seed.csv")


def load_run(directory: Path) -> RunRecord:
    config = load_config(directory / "config.yaml")
    metadata = json.loads((directory / "metadata.json").read_text())
    terminal = json.loads((directory / "terminal_state.json").read_text())
    result = SimulationResult(
        trajectory=pd.read_csv(directory / "trajectory.csv"),
        actuator_events=pd.read_csv(directory / "actuator_events.csv"),
        observation_events=pd.read_csv(directory / "observation_events.csv"),
        terminal_state=[
            terminal[k] for k in ("temperature_c", "humidity_pct", "moisture_fraction")
        ],
        communication_events=pd.read_csv(directory / "communication_events.csv"),
    )
    return RunRecord(
        directory,
        config,
        metadata["seed"],
        metadata["controller"],
        result,
        json.loads((directory / "metrics.json").read_text()),
        pd.read_csv(directory / "recovery_events.csv"),
    )


def saved_experiments(results_root: Path) -> list[Path]:
    return sorted((results_root / "ui_runs").glob("*/experiment.json"), reverse=True)


def load_experiment(manifest: Path) -> ExperimentRecord:
    data = json.loads(manifest.read_text())
    directory = manifest.parent
    return ExperimentRecord(
        directory,
        load_config(directory / "config.yaml"),
        data["controllers"],
        data["signature"],
        data["created_utc"],
        [load_run(directory / p) for p in data["runs"]],
    )


def execute_experiment(
    config: SimulationConfig,
    controllers: list[str],
    results_root: Path,
    completed: Callable[[int, int, str], None] | None = None,
) -> ExperimentRecord:
    """Write real CLI-compatible artifacts once, then read exactly those artifacts for display."""
    created = datetime.now(UTC)
    directory = (
        results_root / "ui_runs" / (created.strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:6])
    )
    directory.mkdir(parents=True)
    (directory / "config.yaml").write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    records, rows = [], []
    total = len(config.seeds) * len(controllers)
    for seed in config.seeds:
        for controller in controllers:
            # Scenario names are metadata, not paths; keep the on-disk layout fixed.
            relative = Path("runs") / f"seed_{seed}" / controller
            target = directory / relative
            metrics = write_run(config, seed, controller, target, plots=False)
            records.append(str(relative))
            rows.append(
                {
                    "experiment": "interactive",
                    "scenario": config.name,
                    "seed": seed,
                    "controller": controller,
                    **metrics,
                }
            )
            if completed:
                completed(len(rows), total, f"{CONTROLLERS[controller]} · seed {seed}")
    per_seed = pd.DataFrame(rows)
    per_seed.to_csv(directory / "per_seed.csv", index=False)
    summarize(per_seed, ["experiment", "scenario", "controller"]).to_csv(
        directory / "summary.csv", index=False
    )
    if set(controllers) == set(CONTROLLERS):
        paired = paired_differences(per_seed)
        paired.to_csv(directory / "paired_differences.csv", index=False)
        summarize(paired, ["experiment", "scenario", "controller"]).to_csv(
            directory / "paired_summary.csv", index=False
        )
    write_json(
        directory / "metadata.json",
        {
            **environment_metadata(),
            "experiment": "interactive",
            "seeds": config.seeds,
            "run_count": total,
        },
    )
    # This file is the completion marker; partial/failed runs are never restored as successes.
    write_json(
        directory / "experiment.json",
        {
            "created_utc": created.isoformat(),
            "signature": request_signature(config, controllers),
            "controllers": controllers,
            "runs": records,
        },
    )
    return load_experiment(directory / "experiment.json")


def comparison_sources(results_root: Path) -> list[Path]:
    """Only discover actual aggregate artifacts, including existing command-line experiments."""
    return sorted(
        (
            p.parent
            for p in results_root.rglob("per_seed.csv")
            if (p.parent / "summary.csv").exists()
        ),
        reverse=True,
    )


def comparison_json(directory: Path) -> bytes:
    payload = {}
    for name in ("per_seed", "summary", "paired_differences", "paired_summary"):
        path = directory / f"{name}.csv"
        if path.exists():
            frame = pd.read_csv(path)
            # Preserve numeric precision and export absent statistics as null, never zero.
            payload[name] = (
                frame.astype(object).where(frame.notna(), None).to_dict(orient="records")
            )
    payload["metadata"] = json.loads((directory / "metadata.json").read_text())
    return (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode()


def experiment_archive(directory: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix in (".csv", ".json", ".yaml"):
                archive.write(path, str(path.relative_to(directory)))
    return buffer.getvalue()
