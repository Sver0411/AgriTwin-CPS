# Sensor trust and timestamp-aligned estimation / 传感器可信度与状态估计

## Implemented interface and information boundary

`create_estimator(config, parameters, dt_seconds)` selects the two original baselines, `ekf`, or
`trust_ekf`. All expose `state`, `correct(packets, step, weights)`, `predict(actual, disturbance)`,
`ages(step)` and `missing_steps`; EKFs additionally expose covariance and replay events.
The engine passes timestamped packets, known synthetic weather and **actual** actuator feedback.
No estimator, health monitor or sampler receives plant state, process-noise draws or evaluator
fault labels. A truth-perturbation test with all observations absent checks this boundary.

## Heuristic diagnosis / 启发式诊断

`SensorHealth` maintains independent state for each channel. The configured `health.method` is:

- `basic`: finite values, hard model bounds, changes per hour, missingness and timestamp age.
- `residual`: basic checks plus `|z - prediction| / residual_scale > residual_threshold`.
- `persistent`: residual checks plus EWMA of signed normalized residuals and long constant runs.

EWMA is `m[k] = (1-alpha)m[k-1] + alpha*r[k]/scale`; a large persistent signed discrepancy
provides drift-like evidence. It does **not** distinguish sensor drift from model mismatch.
A constant run accumulates generation-step gaps while adjacent values differ by at most the
channel tolerance. Sparse samples do not prove the signal remained constant between them.
Rate uses measurement generation times (actual seconds in external replay).

Default scales `[1 °C, 5 %RH, 0.03 fraction]`, residual limit `3`, EWMA alpha `0.2`, persistence
`3 abnormal observations`, rate limits `[30 °C/h,100 %RH/h,0.5 fraction/h]`, constant tolerances
`[0.001 °C,0.005 %RH,0.00001 fraction]`, constant duration `8 steps`, missing age `6 steps` and
delay warning `2 steps` are illustrative engineering settings, **not calibrated sensor specs**.
A first observation after a long gap cannot establish residual persistence.

The heuristic score is `1` within checks, `0.3` suspected, `0.05` repeatedly abnormal and `0` for
missing/nonfinite/out-of-range data. Delayed observations beyond the warning age divide this
score by `1+age`. No recent valid reading gives zero effective trust after the missing-age limit.
States are `normal`, `suspected`, `confirmed_anomaly`, `unknown`. “Confirmed” means the check
confirmed anomalous observation evidence, **not a verified sensor-fault cause or probability**.
The monitor records values, prediction, residual, score, generation timestamp, current age,
last valid timestamp, reasons and abnormal duration in `health_events.csv`.

The two baselines and ordinary EKF log health without applying its weights. `trust_ekf` inflates
measurement variance by `1/trust²`, and ignores updates below `min_update_trust=0.1`. Missing
and invalid components never update the estimate. New valid observations can restore updates;
persistent EWMA evidence can delay restoration. Old reordered packets receive an instantaneous
residual/age score without rewinding current health memory. Stored replay weights are fixed at
arrival; health diagnosis itself is not retrospectively recomputed.

## EKF mathematics / 扩展卡尔曼滤波

The state is `[T,H,M]` in °C, %RH and soil-water fraction. The dynamics are exactly the documented
bounded greenhouse transition `f`; sensing is identity on available components.

```
x_prior = f(x_posterior, actual_action, known_disturbance)
P_prior = F P_posterior Fᵀ + Q
innovation_i = z_i - x_prior_i
K_i = P[:,i] / (P[i,i] + R_i)
x = clip(x + K_i * innovation_i, lower, upper)
A_i = I - K_i e_iᵀ
P = A_i P A_iᵀ + R_i K_i K_iᵀ
```

Sequential scalar updates use Joseph covariance form. The central-difference Jacobian uses
perturbations `[1e-4 °C,1e-4 %RH,1e-6 fraction]` and is tested against analytical interior slopes.
At clipping/drainage kinks it uses symmetric slopes; Gaussian/truncation assumptions are only
approximations. The model's current weak coupling and diagonal prior/noise keep covariance diagonal;
trajectory `std_*` stores `sqrt(P_ii)` (its square recovers diagonal variance).

`initial_std=[2,8,0.08]` gives `P0=diag(std²)`. `process_std_per_sqrt_h=[0.12,0.4,0.001]` gives
`Q=diag(std²)*dt/3600`. `measurement_std=[0.3,1.5,0.01]` gives `R=diag(std²)`. Covariance entries
have pairwise state-unit products, diagonal entries squared channel units. These are independent
estimator assumptions, not automatically inferred from the plant's configured disturbances.

## Delays and bounded replay / 延迟回放

`replay_history_steps=0` disables replay: delayed valid readings approximately update the current
state with measurement variance multiplied by `(1+age)²`. With a positive history window, the EKF
stores per-time priors/covariance, accepted observations with effective R, and actual action and
forcing for each interval. It updates at the packet's generation time, then reapplies all **already
received** stored observations in timestamp order while propagating to now. It never rewrites saved
past trajectory rows: outputs remain causal “what was known then” records.

History retains at most `history+1` priors and `history` interval inputs; old observations are
pruned. Too-old packets follow `too_old_policy=ignore` (default), or explicitly approximate a
current-state update with age-inflated R (`current`). Reasons appear in `estimator_events.csv`.
Future and estimator-expired readings are ignored. Transport expiry may discard them earlier:
raising the history size alone does not override link/estimator maximum observation ages.
Duplicates cannot be assimilated twice. A batch without replay uses the newest valid component;
replay can incorporate a previously unseen older component despite a newer one already arriving.

No-data steps propagate covariance with Q. The twin-assisted controller marks a channel invalid
when its standard deviation exceeds `max_std=[5 °C,20 %RH,0.2 fraction]` or its correction age exceeds
the controller prediction-age limit. Existing hysteresis/fallback then applies: stale thermal data
uses fallback ventilation, stale moisture stops irrigation. Threshold control retains its own
sensor-age rule and bypasses covariance. `control_valid_*` and `uncertainty_fallback` record this.
These constraints are simulation assumptions, not safety certification or calibrated coverage.
