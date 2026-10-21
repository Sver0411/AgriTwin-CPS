"""Plots from computed trajectories; all values represent simulations."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from agritwin_cps.models.greenhouse import CHANNELS

UNITS = ("°C", "%RH", "fraction")


def trajectory_figure(frame: pd.DataFrame):
    fig, axes = plt.subplots(6, 1, figsize=(11, 15), sharex=True, layout="constrained")
    hours = frame.time_seconds / 3600
    for i, (channel, unit) in enumerate(zip(CHANNELS, UNITS, strict=True)):
        ax = axes[i]
        for prefix, style in (("true", "-"), ("estimated", "--"), ("observed", ".")):
            ax.plot(hours, frame[f"{prefix}_{channel}"], style, label=prefix, markersize=2)
        ax.set_ylabel(f"{channel}\n({unit})")
        ax.legend(loc="upper right", ncol=3)
    for name in ("ventilation", "irrigation"):
        axes[3].step(hours, frame[f"actual_{name}"], where="post", label=f"actual {name}")
        axes[3].plot(hours, frame[f"command_{name}"], ":", label=f"command {name}", alpha=0.6)
    axes[3].set_ylabel("Action [0, 1]")
    axes[3].legend(ncol=2)
    scales = (1.0, 5.0, 0.03)
    for channel, scale in zip(CHANNELS, scales, strict=True):
        error = (frame[f"estimated_{channel}"] - frame[f"true_{channel}"]) / scale
        axes[4].plot(hours, error, label=channel)
    axes[4].set_ylabel("Scaled error\n(1°C / 5%RH / 0.03)")
    axes[4].legend(ncol=3)
    for i, field in enumerate(("sensor_fault_active", "local_outage", "remote_outage")):
        if field in frame:
            axes[5].fill_between(
                hours, i, i + 0.7 * frame[field].astype(float), step="post", label=field
            )
    axes[5].set_ylabel("Fault timeline")
    axes[5].set_yticks([])
    if "sensor_fault_active" in frame:
        axes[5].legend(ncol=3)
    axes[5].set_xlabel("Simulated time (h)")
    fig.suptitle("AgriTwin-CPS — synthetic greenhouse simulation")
    return fig


def save_trajectory(frame: pd.DataFrame, path: Path) -> None:
    fig = trajectory_figure(frame)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def save_comparison(summary: pd.DataFrame, path: Path) -> None:
    panels = (
        ("temperature_violation_seconds", "Temperature outside safe range (s)"),
        ("moisture_violation_seconds", "Soil moisture outside safe range (s)"),
        ("mae_temperature", "Temperature estimation MAE (°C)"),
        ("irrigation_amount_fraction", "Irrigation input proxy (fraction)"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout="constrained")
    controllers = ("threshold", "twin_assisted")
    for ax, (metric, title) in zip(axes.flat, panels, strict=True):
        selected = summary[summary.metric == metric]
        cases = selected.scenario.drop_duplicates().tolist()
        positions = np.arange(len(cases))
        for i, controller in enumerate(controllers):
            values = (
                selected[selected.controller == controller].set_index("scenario").reindex(cases)
            )
            ax.bar(
                positions + (i - 0.5) * 0.36,
                values["mean"],
                width=0.36,
                yerr=values["std"].fillna(0),
                capsize=3,
                label=controller,
            )
        prefix = str(selected.experiment.iloc[0]) + "_" if "experiment" in selected else ""
        labels = [case.removeprefix(prefix) for case in cases]
        ax.set_xticks(positions, labels, rotation=25 if len(cases) > 1 else 0, fontsize=9)
        ax.set_title(title)
        ax.legend(fontsize=8)
    fig.suptitle("Simulation controller comparison — mean ± sample SD, paired seeds")
    fig.savefig(path, dpi=140)
    plt.close(fig)
