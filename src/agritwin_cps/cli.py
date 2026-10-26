"""Run reproducible simulations and predeclared experiments without the optional UI."""

import argparse
from pathlib import Path

from agritwin_cps.config import SimulationConfig, load_config
from agritwin_cps.experiments.adaptive import ADAPTIVE_EXPERIMENTS, run_adaptive_experiment
from agritwin_cps.experiments.scenarios import EXPERIMENTS
from agritwin_cps.simulation.runner import reserve_output, run_experiment, write_run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["simulate", "experiment", "all", "adaptive", "replay", "replay-experiment"]
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--output", default="results/run")
    parser.add_argument(
        "--controller", choices=["threshold", "twin_assisted"], default="twin_assisted"
    )
    parser.add_argument(
        "--estimator", choices=["model_only", "observation_corrected", "ekf", "trust_ekf"]
    )
    parser.add_argument(
        "--methods", nargs="+", choices=["model_only", "observation_corrected", "ekf", "trust_ekf"]
    )
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--data-config", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--steps", type=int)
    parser.add_argument(
        "--name", choices=[*EXPERIMENTS, *ADAPTIVE_EXPERIMENTS], default="controller_comparison"
    )
    parser.add_argument(
        "--summary-plots-only",
        action="store_true",
        help="In experiments, save comparison plots and skip individual run plots",
    )
    parser.add_argument("--no-plots", action="store_true", help="Disable all figures explicitly")
    args = parser.parse_args(argv)
    data = load_config(args.config).model_dump()
    if args.steps is not None:
        data["steps"] = args.steps
    if args.seeds is not None:
        data["seeds"] = args.seeds
    if args.estimator is not None:
        data["estimator"]["method"] = args.estimator
    config = SimulationConfig.model_validate(data)
    output = Path(args.output)
    if args.mode in ("replay", "replay-experiment"):
        from agritwin_cps.data_io.csv_import import load_data_config
        from agritwin_cps.data_io.replay import write_replay

        if args.csv is None or args.data_config is None:
            parser.error("replay mode requires --csv and --data-config")
        mapping, replay_config = load_data_config(args.data_config)
        seed = args.seed if args.seed is not None else config.seeds[0]
        if seed < 0:
            parser.error("--seed must be nonnegative")
        if args.mode == "replay":
            write_replay(
                args.csv, mapping, replay_config, config, seed, output, plots=not args.no_plots
            )
        else:
            from agritwin_cps.experiments.measurement import METHODS, run_measurement_experiment

            if args.seed is not None:
                config.seeds = [seed]
            run_measurement_experiment(
                args.csv,
                mapping,
                replay_config,
                config,
                output,
                methods=args.methods or METHODS,
                plots=not args.no_plots,
            )
    elif args.mode == "simulate":
        seed = args.seed if args.seed is not None else config.seeds[0]
        if seed < 0:
            parser.error("--seed must be nonnegative")
        write_run(config, seed, args.controller, output, plots=not args.no_plots)
    elif args.mode == "adaptive":
        if args.name not in ADAPTIVE_EXPERIMENTS:
            parser.error("adaptive mode requires --name from " + ", ".join(ADAPTIVE_EXPERIMENTS))
        run_adaptive_experiment(args.name, config, output, plots=not args.no_plots)
    elif args.mode == "experiment":
        if args.name not in EXPERIMENTS:
            parser.error("Use adaptive mode for the new A–H experiment groups")
        run_experiment(
            args.name,
            config,
            output,
            plots=not args.no_plots,
            run_plots=not args.summary_plots_only,
        )
    else:
        reserve_output(output)
        for name in EXPERIMENTS:
            print(f"Running {name} ...", flush=True)
            frame = run_experiment(
                name,
                config,
                output / name,
                plots=not args.no_plots,
                run_plots=not args.summary_plots_only,
            )
            print(f"Completed {name}: {len(frame)} paired-seed runs", flush=True)
    print(f"Saved simulation artifacts: {output.resolve()}", flush=True)
