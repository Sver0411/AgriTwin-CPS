"""Presentation adapters for recorded evidence; no fault detection or control algorithm."""

import numpy as np
import pandas as pd

from agritwin_cps.models.greenhouse import CHANNELS
from agritwin_cps.ui.workspace import RunRecord

STAGES = (
    "Configured",
    "Recorded",
    "Validation rejection",
    "Derived condition",
    "Recovery observed",
)


def condition_intervals(mask, steps) -> list[tuple[int, int]]:
    """Convert sampled boolean conditions to half-open step bins for plotting only."""
    mask = np.asarray(mask, dtype=bool)
    edges = np.diff(np.r_[False, mask, False].astype(int))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    return [(int(steps[a]), int(steps[b - 1] + 1)) for a, b in zip(starts, ends, strict=True)]


def fallback_conditions(run: RunRecord) -> dict[str, np.ndarray]:
    """Explain the existing controller's validity predicate using recorded input ages.

    These are derived conditions, not engine detection flags. A baseline cache timestamp >= 0
    guarantees its value passed finite/range validation; estimates are recorded separately.
    """
    frame, config = run.result.trajectory, run.config.controller
    if all(f"control_valid_{c}" in frame for c in CHANNELS):
        valid = frame[[f"control_valid_{c}" for c in CHANNELS]].to_numpy(dtype=bool)
    elif run.controller == "threshold":
        valid = np.column_stack(
            [
                (frame[f"observed_timestamp_{c}_step"] >= 0)
                & (frame[f"observation_age_{c}_steps"] <= config.max_sensor_age_steps)
                for c in CHANNELS
            ]
        )
    else:
        valid = np.column_stack(
            [
                frame[f"estimated_{c}"].notna()
                & (frame[f"estimation_age_{c}_steps"] <= config.max_prediction_age_steps)
                for c in CHANNELS
            ]
        )
    return {"Ventilation fallback": ~valid[:, :2].all(axis=1), "Irrigation fallback": ~valid[:, 2]}


def evidence_timeline(run: RunRecord) -> pd.DataFrame:
    """Keep configured windows, runtime records, validation and recovery distinct."""
    frame, cfg = run.result.trajectory, run.config
    dt, horizon = cfg.dt_seconds, cfg.steps
    rows = []

    def add(label, stage, start, end, source, detail=""):
        if start >= horizon or end < 0:
            return
        rows.append(
            {
                "event": label,
                "evidence": stage,
                "start_step": max(0, start),
                "end_step": min(horizon, end),
                "source": source,
                "detail": detail,
            }
        )

    def mask_events(label, stage, mask, source, detail=""):
        for start, end in condition_intervals(mask, frame.step.to_numpy()):
            add(label, stage, start, end, source, detail)

    for fault in cfg.sensor.faults:
        add(
            f"Sensor {fault.kind} · {fault.channel}",
            "Configured",
            fault.start_step,
            fault.end_step,
            "config.sensor.faults",
            f"Magnitude: {fault.magnitude:g}",
        )
    for link in ("local", "remote"):
        settings = getattr(cfg.communication, link)
        for window in settings.outages:
            add(
                f"{link.title()} outage window",
                "Configured",
                window.start_step,
                window.end_step,
                f"config.communication.{link}.outages",
            )
        mask_events(
            f"{link.title()} outage flag",
            "Recorded",
            frame[f"{link}_outage"],
            f"trajectory.{link}_outage",
            "Engine condition, not a detected radio failure",
        )
    for window in cfg.actuator.failures:
        add(
            "Actuator failure window",
            "Configured",
            window.start_step,
            window.end_step,
            "config.actuator.failures",
        )
    missing = frame[[f"sensor_{c}" for c in CHANNELS]].isna().any(axis=1)
    if "sampled" in frame:
        missing &= frame.sampled
    mask_events(
        "Missing sensor samples",
        "Recorded",
        missing,
        "trajectory.sensor_*",
        "NaN at generation: configured missing and/or random dropout; cause not logged",
    )
    for reason, events in run.result.observation_events.groupby("reason"):
        if reason == "accepted":
            continue
        mask_events(
            f"Observation: {reason}",
            "Validation rejection",
            frame.step.isin(events.received_step),
            "observation_events.csv",
            "Input validation outcome; not identification of a drift/stuck fault",
        )
    messages = run.result.communication_events
    delayed = messages[
        (messages.status == "delivered") & (messages.received_step > messages.generated_step)
    ]
    for link, events in delayed.groupby("link"):
        mask_events(
            f"Delayed {link} delivery",
            "Recorded",
            frame.step.isin(events.received_step),
            "communication_events.csv",
            "Reception step exceeds generation step",
        )
    dropped = messages[
        messages.status.isin(
            ["packet_loss", "expired", "disconnected_at_send", "disconnected_at_receive"]
        )
    ]
    for (link, reason), events in dropped.groupby(["link", "status"]):
        mask_events(
            f"{link.title()}: {reason}",
            "Recorded",
            frame.step.isin(events.resolved_step),
            "communication_events.csv",
        )
    for status, events in run.result.actuator_events.groupby("status"):
        if status in ("failed", "limited"):
            mask_events(
                f"Actuator command {status}",
                "Recorded",
                frame.step.isin(events.execution_step),
                "actuator_events.csv",
            )
    for label, mask in fallback_conditions(run).items():
        mask_events(
            label,
            "Derived condition",
            mask,
            "recorded ages + controller validity rule",
            "Derived input validity; not a separately logged mode or fault detector",
        )
    for event in run.recovery.itertuples():
        if pd.notna(event.estimation_recovery_seconds):
            step = event.end_step + event.estimation_recovery_seconds / dt
            add(
                f"{event.kind.title()} estimation recovery",
                "Recovery observed",
                step,
                step,
                "recovery_events.csv",
                "Start of qualifying tolerance dwell; see censor flags",
            )
        if pd.notna(event.remote_resync_seconds):
            step = event.end_step + event.remote_resync_seconds / dt
            add(
                "Remote resynchronization",
                "Recovery observed",
                step,
                step,
                "recovery_events.csv",
                "Fresh telemetry received; distinct from estimation recovery",
            )
    result = pd.DataFrame(
        rows, columns=["event", "evidence", "start_step", "end_step", "source", "detail"]
    )
    result["start_hours"] = result.start_step * dt / 3600
    result["end_hours"] = result.end_step * dt / 3600
    return result
