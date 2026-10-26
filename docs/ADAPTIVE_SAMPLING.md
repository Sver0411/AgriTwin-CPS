# Adaptive sampling and resource accounting / 自适应采样与资源统计

The scheduler runs **before** the current sensor sample. Inputs are the current model prediction,
available standard deviation, past delivered observation ages, past health scores, configured
safe ranges and local-link outage status. No unsampled current measurement or simulator truth
enters a decision. Model change is measured relative to the predicted state at the last sample:
`change=max_i |x_pred_i - anchor_i|/change_scale_i`. Thus `change` is a model-change policy, not
an oracle that inspects unsampled physical measurements.

Five policies share one scheduler and explicit budgets:

| Strategy | Trigger for minimum interval; otherwise maximum interval |
|---|---|
| fixed | Configured fixed interval, no adaptive trigger |
| change | Normalized predicted change exceeds its threshold |
| uncertainty | `max(std_i/uncertainty_scale_i)` exceeds its threshold |
| trust_change | Change trigger OR minimum channel trust below its threshold |
| event | Estimate outside a configured safe range OR low trust OR high uncertainty |

Initial sampling is immediate. Adaptive policies also trigger when maximum valid-data age is
reached, subject to minimum spacing. Default normalization scales `[1 °C,5 %RH,0.03 fraction]`
and trigger threshold `1` are uncalibrated assumptions. No covariance is fabricated for the two
baselines: the uncertainty trigger is unavailable there, but maximum interval and age still apply.
`fixed_interval_steps` must lie between configured minimum and maximum. Default fixed interval
is `1` (legacy behavior); `configs/adaptive.yaml` uses `4`, minimum `1`, maximum `12`.

A sample budget caps samples. A separate byte budget caps **local observation send attempts**;
measurement generation can continue after it is exhausted. Limits are per run and are not renewed.
Minimum/maximum intervals are scheduling targets **while budget is available**. Exhaustion is
logged explicitly and can force stale-data safety degradation. Optional outage-send suppression
avoids sends during a configured local outage, while still allowing samples. It assumes local
knowledge of disconnection and does not estimate real wireless link state.

Each decision records sample/generated/send flags, planned interval, reason, normalized change,
uncertainty (null when unavailable), trust, risk, local outage, cumulative sample/byte usage and
whether generation/delivery produced any valid component. Partial three-channel readings count
as one valid observation event when at least one component is finite and within hard bounds.
Per-channel acceptance coverage remains separately available. A delivery-step count can combine
multiple delivered messages; packet arrival counts come from communication events instead.

## Bytes and fair comparisons

The fixed little-endian application message is `<BQ3dB`: version `uint8`, generated step `uint64`,
three `float64` values and validity mask `uint8`: **34 bytes**. `struct.calcsize` defines this
serialization-size convention; the simulator does not implement a physical network protocol.
All send attempts count this payload, including failed attempts during disconnection. Pending,
delivered and dropped messages are separately counted. There are no retransmissions, headers,
radio wakeups, packet fragmentation, sensor circuit costs or measured energy.

The byte budget covers the local observation path. Remote estimate telemetry still runs every
simulation step, has independent fault/random streams, and is reported separately and in total
bytes. Consequently sampling reduction is not equal to total traffic reduction. This release
studies local sampling policies, not joint local/remote network optimization.

Weather, process noise, sensor standardized noise/dropout, and link draws are precomputed for
every simulation time index. Skipped sampling does not consume or shift later draws. Changing
control changes the plant trajectory; common disturbances do not imply identical hidden states.
Comparisons keep controller age rules and covariance limits common unless explicitly varied.
