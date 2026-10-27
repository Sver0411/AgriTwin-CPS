"""Evaluation only: this module may compare estimates with simulated plant truth."""

import numpy as np
import pandas as pd

from agritwin_cps.config import SimulationConfig
from agritwin_cps.experiments.adaptive_metrics import adaptive_metrics
from agritwin_cps.models.greenhouse import CHANNELS
from agritwin_cps.simulation.engine import SimulationResult


def error_statistics(errors) -> dict[str, float | None]:
    values = np.asarray(errors, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"mae": None, "rmse": None, "bias": None}
    return {
        "mae": float(np.abs(values).mean()),
        "rmse": float(np.sqrt((values**2).mean())),
        "bias": float(values.mean()),
    }


def dwell_recovery(good, start: int, dwell: int, stop: int | None = None) -> int | None:
    """Earliest index with dwell consecutive acceptable samples, or right censoring."""
    stop = len(good) if stop is None else stop
    for index in range(start, stop - dwell + 1):
        if np.asarray(good[index : index + dwell]).all():
            return index - start
    return None


def merged_windows(windows) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted((w.start_step, w.end_step) for w in windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def recovery_events(frame: pd.DataFrame, config: SimulationConfig) -> pd.DataFrame:
    errors = np.column_stack([frame[f"estimated_{c}"] - frame[f"true_{c}"] for c in CHANNELS])
    good = (np.abs(errors) <= config.controller.recovery_tolerance).all(axis=1)
    groups = {
        "sensor": config.sensor.faults,
        "local": config.communication.local.outages,
        "remote": config.communication.remote.outages,
    }
    records = []
    for kind, windows in groups.items():
        merged = merged_windows(windows)
        for index, (start, end) in enumerate(merged):
            if start >= len(frame):
                continue
            stop = min(len(frame), merged[index + 1][0] if index + 1 < len(merged) else len(frame))
            delay = (
                dwell_recovery(good, end, config.controller.recovery_dwell_steps, stop)
                if kind != "remote"
                else None
            )
            sync = None
            sync_errors = {f"sync_error_{c}": None for c in CHANNELS}
            if kind == "remote":
                eligible = frame[
                    (frame.step >= end)
                    & (frame.step < stop)
                    & frame.remote_received
                    & (frame.remote_generated_step >= end)
                ]
                if not eligible.empty:
                    first = eligible.iloc[0]
                    sync = float((first.step - end) * config.dt_seconds)
                    sync_errors = {
                        f"sync_error_{c}": float(first[f"sync_error_{c}"]) for c in CHANNELS
                    }
            records.append(
                {
                    "kind": kind,
                    "start_step": start,
                    "end_step": end,
                    "observation_stop_step": stop,
                    "estimation_recovery_seconds": None
                    if delay is None
                    else delay * config.dt_seconds,
                    "estimation_recovery_censored": delay is None if kind != "remote" else None,
                    "estimation_recovery_applicable": kind != "remote",
                    "remote_resync_seconds": sync,
                    "remote_resync_censored": sync is None if kind == "remote" else None,
                    **sync_errors,
                }
            )
    columns = [
        "kind",
        "start_step",
        "end_step",
        "observation_stop_step",
        "estimation_recovery_seconds",
        "estimation_recovery_censored",
        "estimation_recovery_applicable",
        "remote_resync_seconds",
        "remote_resync_censored",
        *[f"sync_error_{c}" for c in CHANNELS],
    ]
    return pd.DataFrame(records, columns=columns)


def compute_metrics(
    result: SimulationResult, config: SimulationConfig
) -> tuple[dict, pd.DataFrame]:
    f, dt = result.trajectory, config.dt_seconds
    output: dict[str, float | int | None] = {"horizon_seconds": len(f) * dt}
    masks = {
        "sensor_fault": f.sensor_fault_active.to_numpy(),
        "sensor_fault_window": f.sensor_fault_configured.to_numpy(),
        "communication_outage": (f.local_outage | f.remote_outage).to_numpy(),
        "local_outage": f.local_outage.to_numpy(),
        "remote_outage": f.remote_outage.to_numpy(),
    }
    outside = []
    bounds = (
        config.controller.temperature_safe_c,
        config.controller.humidity_safe_pct,
        config.controller.moisture_safe,
    )
    stale = np.zeros(len(f), dtype=bool)
    for channel, (low, high) in zip(CHANNELS, bounds, strict=True):
        errors = f[f"estimated_{channel}"] - f[f"true_{channel}"]
        for name, value in error_statistics(errors).items():
            output[f"{name}_{channel}"] = value
        for label, mask in masks.items():
            for name, value in error_statistics(errors[mask]).items():
                output[f"{name}_{channel}_during_{label}"] = value
        output[f"valid_observation_coverage_{channel}"] = float(
            f[f"observed_{channel}"].notna().mean()
        )
        output[f"max_estimation_age_{channel}_seconds"] = int(
            f[f"estimation_age_{channel}_steps"].max() * dt
        )
        violation = ((f[f"true_{channel}"] < low) | (f[f"true_{channel}"] > high)).to_numpy()
        output[f"{channel}_violation_seconds"] = int(violation.sum() * dt)
        outside.append(violation)
        stale |= (f[f"observed_timestamp_{channel}_step"] < 0) | (
            f[f"observation_age_{channel}_steps"] > config.controller.max_sensor_age_steps
        )
    output["any_safe_range_violation_seconds"] = int(np.any(outside, axis=0).sum() * dt)
    output["stale_local_data_seconds"] = int(stale.sum() * dt)
    remote_stale = (f.remote_generated_step < 0) | (
        f.remote_age_steps > config.communication.remote.max_age_steps
    )
    output["stale_remote_data_seconds"] = int(remote_stale.sum() * dt)
    for actuator in ("ventilation", "irrigation"):
        actual = f[f"actual_{actuator}"].to_numpy()
        previous = np.r_[0.0, actual[:-1]]
        output[f"{actuator}_activation_count"] = int(((actual > 0) & (previous == 0)).sum())
        output[f"{actuator}_switch_count"] = int((actual != previous).sum())
    output["irrigation_amount_fraction"] = float(
        f.actual_irrigation.sum() * dt / 3600 * config.plant.irrigation_fraction_per_h
    )
    output["ventilation_effort_hours"] = float(f.actual_ventilation.sum() * dt / 3600)
    statuses = result.actuator_events.get("status", pd.Series(dtype=str))
    output["failed_actuator_command_count"] = int((statuses == "failed").sum())
    output["limited_actuator_command_count"] = int((statuses == "limited").sum())
    output["pending_actuator_command_count"] = len(f) - len(statuses)
    for link in ("local", "remote"):
        outage = f[f"{link}_outage"]
        output[f"safe_range_violation_during_{link}_outage_seconds"] = int(
            (np.any(outside, axis=0) & outage).sum() * dt
        )
        output[f"stale_local_data_during_{link}_outage_seconds"] = int((stale & outage).sum() * dt)
        output[f"local_continuity_during_{link}_outage"] = (
            float(f.loc[outage, "local_control_executed"].mean()) if outage.any() else None
        )
    output["local_control_continuity"] = float(f.local_control_executed.mean())
    output["settling_time_seconds"] = None  # No equilibrium target in diurnal experiments.
    recovery = recovery_events(f, config)
    for kind in ("sensor", "local", "remote"):
        events = recovery[recovery.kind == kind]
        output[f"{kind}_recovery_event_count"] = len(events)
        valid = events.estimation_recovery_seconds.dropna()
        output[f"{kind}_estimation_recovery_seconds"] = float(valid.mean()) if len(valid) else None
        output[f"{kind}_recovery_censored_count"] = (
            int(events.estimation_recovery_censored.sum()) if kind != "remote" else None
        )
        if kind == "remote":
            valid = events.remote_resync_seconds.dropna()
            output["remote_resync_seconds"] = float(valid.mean()) if len(valid) else None
            output["remote_resync_censored_count"] = int(events.remote_resync_censored.sum())
            for channel in CHANNELS:
                valid = events[f"sync_error_{channel}"].dropna()
                output[f"post_recovery_sync_error_{channel}"] = (
                    float(valid.mean()) if len(valid) else None
                )
    output.update(adaptive_metrics(result, config))
    return output, recovery
