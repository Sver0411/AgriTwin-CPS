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
