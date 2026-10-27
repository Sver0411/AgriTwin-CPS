"""Paired offline measurement comparisons, separate from simulation-truth metrics."""

from pathlib import Path

import pandas as pd
import yaml

from agritwin_cps.data_io.replay import write_replay
from agritwin_cps.experiments.adaptive import paired_to_reference
from agritwin_cps.experiments.comparison import summarize
from agritwin_cps.simulation.runner import environment_metadata, reserve_output, write_json
from agritwin_cps.visualization.plots import metric_comparison_figure

METHODS = ("observation_corrected", "model_only", "ekf", "trust_ekf")


def run_measurement_experiment(
    source, mapping, replay, simulation, output: Path, methods=METHODS, plots=True, completed=None
):
    if not methods or len(set(methods)) != len(methods) or not set(methods) <= set(METHODS):
        raise ValueError("Choose distinct supported estimator methods")
    reserve_output(output)
    (output / "base_config.yaml").write_text(
        yaml.safe_dump(simulation.model_dump(mode="json")), encoding="utf-8"
    )
    (output / "data_config.yaml").write_text(
        yaml.safe_dump(
            {"import": mapping.model_dump(mode="json"), "replay": replay.model_dump(mode="json")}
        ),
        encoding="utf-8",
    )
    cases = [("as_configured", replay)]
    if replay.dropout_probability or replay.delay_rows or replay.packet_loss_probability:
        cases.insert(
            0,
            (
                "unmodified_delivery",
                replay.model_copy(
                    update={"dropout_probability": 0, "delay_rows": 0, "packet_loss_probability": 0}
                ),
            ),
        )
    total = len(cases) * len(methods) * len(simulation.seeds)
    rows = []
    for scenario, replay_case in cases:
        for method in methods:
            config = simulation.model_copy(deep=True)
            config.estimator.method = method
            if method in ("model_only", "observation_corrected"):
                config.estimator.replay_history_steps = 0
            for seed in config.seeds:
                _, metrics = write_replay(
                    source,
                    mapping,
                    replay_case,
                    config,
                    seed,
                    output / scenario / f"seed_{seed}" / method,
                    plots=False,
                )
                rows.append(
                    {
                        "experiment": "measurement_estimators",
                        "scenario": scenario,
                        "controller": method,
                        "seed": seed,
                        **metrics,
                    }
                )
                if completed:
                    completed(len(rows), total, f"{scenario}/{method} · seed {seed}")
    frame = pd.DataFrame(rows)
    summary = summarize(frame, ["experiment", "scenario", "controller"])
    paired = paired_to_reference(frame)
    for name, table in (
        ("per_seed", frame),
        ("summary", summary),
        ("paired_differences", paired),
        ("paired_summary", summarize(paired, ["experiment", "scenario", "controller"])),
    ):
        table.to_csv(output / f"measurement_{name}.csv", index=False)
    if plots:
        import matplotlib.pyplot as plt

        for scenario, _ in cases:
            subset = frame[frame.scenario == scenario]
            for prefix in ("measurement", "preupdate", "heldout", "masked_target_prediction"):
                metric = f"{prefix}_agreement_mae_temperature"
                if subset[metric].notna().any():
                    figure = metric_comparison_figure(
                        subset,
                        summary[summary.scenario == scenario],
                        paired[paired.scenario == scenario],
                        metric,
                        f"{prefix} temperature agreement",
                        "degC",
                    )
                    figure.savefig(output / f"{scenario}_{prefix}.png", dpi=140)
                    plt.close(figure)
    write_json(
        output / "metadata.json",
        {
            **environment_metadata(),
            "data_origin": mapping.origin,
            "dataset_id": mapping.dataset_id,
            "seeds": simulation.seeds,
            "methods": list(methods),
            "paired_reference": methods[0],
            "run_count": len(frame),
            "closed_loop_validation": False,
        },
    )
    write_json(output / "replay_comparison.json", {"status": "complete", "run_count": len(frame)})
    return frame
