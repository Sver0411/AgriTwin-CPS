# Limitations and planned work / 局限性与后续工作

## Evidence status

The bounded plant, independent estimators, virtual sensing, actuator/local-control loop, health
checks, EKF/replay, sampling budgets, paired runner and interface are implemented and tested.
Tests establish numerical/software behavior under declared conditions, not field accuracy.

The South African public dataset is used only for offline temperature measurement-consistency
comparisons on quality-selected segments. There is **no calibrated full greenhouse model or
closed-loop validation on public data**, nor annotated field fault-detection validation. No physical
hardware, crop or greenhouse is connected. Synthetic truth remains distinct from measurement.
Illustrative model, noise, trust, control and safety parameters are not agricultural recommendations.

## Modeling

Direct RH dynamics omit psychrometrics, condensation and strong thermal/water coupling. The proxy
omits crop physiology, geometry, spatial differences, water volumes, actuator mechanics, production
or economics. Clipping bounds can conceal unphysical regimes and distort Gaussian assumptions.
Simulation assumes perfectly known synthetic weather and applied actions. Shared plant/twin model
families and jointly varied mismatch coefficients cover only a small structural mismatch space.
Simple seeded noise cannot represent all seasonal, correlated or heavy-tailed sensor errors.

## Trust, estimation and control

Heuristic scores are not fault probabilities. Residuals confound model error, real environmental
change and sensor malfunction. Slow drift can be assimilated before a residual threshold triggers;
constant values can also be real or quantized measurements. Simulation diagnosis already contains
misses and false alarms. Unit tests of designed faults are not a field sensitivity/specificity study.

EKF Q/R/P are assumed, covariance is uncalibrated, and hard clipping/Jacobian kinks violate exact
Gaussian assumptions. Health history is causal but not re-diagnosed during replay; stored weights
remain fixed. Finite history and transport/estimator expiry discard some delayed data. Old saved
trajectory rows remain the estimates available at that time; no retrospective smoothing claim.

Default trust-EKF degrades markedly on the public temperature segment under assumed forcing.
This is evidence of a failure condition, not justification for silently tuning the final test.
The fixed-gain and model-only baselines have no covariance. Model-only age limits cause fallback.
Threshold/twin controllers differ in age policy; EKF SD limits add an explicit method difference.
No controller has formal invariance, optimality or agricultural safety guarantees.

## Sampling and transport

The change policy observes predicted change, not unsampled physical measurements. All-channel
low trust may increase sampling when reliability is poor; it need not save traffic. Policies are
heuristics, not optimized scheduling solutions. Budget exhaustion overrides interval targets.
Local observation budgets exclude remote per-step telemetry; total bytes remain separately visible.
Links omit radio propagation, network protocols, retransmission, congestion, clock skew and energy.
Outage knowledge is configured in simulation. Remote independence checks architecture, not hardware.
Transport drops cannot be undone by estimator history replay.

## Public data and evaluation

The original downloads contain duplicate timestamps, backward jumps, long gaps and questionable
full-file calendar dates. Selections are disclosed, so inference covers the retained subset only.
Source timezone normalization is an assumption. No automatic date repair is made. The replay uses
constant assumed forcing/actions, even where additional source columns exist; it does not validate
the model using mapped measured weather or fan/wet-wall physics. Humidity/moisture are unmeasured
in the selected training/test target files, and their accuracy metrics remain null.

Posterior measurement agreement includes assimilated measurements. Pre-update and masked agreement
remain agreement against noisy measurements, not latent state truth. Repeated masking seeds on
one greenhouse are not independent greenhouse replications. No field fault labels or real hardware
energy/yield evidence exists. No confidence interval, significance, novelty or superiority claim.

Recovery metrics are tolerance/dwell dependent, overlapping faults complicate causal attribution,
and conditional recovery means require censor counts. Settling time is N/A for diurnal runs.
A–H use three development seeds; H repeats C's design and adds no independent evidence. Broader
multi-season/multi-site evaluation and independent model-family mismatch remain future research.

## Prioritized next work

1. Model/forcing calibration on separate calibration records; map measured weather/actions with
   verified timestamp alignment and units, then reserve a new untouched evaluation segment.
2. Distinguish model mismatch from sensor anomalies, study residual blind spots and recovery,
   and validate diagnosis on independently annotated observations.
3. Assess Q/R/health sensitivity on disjoint development scenarios and freeze before evaluation;
   report calibration, equal-age control ablations and sampling/accuracy Pareto tradeoffs.
4. Joint local/remote scheduling and explicit retry/clock models if that becomes the research scope.
5. Stronger physical humidity balance and optional hardware adapters after empirical validation.
   Reinforcement learning and large-language-model integration are outside this release.
