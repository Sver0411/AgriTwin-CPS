# Results and evidence boundaries

The initial release has been executed locally through all seven experiment groups (26 scenarios,
five seeds, two controllers: 260 runs), plus nominal, sensor-fault and communication-outage
acceptance runs and a separate complete controller comparison. These are synthetic software
experiments. Actual validation commands and test counts are recorded in RESEARCH_LOG.md.

Generated numerical outcomes and figures are intentionally not versioned as source data.
Use the run's own resolved `config.yaml`, `metadata.json`, source hashes and per-seed CSVs to
inspect evidence. Example local output names used during development are `results/full_suite/`,
`results/controller_comparison/` and `results/acceptance_*`; a fresh checkout creates them only
when the documented commands run. Final verification artifacts may use `results/final_validation/`.

The suite permits both favorable and unfavorable paired deltas. Accuracy and control objectives
can disagree. Remote-outage continuity is a test of isolation by construction, not a wireless
performance result. A scalar summary alone is insufficient for claiming resilience: inspect
stale-data age, actual actuator behavior, environmental bounds and censored recovery events.

The initial release established no public-data/hardware validation. Version 2 adds only the
offline temperature measurement-consistency check below. There is no full-model or hardware
validation, confidence interval, significance, crop-yield, physical-energy, novelty or superiority claim.
Before using results in a paper, freeze source/configuration, preserve every seed and failure,
separate development from evaluation, and review the assumptions and formulas.

To regenerate evidence:

```bash
python scripts/run_experiment.py --name controller_comparison --output results/reproduce_comparison
python scripts/run_all_experiments.py --output results/reproduce_suite --summary-plots-only
```


## Version 2 executed evidence (2026-10-26)

Final numerical artifacts: `results/v2_validation/delivery/`. Commands, exit codes, frozen
configuration/source hashes and elapsed run times are in `acceptance_commands.json` and
`protocol_frozen.json`. The package version is 2.0.0. Runtime/source/config metadata accompanies
every run; generated data remain ignored by Git. Existing early acceptance artifacts are retained.
Numerical A–H and public final aggregate tables were equal across the corrected acceptance
reruns. This is reproducibility of one numerical environment, not cross-platform equivalence.

Executed: nominal 48-step, sensor-fault and remote-outage 288-step runs; the full five-seed/two-
controller 576-step baseline comparison; all A–H groups (144 simulations, 288 steps, seeds 11/22/33);
one fixture replay; public development (24 offline runs) and final evaluation (40 offline runs).
An initial estimator comparison inherited adaptive sampling and was rerun with identical fixed
schedules for A/B/D/E/G. The earlier records were not deleted or presented as the isolated ablation.

### Simulated sampling tradeoff

C uses trust-EKF, identical common disturbances/faults and three development seeds. Values below
are means, with sample SD for temperature MAE; individual seeds and SD for every metric remain in
`adaptive/sampling/per_seed.csv` and `summary.csv`. These numbers describe this one configuration.

| Policy | Samples | Local bytes | Total bytes | Temperature MAE (°C), mean ± SD |
|---|---:|---:|---:|---:|
| fixed (4-step) | 72.00 | 2448.00 | 12240.00 | 0.2137 ± 0.0173 |
| change | 48.33 | 1643.33 | 11435.33 | 0.2072 ± 0.0398 |
| uncertainty | 46.00 | 1564.00 | 11356.00 | 0.1688 ± 0.0183 |
| trust_change | 102.33 | 3479.33 | 13271.33 | 0.2057 ± 0.0110 |
| event | 97.00 | 3298.00 | 13090.00 | 0.1928 ± 0.0332 |

All five had zero configured environmental violation duration in this development case. That is
not universal safety. Trust/change and event policies **increased** traffic; remote telemetry
contributed 9792 bytes per run regardless of local schedule. Resource results are application
payload proxies, not physical energy savings. `resource_tradeoff.png` retains every seed/scenario.

In the fixed-sampling estimator ablation, temperature MAE was 0.3493 (fixed-gain), 0.2178 (EKF),
0.2137 (trust-EKF) and 0.1818 °C (model-only). Model-only nevertheless had mean 6500 seconds outside
at least one configured state range due to age/fallback and moisture behavior. Temperature MAE
alone cannot rank closed-loop performance. In fixed-sampling diagnosis group B, temperature drift
recall was **0** for all three diagnosis methods, with one undetected temperature window per run;
precision was undefined because no confirmed temperature alarms occurred. This is a residual
blind spot, even though designed unit-test anomalies can be detected. Read other-channel results,
severity cases, false positives and censor counts rather than assuming broad diagnostic accuracy.

### Public temperature measurement consistency

Source attribution, timezone assumption, retained 859-row test segment and exclusions are in
DATA_REPLAY.md and `results/v2_validation/public_data/audit.json`. Final seeds are
101/202/303/404/505. No model/noise/trust parameters were fitted or retuned on final outcomes.
The test is a **measurement** consistency comparison with constant assumed forcing, not full-model
validation or latent-truth estimation accuracy. Temperature only is measured; humidity/moisture
accuracy is N/A. The fixed-gain baseline is the paired reference in exported differences.

| Estimator | Unmodified delivery: posterior MAE (°C) | 20% masking + 2-row delay: posterior MAE, mean ± SD | Same case: pre-update MAE, mean ± SD | Same case: masked-component MAE, mean ± SD |
|---|---:|---:|---:|---:|
| observation_corrected | 0.4657 | 1.6068 ± 0.0254 | 1.7331 ± 0.0258 | 1.6213 ± 0.1217 |
| model_only | 5.2825 | 5.2825 ± 0.0000 | 5.2825 ± 0.0000 | 5.2660 ± 0.4107 |
| ekf | 1.3265 | 1.7271 ± 0.0189 | 1.8489 ± 0.0195 | 1.7533 ± 0.1369 |
| trust_ekf | 4.6620 | 4.7809 ± 0.0140 | 4.8197 ± 0.0146 | 4.8232 ± 0.5718 |

Unmodified-delivery SD across seeds is zero because the record and delivery are deterministic;
heldout metrics are N/A there. Seed variation describes artificial masks, not independent sites.
Posterior agreement includes measurements already assimilated. The pre-update and heldout columns
reduce that ambiguity but still compare with noisy observations. Trust-EKF **underperforms** the
fixed-gain baseline and ordinary EKF here. Plausible causes include unmodeled forcing, mismatch,
uncalibrated noise and rejection of real dynamics. Those mechanisms require separate ablations;
this experiment does not identify a unique cause or justify final-set tuning.

Remaining work is to map/align measured forcing and actions, calibrate on separate data, reserve
new unseen evaluation records, and examine diagnosis sensitivity. There is no hardware reliability,
real-world energy/crop benefit or claim that the new methods universally improve control.
