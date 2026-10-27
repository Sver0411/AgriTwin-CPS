"""Evaluation-only diagnostics, resource counts and uncertainty checks from recorded data."""

import numpy as np

from agritwin_cps.models.greenhouse import CHANNELS


def diagnosis_statistics(labels, alarms) -> dict:
    labels, alarms = np.asarray(labels, bool), np.asarray(alarms, bool)
    tp, fp = int((labels & alarms).sum()), int((~labels & alarms).sum())
    fn, tn = int((labels & ~alarms).sum()), int((~labels & ~alarms).sum())
    return {
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "evaluated_count": len(labels),
        "true_positive_count": tp,
        "false_positive_count": fp,
        "false_negative_count": fn,
        "true_negative_count": tn,
    }


def adaptive_metrics(result, config) -> dict:
    f, dt = result.trajectory, config.dt_seconds
    metrics = {}
    sampling = result.sampling_events
    if not sampling.empty:
        for source, target in (
            ("sampled", "sample"),
            ("generated", "generated_observation"),
            ("valid_generated", "valid_generated_observation"),
            ("valid_received", "valid_observation_delivery_step"),
        ):
            metrics[f"{target}_count"] = int(sampling[source].sum())
        sampled_steps = sampling.loc[sampling.sampled, "step"].to_numpy()
        metrics["mean_sampling_interval_seconds"] = (
            float(np.diff(sampled_steps).mean() * dt) if len(sampled_steps) > 1 else None
        )
    for link in ("local", "remote"):
        events = result.communication_events
        events = events[events.link == link]
        delivered = events.status == "delivered"
        pending = events.status == "pending_at_horizon"
        metrics[f"{link}_sent_message_count"] = len(events)
        metrics[f"{link}_received_message_count"] = int(delivered.sum())
        metrics[f"{link}_lost_message_count"] = int((~delivered & ~pending).sum())
        for status in (
            "delivered",
            "packet_loss",
            "expired",
            "disconnected_at_send",
            "disconnected_at_receive",
            "pending_at_horizon",
        ):
            metrics[f"{link}_{status}_message_count"] = int((events.status == status).sum())
        metrics[f"{link}_pending_message_count"] = int(pending.sum())
        metrics[f"{link}_application_bytes"] = int(events.application_bytes.sum())
    metrics["total_application_bytes"] = sum(
        metrics[f"{link}_application_bytes"] for link in ("local", "remote")
    )
    bounds = (
        config.controller.temperature_safe_c,
        config.controller.humidity_safe_pct,
        config.controller.moisture_safe,
    )
    for channel, (low, high) in zip(CHANNELS, bounds, strict=True):
        actual = f[f"true_{channel}"].to_numpy()
        excess = np.maximum(low - actual, 0) + np.maximum(actual - high, 0)
        metrics[f"{channel}_violation_integral"] = float(excess.sum() * dt / 3600)
        metrics[f"max_observation_age_{channel}_seconds"] = int(
            f[f"observation_age_{channel}_steps"].max() * dt
        )
        std = f[f"std_{channel}"].to_numpy()
        valid = np.isfinite(std) & (std > 0)
        errors = f[f"estimated_{channel}"].to_numpy() - actual
        metrics[f"empirical_95_coverage_{channel}"] = (
            float((np.abs(errors[valid]) <= 1.96 * std[valid]).mean()) if valid.any() else None
        )
        metrics[f"normalized_squared_error_{channel}"] = (
            float(np.square(errors[valid] / std[valid]).mean()) if valid.any() else None
        )
        # Diagnose delivered observations, once per generated timestamp per channel.
        health = result.health_events
        h = health[(health.channel == channel) & (health.generated_step >= 0)]
        h = h.drop_duplicates("generated_step", keep="first")
        labels = [bool(f.iloc[int(g)][f"fault_label_{channel}"]) for g in h.generated_step]
        stats = diagnosis_statistics(labels, h.state == "confirmed_anomaly")
        metrics.update({f"diagnosis_{key}_{channel}": value for key, value in stats.items()})
        delays, censored = [], 0
        windows = [w for w in config.sensor.faults if w.channel == channel]
        for window in windows:
            if window.start_step >= len(f):
                continue
            detected = h[
                (h.generated_step >= window.start_step)
                & (h.generated_step < window.end_step)
                & (h.state == "confirmed_anomaly")
            ]
            if detected.empty:
                censored += 1
            else:
                delays.append((int(detected.step.min()) - window.start_step) * dt)
        metrics[f"diagnosis_detection_delay_{channel}_seconds"] = (
            float(np.mean(delays)) if delays else None
        )
        metrics[f"diagnosis_detection_censored_{channel}_count"] = censored
    metrics["uncertainty_fallback_seconds"] = int(f.uncertainty_fallback.sum() * dt)
    return metrics
