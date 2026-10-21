# Simulation metrics

Trajectory rows are left endpoints of `N` integration intervals, each lasting `dt` seconds.
All channels use their native units: °C, %RH (percentage points for differences), soil-water
fraction. The endpoint `x[N]` is stored separately. Let `e_i[k]=xhat_i[k]-x_i[k]`.

## Estimation

| Metric | Formula / selection | Unit |
|---|---|---|
| MAE | `sum(abs(e))/n` | Channel unit |
| RMSE | `sqrt(sum(e²)/n)` | Channel unit |
| Bias | `sum(e)/n` | Channel unit, signed |
| Valid-observation coverage | Number of steps with a newly accepted component divided by N | Fraction |
| Error during sensor faults | Same formulas restricted to steps with an active configured sensor window or realized random channel dropout | Channel unit |
| Error during communication outages | Same formulas restricted to union of configured local/remote outages | Channel unit |
| Maximum estimation age | Largest age of usable correction timestamp × dt; model-only age = k+1 | s |

No eligible samples produce null/empty, not zero. Coverage is acceptance per step rather than
packet delivery ratio or percentage of cached finite values. Fault-period metrics use the union
of active fault channels and generated-fault time; delayed consequences may extend beyond it.
Noise alone is not classified as a fault window. Communication-outage errors pool local and
remote windows; the trajectory flags allow separate reanalysis when both exist.

## Environmental control and proxies

For configured safe interval `[L_i,U_i]`, violation duration is
`dt*sum(1[x_i<L_i or x_i>U_i])`. Boundary equality is safe. The any-range duration uses the union
across channels, not the sum (which could double count). Temperature/humidity/soil durations are
reported separately, in seconds. No continuous-time crossing interpolation is claimed.

For actual actuator sequence `a[k]` and `a[-1]=0`:

- Activation count: `sum(1[a[k]>0 and a[k-1]==0])`.
- Switch count: `sum(1[a[k]!=a[k-1]])`, including nonzero intensity changes.
- Irrigation amount: `b_irrig * sum(r[k]) * dt/3600`, cumulative soil-water fraction **input proxy**.
  It is not a volume, net soil-water change or real water consumption.
- Ventilation effort: `sum(v[k])*dt/3600`, full-action equivalent hours **effort proxy**.
  It is not electric energy or radio power.

Settling time is null for the implemented diurnal experiments, which have no fixed equilibrium
reference or mathematically specified settling band. It is not substituted by recovery time.

## Reliability and event recovery

Local control continuity is executed local decisions divided by eligible steps, both globally and
conditioned on each link's outage. Empty outage subsets are null. The current engine always runs
the local controller; this metric tests software scheduling independence, not hardware uptime.

Local stale duration counts steps where any channel has never been valid or its cached age
exceeds `max_sensor_age_steps`, multiplied by dt. Remote stale duration similarly uses the remote
cache and remote `max_age_steps`. Age is since measurement generation, not reception; data can
become stale without an explicit outage. A finite prediction is not a fresh observation.

Failed actuator command count is the number of due commands whose execution occurs within a
configured failure window. A command carries both actuator requests, so this counts commands,
not individual motors. Rate-limited commands and commands still pending at the horizon are
separate counts. Commands and actual actions are recorded separately.

For deterministic sensor-fault, local-outage and remote-outage windows, overlapping/adjacent
windows within each category are merged. At a window's exclusive end `b`, estimation recovery
is the earliest `j>=b` with all three channel absolute errors within configured tolerances for
`recovery_dwell_steps` consecutive samples. The reported delay is `(j-b)*dt`. The start of the
qualifying dwell, not its completion, is the reported time. Search stops at the next window in
that category or the trajectory horizon; events without a complete qualifying dwell are
**right-censored**. Other fault categories can overlap; recovery is not causal attribution.

Remote resynchronization delay is time from outage end to the first received remote estimate
whose generation timestamp is at/after that end. The message must also pass transport-age and
component-validity checks. Synchronization error is the absolute difference between the received
remote cached state and the current local estimate at that first post-recovery delivery, in
channel units. This is not an estimation error against plant truth. A delayed fresh message can
therefore resynchronize with nonzero synchronization error.

`recovery_events.csv` retains event bounds, observation stop, delays, censor flags and errors.
Per-run recovery means average only uncensored eligible events; censored counts and event counts
are always reported. Random dropout alone does not define deterministic recovery windows.
Failures extending beyond the horizon are censored, not recorded as zero-second recovery.

## Aggregation

For available per-seed values `m_s`, mean is `sum(m_s)/n`, sample SD is
`sqrt(sum((m_s-mean)²)/(n-1))`. SD is undefined for fewer than two values. Missing counts are
retained. No imputation or best-seed selection occurs. Paired delta is
`m_twin(s)-m_threshold(s)` for the same seed/scenario. Read favorable directions per metric;
less irrigation is not automatically better if soil safety degrades. Recovery means can be
misleading when censoring differs, so report event tables and censor counts alongside them.

`schema.json` is a machine-readable map of trajectory and metric units. Empty CSV values and
JSON null mean unmeasured/inapplicable/censored as documented above. `failure_cases.csv` records
observed violations, censored recovery and failed commands; no crop yield metric is implemented.
