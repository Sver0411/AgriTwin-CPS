# Limitations and planned work

## Implemented and tested in simulation

The three-state bounded proxy model, independent estimators, common-random-number comparisons,
virtual sensing, local/remote links, constrained actuators and multi-seed artifact runner are
implemented. Unit/integration tests and Streamlit AppTest exercise the documented functionality.
Tests establish software behavior under specific conditions, not empirical model accuracy.

## Not validated on public data or hardware

No public greenhouse dataset has been used for calibration or independent validation. No physical
sensors, actuators, gateways, crops or greenhouse experiments have been connected. All default
coefficients, safety bands, noise models, recovery thresholds and fault schedules are assumed.
Synthetic `true_state` is not a hardware measurement. This release is not validated for farm use.

## Modeling limitations

- Direct relative-humidity dynamics omit absolute humidity, condensation and heat/moisture coupling.
- No crop physiology, spatial heterogeneity, greenhouse geometry, water volume, actuator mechanics,
  psychrometrics, production economics or crop yield model is included.
- Hard clipping prevents unbounded states but can conceal unphysical regimes and distort errors.
- The twin assumes perfect weather knowledge and noiseless applied-actuator feedback.
- The plant and twin share the same functional family; parameter mismatch does not represent
  all structural mismatch. Two mismatch coefficients vary jointly in the reference sweep.
- Weather and sensor distributions are simple and independent; real errors can be correlated,
  seasonal, heavy-tailed or state dependent. Five evaluation seeds give limited distributional evidence.

## Estimation and control limitations

The observation-corrected estimator is a fixed-gain heuristic, not a Kalman filter or an optimal
nonlinear estimator. It records observation age/missing duration but no covariance or calibrated
uncertainty. It discounts delayed readings at the current time; historical replay is planned.
Plausible drift and stuck-at faults cannot reliably be detected with current range checks.
Model-only operation reaches a configured age limit and enters fallback rather than predicting
indefinitely. Fallback itself can violate safe ranges during adverse weather. Hysteretic control
has no crop objective, formal invariance proof, hard-state constraint optimizer or optimality claim.
The two controllers also differ in allowed data age, so apparent benefit cannot be attributed
solely to smoothing; an equal-age ablation is a useful next experiment.

## Communications and reporting limitations

Links model application messages only: no wireless propagation, protocol stacks, retransmission,
clock skew, bandwidth congestion, broker availability, authentication or energy accounting.
Remote independence is an architectural property; it cannot validate a real embedded controller.
In-flight packets due during an outage are dropped and no historical backlog is replayed.
Fault-period metrics use active-window time rather than tracking every delayed causal effect.
Recovery is threshold/dwell based; overlapping fault categories complicate attribution. Means
conditional on recovery must be read with censor counts. Settling time is not applicable to
these diurnal experiments. There is no agricultural yield, actual water volume or energy metric.

## Prioritized next work (planned)

1. Freeze this baseline, increase independent evaluation seeds, and perform equal-age and
   model-only/observation-corrected ablations with paired reporting and explicit censor handling.
2. Study prediction horizon versus mismatch using disjoint development/evaluation scenarios.
3. Implement timestamp-aligned delayed-state replay and compare it with the age-discount heuristic.
4. Select and verify a public dataset, document units/licensing, and evaluate calibration on
   genuinely held-out records before making empirical model claims.
5. Only after validation, consider absolute-humidity physics, parameter identification and optional
   hardware adapters. Reinforcement learning is outside the current scope.
