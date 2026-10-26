"""Offline measurement replay, without plant truth or implied closed-loop validation."""

import hashlib
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import Field, model_validator

from agritwin_cps.config import Settings, SimulationConfig
from agritwin_cps.data_io.csv_import import ImportConfig, import_csv
from agritwin_cps.experiments.metrics import error_statistics
from agritwin_cps.models.greenhouse import CHANNELS, Action, Disturbance
from agritwin_cps.sensors.health import SensorHealth
from agritwin_cps.sensors.virtual_sensor import Observation
from agritwin_cps.simulation.runner import environment_metadata, reserve_output, write_json
from agritwin_cps.twin.ekf import create_estimator
from agritwin_cps.visualization.plots import save_replay


class ReplayConfig(Settings):
    start_time: str | None = None
    end_time: str | None = None
    partition: Literal["calibration", "development", "final_evaluation"] = "development"
    calibration_end_time: str | None = None
    development_end_time: str | None = None
    dropout_probability: float = Field(default=0, ge=0, le=1)
    delay_rows: int = Field(default=0, ge=0)
    max_gap_seconds: float = Field(default=86400, gt=0)
    assumed_outdoor_temperature_c: float = 21
    assumed_outdoor_humidity_pct: float = Field(default=65, ge=0, le=100)
    assumed_solar_proxy: float = Field(default=0, ge=0, le=1)
    assumed_evapotranspiration_proxy: float = Field(default=0.25, ge=0, le=1)
    assumed_ventilation: float = Field(default=0, ge=0, le=1)
    assumed_irrigation: float = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def splits(self):
        if self.partition == "final_evaluation" and not self.development_end_time:
            raise ValueError("Final evaluation requires a frozen development_end_time boundary")
        if self.calibration_end_time and self.development_end_time:
            if as_utc(self.calibration_end_time) >= as_utc(self.development_end_time):
                raise ValueError("Calibration must end before development")
        return self


def as_utc(value):
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def select_partition(frame: pd.DataFrame, config: ReplayConfig) -> pd.DataFrame:
    selected = frame
    if config.start_time:
        selected = selected[selected.timestamp >= as_utc(config.start_time)]
    if config.end_time:
        selected = selected[selected.timestamp < as_utc(config.end_time)]
    if config.partition == "calibration" and config.calibration_end_time:
        selected = selected[selected.timestamp < as_utc(config.calibration_end_time)]
    elif config.partition == "development":
        if config.calibration_end_time:
            selected = selected[selected.timestamp >= as_utc(config.calibration_end_time)]
        if config.development_end_time:
            selected = selected[selected.timestamp < as_utc(config.development_end_time)]
    elif config.partition == "final_evaluation":
        selected = selected[selected.timestamp >= as_utc(config.development_end_time)]
    if len(selected) < 2:
        raise ValueError("Selected partition/time range must contain at least two rows")
    gaps = selected.timestamp.diff().dt.total_seconds().dropna()
    if gaps.max() > config.max_gap_seconds:
        raise ValueError("Data gap exceeds max_gap_seconds; choose a continuous segment explicitly")
    return selected.reset_index(drop=True)


def write_replay(
    source: Path | bytes,
    mapping: ImportConfig,
    replay: ReplayConfig,
    simulation: SimulationConfig,
    seed: int,
    output: Path,
    plots=True,
    completed=None,
):
    frame, statistics = import_csv(source, mapping)
    frame = select_partition(frame, replay)
    reserve_output(output)
    data_config = {
        "import": mapping.model_dump(mode="json"),
        "replay": replay.model_dump(mode="json"),
    }
    (output / "data_config.yaml").write_text(yaml.safe_dump(data_config), encoding="utf-8")
    resolved = simulation.model_dump(mode="json")
    resolved["seeds"] = [seed]
    (output / "config.yaml").write_text(yaml.safe_dump(resolved), encoding="utf-8")
    estimator = create_estimator(simulation.estimator, simulation.twin, simulation.dt_seconds)
    health = SensorHealth(simulation.health, simulation.dt_seconds)
    draws = np.random.default_rng(seed).random((len(frame), 3))
    action = Action(replay.assumed_ventilation, replay.assumed_irrigation)
    disturbance = Disturbance(
        replay.assumed_outdoor_temperature_c,
        replay.assumed_outdoor_humidity_pct,
        replay.assumed_solar_proxy,
        replay.assumed_evapotranspiration_proxy,
    )
    rows = []
    for k in range(len(frame)):
        prior = estimator.state.copy()
        generated = k - replay.delay_rows
        packets, weights = [], {}
        observed = np.full(3, np.nan)
        if generated >= 0:
            observed = frame.loc[generated, list(CHANNELS)].to_numpy(dtype=float, copy=True)
            observed[draws[generated] < replay.dropout_probability] = np.nan
            packet = Observation(generated, tuple(observed))
            prediction = (
                estimator.prediction_at(generated) if hasattr(estimator, "prediction_at") else prior
            )
            weights[generated] = health.inspect(
                packet,
                prediction,
                k,
                generated_time_seconds=(
                    frame.timestamp.iloc[generated] - frame.timestamp.iloc[0]
                ).total_seconds(),
            )
            packets.append(packet)
        for i, channel in enumerate(CHANNELS):
            if not mapping.columns.get(channel):
                health.states[i], health.reasons[i] = "unknown", "unmapped_channel"
                health.abnormal_steps[i] = 0
        health.record(k)
        estimated = estimator.correct(packets, k, weights)
        std = (
            np.sqrt(np.diag(estimator.covariance))
            if hasattr(estimator, "covariance")
            else [np.nan] * 3
        )
        row = dict(
            step=k,
            timestamp=frame.timestamp.iloc[k].isoformat(),
            received_generated_row=generated if generated >= 0 else None,
            observed_timestamp=frame.timestamp.iloc[generated].isoformat()
            if generated >= 0
            else None,
            observation_delay_seconds=(
                frame.timestamp.iloc[k] - frame.timestamp.iloc[generated]
            ).total_seconds()
            if generated >= 0
            else None,
        )
        for i, channel in enumerate(CHANNELS):
            row[f"measured_{channel}"] = frame[channel].iloc[k]
            row[f"observed_{channel}"] = observed[i]
            row[f"estimated_{channel}"] = estimated[i]
            row[f"prediction_{channel}"] = prior[i]
            row[f"std_{channel}"] = std[i]
            row[f"artificially_heldout_{channel}"] = draws[k, i] < replay.dropout_probability
        rows.append(row)
        if k + 1 < len(frame):
            elapsed = (frame.timestamp.iloc[k + 1] - frame.timestamp.iloc[k]).total_seconds()
            estimator.predict(action, disturbance, elapsed_seconds=elapsed)
            health.dt_seconds = elapsed
        if completed:
            completed(k + 1, len(frame))
    trajectory = pd.DataFrame(rows)
    metrics = {}
    for channel in CHANNELS:
        for prefix, source_column, mask in (
            ("measurement_agreement", "estimated", np.ones(len(frame), bool)),
            ("preupdate_agreement", "prediction", np.ones(len(frame), bool)),
            (
                "heldout_agreement",
                "estimated",
                draws[:, CHANNELS.index(channel)] < replay.dropout_probability,
            ),
        ):
            errors = (trajectory[f"{source_column}_{channel}"] - trajectory[f"measured_{channel}"])[
                mask
            ]
            metrics.update(
                {
                    f"{prefix}_{name}_{channel}": value
                    for name, value in error_statistics(errors).items()
                }
            )
            metrics[f"{prefix}_valid_count_{channel}"] = int(errors.notna().sum())
    frame.to_csv(output / "imported.csv", index=False)
    trajectory.to_csv(output / "trajectory.csv", index=False)
    pd.DataFrame(health.events).to_csv(output / "health_events.csv", index=False)
    pd.DataFrame(
        getattr(estimator, "events", []), columns=["received_step", "generated_step", "reason"]
    ).to_csv(output / "estimator_events.csv", index=False)
    write_json(output / "import_statistics.json", statistics)
    write_json(output / "metrics.json", metrics)
    write_json(
        output / "metadata.json",
        {
            **environment_metadata(),
            "data_origin": mapping.origin,
            "dataset_id": mapping.dataset_id,
            "dataset_sha256": statistics["source_sha256"],
            "config_sha256": hashlib.sha256((output / "config.yaml").read_bytes()).hexdigest(),
            "data_config_sha256": hashlib.sha256(
                (output / "data_config.yaml").read_bytes()
            ).hexdigest(),
            "seed": seed,
            "partition": replay.partition,
            "assumed_inputs": replay.model_dump(mode="json"),
            "closed_loop_validation": False,
            "pending_delayed_row_count": min(replay.delay_rows, len(frame)),
        },
    )
    from agritwin_cps.simulation.schema import unit_for

    write_json(
        output / "schema.json",
        {
            "data_semantics": (
                "measured values and model estimates; no simulated or latent physical truth"
            ),
            "timestamp": "ISO 8601 UTC; generated timestamps retained separately",
            "age_and_history_units": (
                "original row index; prediction integrates actual elapsed seconds"
            ),
            "trajectory_units": {
                name: (
                    "ISO 8601 UTC"
                    if name in ("timestamp", "observed_timestamp")
                    else "original row index"
                    if name in ("step", "received_generated_row")
                    else "boolean"
                    if name.startswith("artificially_heldout_")
                    else unit_for(name)
                )
                for name in trajectory.columns
            },
            "metric_units": {name: unit_for(name) for name in metrics},
            "missing_values": "CSV empty / JSON null; unmeasured channels are not zeros",
        },
    )
    if plots:
        save_replay(trajectory, output / "replay.png")
    write_json(output / "replay.json", {"status": "complete", "row_count": len(frame)})
    return trajectory, metrics
