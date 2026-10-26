# Model assumptions, equations and units

This is an intentionally simplified proxy model, not a calibrated greenhouse energy/mass balance.
All default coefficients below are chosen demonstration assumptions. No coefficient is presented
as a measurement or borrowed from an unverified publication. The scope is controlled simulation
experiments on estimation and control, not crop management recommendations.

## State and time

`x = [T,H,M]`: temperature `T` in °C, relative humidity `H` in percent (0–100), soil-water proxy
`M` as a fraction (0–1). Default plant initial state: `[24,65,0.45]`; independent twin prior:
`[23,62,0.43]`. Numerical hard bounds: `[-10,60]` °C, `[0,100]` %RH, `[0,1]` fraction.
These hard bounds are numerical guardrails, not the narrower configured control safety ranges.

`dt_seconds = 300`, and `h = dt_seconds/3600` hours. Each step uses explicit Euler integration:

```text
T' = T + h * [(a_out + a_vent*v)*(T_out - T) + a_solar*S] + w_T
H' = H + h * [(c_out + c_vent*v)*(H_out - H)
              + c_evap*E*(1 - H/100) + c_irrig*r] + w_H
M' = M + h * [b_irrig*r - b_loss*E - b_drain*max(M-M_drain,0)] + w_M
x_next = clip([T',H',M'], lower_hard_bounds, upper_hard_bounds)
```

`v,r` are actual ventilation and irrigation actions in `[0,1]`, not merely commands.
`S` is a dimensionless daylight proxy; `E` is a dimensionless moisture-loss proxy. Relative
humidity is modeled directly, without absolute humidity, condensation or saturation thermodynamics.
Irrigation increases humidity additively; evaporation's humidity contribution decreases toward
saturation. Temperature/humidity/soil coupling is deliberately weak and is not energy conserving.
Clipping can hide physically unrealistic regimes; researchers should inspect saturation traces.

## Model parameters (plant and twin independently configurable)

| Configuration key | Default | Unit | Role / demonstration rationale |
|---|---:|---|---|
| heat_exchange_per_h | 0.18 | h⁻¹ | Slow passive thermal relaxation |
| solar_heat_c_per_h | 4.0 | °C/h per solar unit | Daylight heating |
| ventilation_heat_per_h | 1.2 | h⁻¹ per action | Faster outdoor heat exchange |
| humidity_exchange_per_h | 0.12 | h⁻¹ | Slow passive humidity exchange |
| ventilation_humidity_per_h | 0.9 | h⁻¹ per action | Ventilation exchanges humidity |
| evaporation_rh_per_h | 4.0 | %RH/h per E unit | Moisture source near unsaturated air |
| irrigation_rh_per_h | 2.0 | %RH/h per action | Simplified irrigation humidity source |
| irrigation_fraction_per_h | 0.14 | fraction/h per action | Water addition proxy |
| moisture_loss_per_h | 0.012 | fraction/h per E unit | Evapotranspiration loss proxy |
| drainage_per_h | 0.2 | h⁻¹ | Drainage above threshold |
| drainage_threshold | 0.65 | fraction | Onset of drainage proxy |

The default exchange rates give modest changes over a five-minute step. Configurations require
`0 < dt_seconds <= 300` and `h*max(exchange rates, drainage rate) <= 1` for plant and twin.
Humidity evaporation adds a small damping term. Parameter ranges and clipping limit runaway
values; no claim of stability for arbitrary physical systems follows from these checks.

Plant process perturbations are independent normal samples with standard deviations
`[0.12,0.4,0.001]*sqrt(h)` in state units. The twin does not observe these samples. Setting process
noise to zero gives deterministic plant propagation for fixed weather and actions. Process-noise
parameters use channel units per square-root hour, not per step.

## Synthetic weather

Let `t=k*h`, with simulation starting at local scenario hour 0:

```text
phase = sin(2*pi*(t-8)/24)
T_out = 21 + 7*phase + Normal(0,0.3)             [°C]
H_out = clip(65 - 15*phase + Normal(0,1),0,100)  [%RH]
S = max(0,sin(2*pi*((t mod 24)-6)/24))           [0,1]
E = 0.25 + 0.75*S                              [0.25,1]
```

Temperature mean/amplitude/noise and humidity mean/noise are configurable. The fixed diurnal
humidity amplitude is 15 percentage points and daylight timing is an assumed scenario convention.
Weather noise is per-sample; changing `dt` does not preserve its continuous-time spectrum. Weather
is generated before control, uses no API, and is assumed available without measurement error.
There is no crop transpiration model, water volume, greenhouse geometry or seasonal calibration.

## Sensors and faults

Default independent sensor noise SD: `[0.3,1.5,0.01]` in channel units. Default fixed bias is zero,
dropout probability zero and measurement delay zero steps. Dropout is independent by channel and
step. Bias faults add a value, drift adds `magnitude*(k-start)*h` (magnitude in channel units/hour),
stuck faults replace the value, and missing faults produce NaN. Fault windows are half-open.
Drift starts at zero and disappears at the window end; lingering calibration offsets need a bias
window. Faults are applied in configured order, but missing and random dropout always take
precedence. Out-of-range measurements are rejected rather than clipped into valid observations.

## Estimation

Method A propagates its own state with the twin parameters and actual actuator feedback; it never
uses sensor values for correction. Method B predicts, then for each newly accepted component uses

```text
age_i = current_step - observation_timestamp_i
alpha_i = configured_gain_i / (1 + age_i)
xhat_i <- clip(xhat_i + alpha_i*(measurement_i - xhat_i), hard_bounds_i)
```

Default gains `[0.35,0.3,0.4]` are transparent demonstration constants, not optimized gains.
The maximum acceptable observation age is 5 steps. A batch uses the newest accepted value of each
component. For these two baselines, delayed readings correct the current state approximately,
without covariance or historical replay. After observations return, ordinary correction resumes.
Version 2 adds separate health checks, EKF and bounded replay; see SENSOR_TRUST_ESTIMATION.md.
The fixed-gain baseline makes no covariance/optimality claim. Per-channel observation age and consecutive unused-step
count document uncertainty growth qualitatively, including model-only runs.

## Control and actuators

Both controllers use hysteresis: ventilation on if `T>=28` °C or `H>=85` %RH, off only when
`T<=25` °C and `H<=75` %RH; irrigation on at `M<=0.34`, off at `M>=0.48`. Intermediate values
preserve the previous command. The baseline uses cached observations up to 5 steps old; twin
control uses estimates for up to 30 steps without a valid correction. Method A's age grows from
initialization and eventually reaches the same prediction limit.

When either temperature/humidity input is unavailable or too old, ventilation becomes 0.5;
stale/missing moisture forces irrigation to zero. These constraints do not guarantee plant safety.
Actuator default delay is zero and minimum switching interval is 3 steps. Inputs must be finite
and within `[0,1]`. Optional failure windows freeze the previous action.

Safety intervals `[16,32]` °C, `[35,90]` %RH and `[0.25,0.75]` soil-water fraction are configurable
simulation assumptions only. Recovery tolerances `[1,5,0.03]` in state units and a 3-step dwell are
also scenario assumptions, not validated sensor accuracy or agricultural limits.

## Version 2 noise-increment windows

The isolated injector also supports `kind: noise`. Its magnitude is an **increment in channel
standard deviation** during the window: the base noise and increment use the same precomputed
standard-normal draw, giving `(base_SD + increment)*Z`. It is not the sum of two independent
Gaussian disturbances. This preserves time-indexed common random numbers across schedules.
Out-of-range faults can be configured using bias or stuck-at magnitudes; missing still takes
precedence. Health/estimation policies are separate from the plant model.
