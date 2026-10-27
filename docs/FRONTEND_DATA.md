# Offline 3D artifact interface (viewer 0.1, artifact semantics 2.1)

The independent React/TypeScript/Three.js viewer reads saved Python artifacts. It does not
simulate climate, estimate state, run controllers, or write to the research engine. Streamlit
remains the configuration/execution/analysis interface. The viewer needs no backend service.

## Load contract

Select files from **one run**, not an experiment aggregate. `trajectory.csv` is required.
`config.yaml`, `metadata.json`, `schema.json` are recommended. Optional files are
`health_events.csv`, `communication_events.csv`, `actuator_events.csv`, `sampling_events.csv`,
`estimator_events.csv`, `recovery_events.csv`, and a run/replay completion marker. Unknown
files do not create data. Duplicate filenames are rejected to avoid blending different runs.
The browser reads files locally; there is no upload endpoint. The saved demo is fetched only
from the same local Vite server.

`frontend/src/data.ts` normalizes artifacts to the typed `Run`, `Frame`, `ChannelValue` and
`RunEvent` structures in `types.ts`. Missing numbers remain `null`, rendered as “暂无数据”.
Malformed CSV/numbers, duplicate/decreasing steps, invalid/nonmonotonic recorded timestamps,
contradictory measurement/truth declarations, and incompatible declared channel units fail
visibly. A failed import preserves the previous loaded run. Empty optional event files are valid.
This adapter accepts engine output, not arbitrary raw field CSVs; use the Python importer for
unit conversion, timestamp normalization and explicit source mapping first.

| Artifact | Used fields and meaning |
|---|---|
| trajectory | Strictly increasing `step`; `time_seconds` or UTC `state_timestamp`/`timestamp`; channel values, trust, generation ages, configured local/remote outage flags, commands and actual actions |
| config | `dt_seconds`, sensor fault windows, link outage windows, actuator failure/delay/switch limits; windows are half-open **step indices**, not fixed wall-clock durations |
| metadata | Data origin, dataset, random seed, package/source/config hashes and assumptions; retained in the source disclosure |
| schema | Canonical °C, %RH, soil-water fraction; conflicting explicit units are rejected rather than relabelled |
| health events | Join on `(step, channel)`; diagnosis state/reason/trust are available at that recorded step, never at an earlier generation step |
| communication events | `generated_step`, `sent_step`, `scheduled_step`, `received_step`, `resolved_step`, `status`, `link`; reveal final status at reception/resolution |
| actuator events | Join on execution step; requested `ventilation`/`irrigation` differ from recorded `actual_*`; failed/limited events do not imply zero actual output |
| sampling events | Recorded sampling decisions and reasons; no inferred samples on absent rows |
| estimator events | Per-component assimilation, target step, gain/effective variance and rejection reason; packet summary rows have no component and are excluded from component events |
| recovery events | Observed qualifying recovery or right censoring; remote recovery is telemetry resynchronization, not local estimate recovery |

## Time and source semantics

One `index` owns all displayed state. Frame position is independent of step number, so skipped
step indices do not shift event joins. Event jumps choose the first saved frame at/after the
recorded event, clamped at the horizon. Events retain their original step even when clamped.
Playback is **display speed**, one frame per 700 ms at 1×; it does not claim wall-clock timing.
Trend horizontal coordinates follow saved-frame order, including irregular measurement records.
The cursor, scene, device details and cards all use the same frame.

Simulation rows are interval left endpoints. `true_*` is simulated truth, `observed_*` is the
newly accepted component at reception, `estimated_*` is the local estimate at that step. Cached
observation age can remain meaningful when no new observation is delivered; it is not a new
measurement. Health records may retain evidence from an older packet and show its age.

Measurement replay uses `measured_*` at the current physical timestamp, `observed_*` from a
possibly delayed source row, and `estimated_*` at the current state timestamp. No `true_*`
curve/card is created. Observation plots are explicitly indexed by **arrival frame**, not falsely
aligned with current physical measurement time. Generated time is shown in sensor details.
For irregular replay records, seconds of received-data age use recorded delay or timestamp
differences; row ages are not multiplied by nominal simulation dt. Missing age is unavailable.
All trends show the full loaded offline record; future points shown for browsing are not evidence
that an estimator had them earlier. Diagnosis/details list evidence through the selected frame.

## Evidence and spatial limits

Stable categories distinguish configured windows (gray), generated injection exposure (amber),
diagnosis (red), transport (muted violet), actuator processing (brown), recovery (green), sampling
(gray-green), and estimator assimilation (blue). An injected exposure is not a detected anomaly;
heuristic trust is not a fault probability. Configured “online” does not guarantee packet delivery.
Zero-second recovery means tolerance already met, not proof of causal improvement. Censored events
say recovery was not observed; they do not become successes at the last frame.

Sensor coordinates, beds, glass and devices are schematic. Climate is globally lumped: there is
no measured/calibrated spatial field, interpolated heatmap, live physical synchronization or
hardware validation. Fan motion and irrigation indicator use actual saved actions; scene status
markers use available diagnosis/actuator records. The bundled 96-step seed-11 demo was generated
by `scripts/export_frontend_demo.py`; it is synthetic simulation, not public measurements. Its
config, source hashes and events are included. Generated scientific results otherwise stay ignored.
