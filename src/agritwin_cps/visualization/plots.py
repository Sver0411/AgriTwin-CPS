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


# Shared presentation palette. UI figures preserve native channel units and all raw samples.
STATE_COLORS = {"true": "#1D1D1F", "estimated": "#0071E3", "observed": "#8E8E93"}
RESEARCH_STYLE = {
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelcolor": "#515154",
    "text.color": "#1D1D1F",
    "axes.edgecolor": "#D2D2D7",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#ECECEF",
    "grid.alpha": 0.8,
    "axes.axisbelow": True,
    "legend.frameon": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
}


def environment_figure(frame: pd.DataFrame, bounds=None, channels=CHANNELS):
    """Truth/estimate lines and discrete accepted readings; NaNs are never filled or bridged."""
    names = {
        "temperature": "Air temperature",
        "humidity": "Air humidity",
        "moisture": "Soil moisture",
    }
    units = dict(zip(CHANNELS, UNITS, strict=True))
    with plt.rc_context(RESEARCH_STYLE):
        fig, axes = plt.subplots(
            len(channels),
            1,
            figsize=(11, 2.6 * len(channels)),
            sharex=True,
            squeeze=False,
            layout="constrained",
        )
        hours = frame.time_seconds / 3600
        for ax, channel in zip(axes.flat, channels, strict=True):
            if bounds:
                low, high = bounds[channel]
                ax.axhspan(low, high, color="#F5F5F7", label="Configured safe range")
            ax.plot(
                hours,
                frame[f"true_{channel}"],
                color=STATE_COLORS["true"],
                linewidth=1.6,
                label="Simulation truth",
            )
            ax.plot(
                hours,
                frame[f"estimated_{channel}"],
                color=STATE_COLORS["estimated"],
                linestyle="--",
                linewidth=1.5,
                label="Twin estimate",
            )
            ax.scatter(
                hours,
                frame[f"observed_{channel}"],
                color=STATE_COLORS["observed"],
                s=9,
                alpha=0.65,
                label="Accepted virtual observation",
                zorder=3,
            )
            ax.set_title(names[channel], loc="left")
            ax.set_ylabel(units[channel])
            ax.legend(ncol=2, fontsize=8, loc="best")
        axes[-1, 0].set_xlabel("Simulated time (h)")
        return fig


def estimation_error_figure(frame: pd.DataFrame):
    """Separate axes prevent comparing different physical units on an unlabelled scale."""
    with plt.rc_context(RESEARCH_STYLE):
        fig, axes = plt.subplots(3, 1, figsize=(11, 7.2), sharex=True, layout="constrained")
        for ax, channel, unit in zip(axes, CHANNELS, UNITS, strict=True):
            ax.plot(
                frame.time_seconds / 3600,
                frame[f"estimated_{channel}"] - frame[f"true_{channel}"],
                color=STATE_COLORS["estimated"],
                linewidth=1.2,
                label="Estimate − simulation truth",
            )
            ax.axhline(0, color="#86868B", linewidth=0.8)
            ax.set_title(f"{channel.title()} estimation error", loc="left")
            ax.set_ylabel(unit)
            ax.legend(fontsize=8)
        axes[-1].set_xlabel("Simulated time (h)")
        return fig


def control_actions_figure(frame: pd.DataFrame, fallback=None):
    with plt.rc_context(RESEARCH_STYLE):
        fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True, layout="constrained")
        for ax, name in zip(axes, ("ventilation", "irrigation"), strict=True):
            hours = frame.time_seconds / 3600
            mask = None if fallback is None else fallback[f"{name.title()} fallback"]
            if mask is not None and np.any(mask):
                ax.fill_between(
                    hours,
                    0,
                    1,
                    where=mask,
                    step="post",
                    color="#EEEEF0",
                    label="Fallback condition (derived)",
                )
            ax.step(
                hours,
                frame[f"command_{name}"],
                where="post",
                linestyle="--",
                color="#86868B",
                linewidth=1.5,
                label="Requested command",
            )
            ax.step(
                hours,
                frame[f"actual_{name}"],
                where="post",
                color="#1D1D1F",
                linewidth=1.7,
                label="Actual action",
            )
            ax.set_title(name.title(), loc="left")
            ax.set_ylabel("Normalized action [0, 1]")
            ax.set_ylim(-0.06, 1.18)
            ax.legend(ncol=3, fontsize=8, loc="upper right")
        axes[-1].set_xlabel("Simulated time (h)")
        return fig


def fault_timeline_figure(events: pd.DataFrame, time_range: tuple[float, float]):
    colors = {
        "Configured": "#AEAEB2",
        "Recorded": "#343438",
        "Validation rejection": "#86868B",
        "Derived condition": "#6E6E73",
        "Recovery observed": "#0071E3",
    }
    styles = {
        "Configured": "--",
        "Recorded": "-",
        "Validation rejection": ":",
        "Derived condition": "-.",
        "Recovery observed": "-",
    }
    from matplotlib.lines import Line2D

    with plt.rc_context(RESEARCH_STYLE):
        labels = list(dict.fromkeys(zip(events.evidence, events.event, strict=True)))
        fig, ax = plt.subplots(
            figsize=(11, max(3.2, len(labels) * 0.38 + 1.2)), layout="constrained"
        )
        for event in events.itertuples():
            position = labels.index((event.evidence, event.event))
            color = colors[event.evidence]
            if event.start_hours == event.end_hours:
                ax.scatter(event.start_hours, position, marker="D", color=color, s=32, zorder=3)
            else:
                ax.plot(
                    [event.start_hours, event.end_hours],
                    [position, position],
                    color=color,
                    linewidth=5 if event.evidence != "Configured" else 2,
                    linestyle=styles[event.evidence],
                    solid_capstyle="butt",
                )
        ax.set_yticks(range(len(labels)), [event for _, event in labels], fontsize=10)
        ax.invert_yaxis()
        ax.set_xlim(*time_range)
        ax.set_xlabel("Simulated time (h); conditions shown in sampled step bins")
        ax.set_title("Fault and recovery evidence", loc="left", pad=35)
        ax.legend(
            handles=[
                Line2D(
                    [0],
                    [0],
                    color=colors[stage],
                    linewidth=3,
                    linestyle=styles[stage],
                    marker="D" if stage == "Recovery observed" else "",
                    label=stage,
                )
                for stage in colors
                if stage in set(events.evidence)
            ],
            loc="lower left",
            bbox_to_anchor=(0, 1.01),
            ncol=3,
            fontsize=8,
        )
        return fig


def metric_comparison_figure(
    per_seed: pd.DataFrame,
    summary: pd.DataFrame,
    paired: pd.DataFrame,
    metric: str,
    title: str,
    unit: str,
):
    """Show every seed, mean/sample SD, and available paired deltas; always include zero."""
    colors = {"threshold": "#8E8E93", "twin_assisted": "#1D1D1F"}
    labels = {"threshold": "Threshold", "twin_assisted": "Twin-assisted"}
    seeds = sorted(per_seed.seed.unique())
    controllers = [c for c in colors if c in set(per_seed.controller)]
    has_pairs = not paired.empty and metric in paired and paired[metric].notna().any()
    with plt.rc_context(RESEARCH_STYLE):
        fig, axes = plt.subplots(1, 3 if has_pairs else 2, figsize=(12, 3.8), layout="constrained")
        for i, controller in enumerate(controllers):
            values = per_seed[per_seed.controller == controller].set_index("seed").reindex(seeds)
            positions = np.arange(len(seeds)) + (i - (len(controllers) - 1) / 2) * 0.18
            axes[0].scatter(
                positions,
                values[metric],
                color=colors[controller],
                marker=("o", "s")[i],
                s=35,
                label=labels[controller],
            )
            row = summary[(summary.controller == controller) & (summary.metric == metric)].iloc[0]
            if pd.notna(row["mean"]):
                axes[1].scatter(i, row["mean"], color=colors[controller], s=50, zorder=3)
                if pd.notna(row["std"]):
                    axes[1].errorbar(
                        i, row["mean"], yerr=row["std"], color=colors[controller], capsize=5
                    )
        axes[0].set_xticks(
            range(len(seeds)), [str(s) for s in seeds], rotation=30 if len(seeds) > 5 else 0
        )
        axes[0].set_xlabel("Random seed")
        axes[0].set_title("Individual seeds", loc="left")
        axes[0].legend(fontsize=8)
        axes[1].set_xticks(range(len(controllers)), [labels[c] for c in controllers])
        axes[1].set_title("Mean ± sample SD", loc="left")
        if has_pairs:
            valid = paired.set_index("seed").reindex(seeds)
            axes[2].scatter(range(len(seeds)), valid[metric], color="#0071E3", s=35)
            axes[2].set_xticks(
                range(len(seeds)), [str(s) for s in seeds], rotation=30 if len(seeds) > 5 else 0
            )
            axes[2].set_xlabel("Paired random seed")
            axes[2].set_title("Twin − threshold", loc="left")
        for ax in axes:
            ax.set_ylabel(unit)
            ax.axhline(0, color="#AEAEB2", linewidth=0.8)
        fig.suptitle(title)
        return fig
