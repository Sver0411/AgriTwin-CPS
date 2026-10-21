# Experiment protocol

## Question and controlled conditions

Do estimated states improve or harm constrained greenhouse control under imperfect sensing,
application-layer communications and model mismatch? There is no predeclared performance winner.

The reference protocol uses 576 intervals of 300 s (48 h), plant initial state `[24,65,0.45]`,
independent twin prior `[23,62,0.43]`, and evaluation seeds **101, 202, 303, 404, 505**.
Each scenario runs both `threshold` and `twin_assisted` with the same equations, weather,
initial states, disturbance draws, sensor noise draws, dropout draws and link random draws.
Actuator constraints and controller hysteresis are identical. Only the controller's state source
and allowed prediction age differ. Realized plant paths may diverge because control differs.

Six independent RNG streams are spawned from `numpy.random.SeedSequence(seed)`: weather,
process disturbance, sensor noise, channel dropout, local transport and remote transport.
All arrays are generated before the loop; control decisions cannot change later random draws.
Nominal zero-noise trajectories can still vary across seeds because synthetic outdoor weather
has its configured variability. Noise is an exogenous disturbance, not a sensor fault there.

## Predeclared groups

All baselines below are paired threshold versus twin-assisted controllers. Estimation MAE,
RMSE, bias, valid-observation coverage, environmental violation durations, irrigation/ventilation
proxies, activations, stale-data durations and recovery/censoring are saved for every run.
Additional emphasis and limitations are specified per group.

| Group / research question | Independent variables | Scenarios × repetitions × controllers | Main metrics and specific limits |
|---|---|---:|---|
| 1. Nominal: does the closed loop run with clean sensors? | Sensor noise = 0, process noise = 0 | 1 × 5 × 2 | State/control traces, initial prior convergence; weather remains synthetic |
| 2. Sensor noise: how do estimation and actions change? | SD multipliers 0,1,3,6 of `[0.3,1.5,0.01]` | 4 × 5 × 2 | MAE/RMSE, violations, switching; independent Gaussian channel errors only |
| 3. Missing observations: what is the effect of random/burst loss? | Independent dropout 0,0.2,0.5; separate all-channel bursts of 6,24,72 steps | 6 × 5 × 2 | Coverage, age, fault-period errors and recovery; probabilities and bursts are separate cases, not a full factorial |
| 4. Drift: can correction inherit biased measurements? | Temperature drift 0,0.2,0.6 °C/h; separate soil bias −0.08 | 4 × 5 × 2 | Signed bias, violations, recovery; plausible drift has no automatic detector |
| 5. Outage: can local control continue and monitoring recover? | Local versus remote outage, lengths 12,48,96 steps | 6 × 5 × 2 | Continuity, stale duration, estimation recovery and remote resync; remote failure cannot affect local decisions by construction |
| 6. Model mismatch: when does prediction become harmful? | Twin solar heating and soil-loss factors 0.5,1,1.5,2 of plant values | 4 × 5 × 2 | Fault-period error and paired control metrics; two parameters varied jointly, not identifiable individual effects |
| 7. Controller comparison: is smoothing/prediction beneficial under joint noise/dropout? | SD `[1.5,7.5,0.05]`, dropout 0.2 | 1 × 5 × 2 | Paired differences of all metrics; one deliberately fixed synthetic regime |

For generated sweeps, deterministic fault/outage windows begin at `floor(N/3)`.
Drift/bias ends at `floor(2N/3)`; missing bursts and outages end at the requested duration capped
at `N-1`. The mismatch group includes an all-channel missing window of `min(72,max(1,floor(N/6)))`
steps. Outage links additionally use delay 2, jitter 0–3, packet-loss probability 0.1 and maximum
age 5 steps. Other controlled variables retain the base configuration. Saved per-run YAML is
authoritative. Short test horizons truncate windows; they are smoke tests, not the reference study.

`configs/*.yaml` are convenient single-run examples, while the experiment runner constructs the
sweeps above. With `configs/default.yaml`, the full protocol is **26 scenarios, 260 runs**.
A custom base configuration can intentionally add combined faults; it changes the protocol and
must be reported as a separate experiment, rather than silently pooled with reference results.

## Reporting and interpretation

Save every seed, including failures. `summary.csv` uses arithmetic means and sample standard
deviations (`ddof=1`), with `n_valid`, `n_total`, and `n_missing`. A singleton has undefined SD.
No confidence intervals or significance claims are generated from five seeds. `paired_differences.csv`
is twin minus threshold within each `(experiment,scenario,seed)` pair; smaller is desirable for
error, violation and effort metrics but not for coverage or continuity. These metrics describe
different objectives and should not be collapsed into an undisclosed score.

Recovery times conditional on successful recovery must be read together with censored counts and
the event table. Empty means indicate no eligible/observed events, not perfect recovery. The
failure summary lists any environmental violation, censored recovery, or failed actuator command;
it is an inspection index rather than a universal pass/fail or agricultural safety certificate.

Method A versus B can be studied by rerunning with `--estimator model_only` and
`--estimator observation_corrected` into separate directories. The reference 260-run suite uses
observation correction; it does not claim an independent estimator-method ablation.

## Development versus evaluation

`configs/tuning.yaml` uses disjoint seeds 11,22,33. It is reserved for future parameter tuning;
the initial release's gains, thresholds and scenario ranges are fixed illustrative assumptions,
not parameters selected by optimizing these evaluation results. If tuning is performed, record
the objective, search space, training seeds, scenario ranges and frozen configuration before
running a new evaluation. Previously inspected evaluation scenarios must not be relabeled as an
unseen test set. There is currently no independent empirical validation dataset or held-out
real-world test distribution.
