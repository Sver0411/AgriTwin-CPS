# Reproducibility and artifact contract

From a fresh checkout, install with Python 3.11 and
`uv sync --frozen --extra dev --extra ui --no-editable`, then activate `.venv`.
Omit `--extra ui` if the interface is unnecessary. Installation needs package downloads; all
subsequent simulations run offline. `uv.lock` records resolved versions. Alternative pip installs
follow dependency constraints but need not resolve identically to the lockfile.

For source edits, reinstall the wheel using the README command before executing tests/experiments.
The reference installation uses a regular wheel because hidden editable `.pth` files on some
macOS environments can prevent source-path discovery. This issue is independent of the model.

## Randomness and fair comparisons

A seed creates six independent streams through `SeedSequence.spawn(6)`. Every exogenous draw is
precomputed at fixed shape before control. Repeated runs with the same configuration, seed,
controller and numerical environment produce equal trajectories. Byte-identical metadata is not
expected: timestamps, Git status and output directories can differ. Floating point and library
versions can change results across platforms; no cross-platform bitwise guarantee is made.

Reference evaluation seeds are 101,202,303,404,505. Reserved development seeds are 11,22,33 in
`configs/tuning.yaml`. No seed is selected after observing a favorable outcome. No external data
are downloaded or claimed. Independent truth/twin priors are explicit in resolved configuration.

## Per-run files

| File | Content |
|---|---|
| config.yaml | Fully resolved validated configuration; seeds reduced to actual single seed |
| metadata.json | Schema version, UTC creation time, package/Python versions, source SHA256 hashes, Git state, controller and seed, config hash |
| schema.json | Units, missing-value and time conventions, event-table descriptions |
| trajectory.csv | Left endpoints; true/sensor/observed/estimated/remote states; timestamps, ages, missing counts, disturbances, commands, actual actions, faults |
| terminal_state.json | Plant state after the final interval (not counted again in metrics) |
| observation_events.csv | Per-component timestamp/range/finite validation outcomes |
| communication_events.csv | Per-message local/remote lifecycle with generation/send/schedule/receive/resolution times and status |
| actuator_events.csv | Due commands, execution timestamps and applied/limited/failed status |
| recovery_events.csv | Deterministic window bounds, recovery/resync delays and censoring |
| metrics.json | Computed scalar simulation metrics; null when not applicable |
| trajectory.png | Computed states, commands/actions, scaled errors and fault timeline unless disabled |

`source_sha256` hashes actual executing package Python files, including regular wheel installs.
Git metadata describes the launch working directory; launch from this project root to associate
it with the repository. Git state can be dirty during development; source hashes and saved
configuration remain the precise execution provenance. No user identity or hostname is recorded.
Time fields in event tables are integer simulation steps; convert via `dt_seconds` in config.

`sensor_*` is the raw reading generated this step, before link delivery. `observed_*` is the latest
newly accepted component delivered this step, NaN otherwise. `observed_timestamp_*_step` holds the
cache's most recent valid generation time, or −1 if never valid. Cached values can persist across
missing samples; the baseline uses this cache, with its explicit age constraint. `estimated_*`
is after correction at this step. `remote_*` is the last accepted remote telemetry state and can
be stale; `sync_error_*` compares it with the current local estimate. Values and ages must be read
together. `local_control_executed` means a decision was scheduled, not that an action succeeded.

Observation validation follows the active input path: threshold runs use
`controller.max_sensor_age_steps`, while twin-assisted runs use
`estimator.max_observation_age_steps`. The estimator always validates its own observations
independently, including when running for evaluation beside the threshold controller.
`observation_events.csv` and accepted-observation coverage describe the active path, not the
shadow estimator's acceptance. The local transport's `max_age_steps` is an additional delivery
limit: messages dropped by transport cannot be recovered by either consumer.

Each trajectory row uses channel units specified in schema.json: temperature °C, humidity %RH,
moisture fraction; actions in `[0,1]`, solar/evapotranspiration dimensionless proxies.
CSV NaN is an empty cell; JSON missing metrics are null. They must never be converted into a
zero observation or zero recovery time. Event tables keep headers even when empty.

## Experiment files

Each experiment contains `<scenario>/seed_<seed>/<controller>/` run directories plus:
`per_seed.csv`, `summary.csv`, `paired_differences.csv`, `paired_summary.csv`, `failure_cases.csv`,
`metadata.json` and `comparison.png` (unless disabled). Summary has mean, sample SD, valid/total/
missing counts. Paired differences use twin minus threshold for matching seeds. `--summary-plots-only`
skips per-run figures while retaining all raw data, events, metrics and comparison figures.

Output directories must be empty. The runner refuses accidental overwrite. A failed run can leave
partial artifacts; use a new output directory after fixing it and preserve diagnostics. There is
no automatic resume or distributed execution. The optional interface now uses the same per-run writer, preserving the same configurations,
events, metrics, schemas and source/environment provenance. Successful interactive experiments
are stored under `results/ui_runs/<id>/`, with `experiment.json` written only after completion.
This manifest supports refresh recovery; draft settings remain separate and do not alter saved
results. CSV/JSON and a prepared ZIP export these artifacts. Existing CLI groups remain readable
in the comparison workspace. Set `AGRITWIN_RESULTS_DIR` to use an alternate local results root.
The interface adds no new statistical definitions or dependencies.

Preset and YAML fault windows are half-open **step-index** intervals. Changing `dt_seconds`
keeps their indices and therefore changes their physical timing. Custom sensor/link windows
entered in GUI hours instead retain their requested hours, rounded up to the simulation grid.
UI preflight and the shared run writer warn about windows entirely beyond the horizon or
extending past it. These are notices, not rejection or automatic rescheduling; partial runs can
still be useful for censored-recovery studies. The low-level `simulate()` function stays silent.

The UI labels the selected base preset separately from the resolved configuration. Modified
settings that retain the base name receive a `_custom` suffix in saved configurations and
comparison tables; explicit YAML names distinct from the base name are preserved. This changes no
layout. UI experiments appear in comparison discovery only with `experiment.json`, in addition
to their aggregate CSVs. CLI discovery continues to use `per_seed.csv` plus `summary.csv`.

Generated results, virtual environments, caches and build artifacts are ignored by Git.
Only `results/.gitkeep` is versioned there. The MIT license covers this project's source; installed
dependencies retain their own licenses. No credentials are required or embedded.

## Version 2 artifacts and workflows

No new runtime dependency is required. Version 2.0.0 uses the updated uv lock; the regular-wheel
installation and reinstall procedure above still applies. `configs/adaptive.yaml` is explicitly a
development configuration (11/22/33). Default legacy configuration still selects fixed-gain and
fixed every-step sampling. Histories are bounded; result/event tables intentionally retain the run.

New per-run artifacts: `health_events.csv`, `sampling_events.csv`, `estimator_events.csv`, and
`run.json` written only after successful simulation/artifact/plot completion. Trajectories add
trust, SD, sample flags, per-channel control validity and evaluator-only fault labels. Schema 2.0
records units. Existing single-run and aggregate CSV locations remain unchanged.

A–H use `agritwin adaptive --name GROUP --config configs/adaptive.yaml --output NEW_DIR`.
Aggregate identifiers preserve the original `controller` column for **variant labels**; actual
controller/estimator/sampling choices appear in each saved config/metadata. Paired deltas are each
variant minus the first declared variant per scenario. New UI adaptive directories require
`adaptive_experiment.json` for discovery; ordinary legacy CLI detection remains unchanged.

Generic `agritwin replay` and `replay-experiment` use `--csv` and `--data-config`. Per-run replay
metadata keeps package source hashes under `source_sha256` and dataset bytes under `dataset_sha256`,
plus config hashes, seed, partition, assumed inputs and source identity. It saves original normalized
measurements, timestamped trajectories, health/filter events, schema, metrics and `replay.json`
only after completion. Measurement comparisons intentionally use `measurement_per_seed.csv`,
`measurement_summary.csv`, paired tables and `replay_comparison.json`; they do not enter the
simulation-truth comparison selector or borrow its metric semantics.

Streamlit adds native estimator/health/sampling/history/budget controls. Its three new workspaces
read these artifacts. Replay and adaptive failures preserve previous completed results and save
local diagnostics under `results/failures/`. Historical successful results can be restored from
completion manifests. Config drafts and output directories stay distinct. See DATA_REPLAY.md for
public-source preparation and the handwritten format fixture disclaimer. Do not commit raw local
user data, generated results or caches.
