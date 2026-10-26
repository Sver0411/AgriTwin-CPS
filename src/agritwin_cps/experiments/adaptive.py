"""Predeclared paired comparisons that reuse the simulation artifact writer."""

from pathlib import Path

import pandas as pd
import yaml

from agritwin_cps.config import SimulationConfig
from agritwin_cps.experiments.comparison import IDENTIFIERS, summarize
from agritwin_cps.simulation.runner import (
    environment_metadata,
    reserve_output,
    write_json,
    write_run,
)
from agritwin_cps.visualization.plots import save_comparison, save_resource_tradeoff

ADAPTIVE_EXPERIMENTS = (
    "estimators",
    "diagnostics",
    "sampling",
    "fault_severity",
    "mismatch",
    "budget",
    "delay_loss",
    "resources",
)


def variants(group: str, base: SimulationConfig):
    """Return scenario/algorithm/config triples, with no data-driven parameter selection."""
    if group not in ADAPTIVE_EXPERIMENTS:
        raise ValueError(f"Unknown adaptive experiment: {group}")
    common = base.model_dump(mode="json")
    common["estimator"]["method"] = "trust_ekf"
    if group not in ("sampling", "budget", "resources"):
        common["sampling"]["strategy"] = "fixed"
    definitions = []
    if group == "estimators":
        definitions = [
            ("shared", m, {"method": m}, {})
            for m in ("model_only", "observation_corrected", "ekf", "trust_ekf")
        ]
    elif group == "diagnostics":
        definitions = [
            ("shared", m, {}, {"health": {"method": m}})
            for m in ("basic", "residual", "persistent")
        ]
    elif group in ("sampling", "resources"):
        definitions = [
            ("shared", m, {}, {"sampling": {"strategy": m}})
            for m in ("fixed", "change", "uncertainty", "trust_change", "event")
        ]
    elif group == "budget":
        for fraction in (0.0, 0.25, 0.5, 1.0):
            for policy in ("fixed", "trust_change"):
                definitions.append(
                    (
                        f"budget_{fraction:g}",
                        policy,
                        {},
                        {
                            "sampling": {
                                "strategy": policy,
                                "local_byte_budget": int(base.steps * 34 * fraction),
                            }
                        },
                    )
                )
    elif group in ("fault_severity", "mismatch"):
        factors = (0.0, 1.0, 2.0, 4.0) if group == "fault_severity" else (0.5, 1.0, 1.5)
        for factor in factors:
            for method in ("ekf", "trust_ekf"):
                changes = (
                    {
                        "sensor": {
                            "faults": [
                                {
                                    "channel": "temperature",
                                    "kind": "bias",
                                    "magnitude": 3 * factor,
                                    "start_step": base.steps // 3,
                                    "end_step": max(base.steps // 3 + 1, 2 * base.steps // 3),
                                }
                            ]
                        }
                    }
                    if group == "fault_severity"
                    else {
                        "twin": {
                            "solar_heat_c_per_h": base.plant.solar_heat_c_per_h * factor,
                            "moisture_loss_per_h": base.plant.moisture_loss_per_h * factor,
                        }
                    }
                )
                definitions.append((f"factor_{factor:g}", method, {"method": method}, changes))
    else:
        for delay, loss in ((0, 0.0), (2, 0.1), (5, 0.3)):
            for label, method, history in (
                ("ekf_current", "ekf", 0),
                ("ekf_replay", "ekf", 24),
                ("trust_replay", "trust_ekf", 24),
            ):
                definitions.append(
                    (
                        f"delay_{delay}_loss_{loss:g}",
                        label,
                        {
                            "method": method,
                            "replay_history_steps": history,
                            "max_observation_age_steps": 24,
                        },
                        {
                            "communication": {
                                "local": {
                                    "delay_steps": delay,
                                    "packet_loss": loss,
                                    "max_age_steps": 24,
                                    "outages": [
                                        {
                                            "start_step": base.steps // 3,
                                            "end_step": max(base.steps // 3 + 1, base.steps // 2),
                                        }
                                    ],
                                }
                            }
                        },
                    )
                )
    for scenario, label, estimator, changes in definitions:
        data = SimulationConfig.model_validate(common).model_dump(mode="json")
        data["estimator"].update(estimator)
        if data["estimator"]["method"] in ("model_only", "observation_corrected"):
            data["estimator"]["replay_history_steps"] = 0
        for section, values in changes.items():
            if section == "communication":
                data[section]["local"].update(values["local"])
            else:
                data[section].update(values)
        if group == "fault_severity" and scenario == "factor_0":
            data["sensor"]["faults"] = []
        data["name"] = f"{group}_{scenario}_{label}"
        yield scenario, label, SimulationConfig.model_validate(data)


def paired_to_reference(frame: pd.DataFrame) -> pd.DataFrame:
    """Pair every variant with the first declared variant in its scenario, by seed."""
    metrics = [c for c in frame if c not in IDENTIFIERS]
    rows = []
    for (experiment, scenario), subset in frame.groupby(["experiment", "scenario"], sort=False):
        labels = subset.controller.unique()
        reference = subset[subset.controller == labels[0]].set_index("seed")
        for label in labels[1:]:
            other = subset[subset.controller == label].set_index("seed")
            delta = other[metrics] - reference[metrics]
            delta = delta.reset_index().assign(
                experiment=experiment, scenario=scenario, controller=f"{label}_minus_{labels[0]}"
            )
            rows.append(delta)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=frame.columns)


def run_adaptive_experiment(
    group: str,
    base: SimulationConfig,
    output: Path,
    plots=True,
    completed=None,
    selected_variants: list[str] | None = None,
) -> pd.DataFrame:
    reserve_output(output)
    (output / "base_config.yaml").write_text(
        yaml.safe_dump(base.model_dump(mode="json")), encoding="utf-8"
    )
    planned = [
        v for v in variants(group, base) if selected_variants is None or v[1] in selected_variants
    ]
    if not planned:
        raise ValueError("Select at least one declared variant")
    total = len(planned) * len(base.seeds)
    rows, failures = [], []
    for scenario, label, config in planned:
        for seed in config.seeds:
            metrics = write_run(
                config,
                seed,
                "twin_assisted",
                output / scenario / f"seed_{seed}" / label,
                plots=False,
            )
            identifiers = dict(experiment=group, scenario=scenario, controller=label, seed=seed)
            rows.append({**identifiers, **metrics})
            for metric, value in metrics.items():
                if (
                    value is not None
                    and value > 0
                    and (
                        "violation_seconds" in metric
                        or "censored" in metric
                        or "failed_actuator" in metric
                    )
                ):
                    failures.append({**identifiers, "metric": metric, "value": value})
            if completed:
                completed(len(rows), total, f"{label} · seed {seed}")
    frame = pd.DataFrame(rows)
    summary = summarize(frame, ["experiment", "scenario", "controller"])
    paired = paired_to_reference(frame)
    for name, table in (
        ("per_seed", frame),
        ("summary", summary),
        ("paired_differences", paired),
        ("paired_summary", summarize(paired, ["experiment", "scenario", "controller"])),
    ):
        table.to_csv(output / f"{name}.csv", index=False)
    pd.DataFrame(failures, columns=[*IDENTIFIERS, "metric", "value"]).to_csv(
        output / "failure_cases.csv", index=False
    )
    write_json(
        output / "metadata.json",
        {
            **environment_metadata(),
            "experiment": group,
            "seeds": base.seeds,
            "run_count": len(frame),
            "controller": "twin_assisted",
            "variant_column": "controller",
            "paired_reference": "first declared variant per scenario",
        },
    )
    if plots:
        save_comparison(summary, output / "comparison.png")
        if group in ("sampling", "budget", "resources"):
            save_resource_tradeoff(frame, output / "resource_tradeoff.png")
    write_json(output / "adaptive_experiment.json", {"status": "complete", "run_count": len(frame)})
    return frame
