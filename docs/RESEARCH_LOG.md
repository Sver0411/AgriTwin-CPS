# Research and validation log

## 2026-10-21 — Initial simulation platform

The project started in an empty, independent Git repository. No existing project was migrated.
Python 3.11 was selected, dependencies were locked, and local commits separated runnable stages.

- Phase 1: bounded temperature/humidity/soil-water dynamics, seeded weather, virtual sensing,
  threshold feedback and constrained actuators. Six tests passed and a nominal trajectory ran.
- Phase 2: independent model-only and observation-corrected estimators, observation validity,
  age tracking, twin-assisted control and state/error plotting. Twelve tests passed, including
  the regression that changes hidden truth while all sensors are missing.
- Phase 3: isolated fault injector, local/remote message queues, delays/loss/outages, expiry and
  automatic fresh-message recovery. Twenty tests passed; sensor and remote-outage scenarios ran.
- Phase 4: seven groups, paired common-random-number comparisons, scalar/event metrics,
  censoring, artifact provenance, CSV/JSON/PNG export and CLI coverage. Thirty tests passed.
  The complete 260-run reference suite and a separate ten-run controller comparison executed.
- Phase 5: English research documentation, Chinese README, MIT license and optional Streamlit
  laboratory with actual-engine plots and export. Interface tests validate normal execution and
  rejection of invalid configuration. The release check passed all 34 tests (including two interface tests); Ruff lint and
  formatting checks also passed. Empty-event schemas and operation without Git were additionally
  verified. A nominal run, sensor-fault run, remote-outage run and complete paired comparison
  were executed with saved artifacts.

All results are generated from the documented uncalibrated proxy model. No public-data validation
or physical hardware experiment has occurred. No published-work comparison, optimality or
innovation conclusion is recorded. Future parameter changes must distinguish development cases
from inspected evaluation cases.

## 2026-10-21 — Research laboratory interface

The optional Streamlit application now separates overview, configuration/execution, state/fault
analysis and experiment comparison. Its neutral white/black/gray presentation preserves distinct
scientific traces and evidence labels. The simulation engine, controllers, estimator algorithms,
metric definitions and dependency set are unchanged.

Interactive runs use the existing artifact writer. Completed experiments persist locally with
configuration, seeds, source metadata and a completion manifest. Draft edits, failed attempts and
saved results have separate state. Browser testing exposed stale hidden sensor controls during
preset changes; explicit widget-state assignment corrected their synchronization.

Validation: 39 tests passed; Ruff lint and formatting checks passed. Nominal, missing-observation,
communication-outage and three-seed paired controller CLI runs completed. A browser-driven
missing-observation experiment produced six runs with the configured noise/dropout values, and
its JSON download matched the saved result data. Desktop (1280 px) and narrow (600 px) layouts
were inspected. Validation logs and screenshots remain local in `results/ui_upgrade_validation/`.

Fault windows are not presented as detections. Fallback conditions are derived from recorded
input validity/ages; no new drift/stuck detector is claimed. A single valid seed has undefined
sample SD. No confidence interval or empirical greenhouse validation was added.

## Version 2.0.0 — 2026-10-26

Implemented sensor-trust-aware estimation/sampling on top of the existing closed loop. Retained
all original algorithms and the earlier targeted fixes for fault-window notices, independent
threshold-cache age, completion-marker discovery and actual custom-configuration names.

Core additions are `sensors/health.py` (basic/residual/persistent evidence), `twin/ekf.py`
(factory, numerical Jacobian, Joseph updates and bounded replay), `sampling/scheduler.py`
(five policies and separate budgets), `experiments/adaptive_metrics.py`, `experiments/adaptive.py`
and `experiments/measurement.py` (paired simulations and separately labelled measurement replay).
`data_io/csv_import.py`, `replay.py` and `public_data.py` provide explicit units/time handling,
chronological offline replay and an audited source adapter. Engine, artifact/schema/CLI, plots and
Streamlit workspaces integrate the same backends. No new dependency, hardware, RL or cloud service.

Validation records under `results/v2_validation/`:

- Final `pytest -q`: **69 passed in 23.53 s**, no warnings, `pytest_release.log`.
- Fresh Python 3.11.15 environment with frozen dev/UI extras: **69 passed in 24.40 s**,
  `pytest_clean_final.log`; install/rebuild logs retained. An initial clean install reused an
  older cached local wheel; rebuilding the current package fixed that environment mismatch.
  The documented reinstall command matters after source edits.
- `ruff check .`: **All checks passed!** (`ruff_final.log`).
- `ruff format --check .`: **67 files already formatted** (`format_final.log`).
- `git diff --check` passed. Source scan found no private-key/token patterns or source files over
  1 MB. Git HEAD remains a1cb95d; local changes are uncommitted and no push was performed.

Executed acceptance commands all returned 0: nominal 4 h, sensor fault 24 h, remote outage 24 h,
a complete original five-seed/two-controller comparison (48 h/run), A–H (144 runs, three development
seeds, 24 h/run), fixture replay and public final comparison (40 runs, four methods × two delivery
conditions × five seeds). Public development procedure checks comprise 24 additional offline runs.
`delivery/acceptance_commands.json` and `protocol_frozen.json` retain commands/source/config identity.
The initial estimator comparison inherited adaptive sampling; A/B/D/E/G were corrected to fixed
common schedules and rerun. Earlier output remains available, without claiming isolated effects.

Raw user-downloaded files were read without alteration and matched their supplied ZIP members.
Timestamp audit found duplicates, backward jumps, gaps and questionable full-file dates.
Fixed quality-selected development/final segments retain 1,717/859 rows; no calendar repair or
value-based filtering. Data/source assumptions and exclusions are recorded. Public outcomes include
clear trust-EKF degradation, and simulated slow-drift detection has blind spots (see RESULTS.md).
No final-set parameter fitting was performed. No full physical-model or hardware validation claim.

Final visual review fixed overlapping method labels and a transient label-reference regression;
all checks above were rerun after the fix. Five public comparison figures were regenerated from
unchanged saved numerical tables, with separate figure/input hashes. Only presentation modules
changed after the numerical acceptance runs; the validation manifest checks numerical-source identity.
UI tests cover native controls, persisted uploaded bytes/identity, explicit units, replay/comparison
execution, failures, restoration and exports. Browser smoke review checked the white/black layout,
seven-page navigation and offline-mode label. Native file-picker interaction was not verified in
that smoke check; CSV import and stored-upload flows were exercised independently.

Reproduction and detailed algorithm/metric limits: README.md, SENSOR_TRUST_ESTIMATION.md,
ADAPTIVE_SAMPLING.md, DATA_REPLAY.md, EXPERIMENT_PROTOCOL.md and METRICS.md. Priority next work is
measured forcing/action alignment and calibration on separate records, followed by newly reserved
validation data and diagnosis/model-mismatch ablations. Suggested English commit title:
`Add trust-aware estimation, sampling, and audited data replay`.
