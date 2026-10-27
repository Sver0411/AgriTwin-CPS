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

| Estimator | Unmodified delivery: posterior MAE (°C) | 20% masking + 2-row delay: posterior MAE, mean ± SD | Same case: pre-update MAE, mean ± SD | Same case: masked-target prediction MAE, mean ± SD |
|---|---:|---:|---:|---:|
| observation_corrected | 0.4657 | 1.6068 ± 0.0254 | 1.7331 ± 0.0258 | 1.6213 ± 0.1217 |
| model_only | 5.2825 | 5.2825 ± 0.0000 | 5.2825 ± 0.0000 | 5.2660 ± 0.4107 |
| ekf | 1.3265 | 1.7271 ± 0.0189 | 1.8489 ± 0.0195 | 1.7533 ± 0.1369 |
| trust_ekf | 4.6620 | 4.7809 ± 0.0140 | 4.8197 ± 0.0146 | 4.8232 ± 0.5718 |

Unmodified-delivery SD across seeds is zero because the record and delivery are deterministic;
heldout metrics are N/A there. Seed variation describes artificial masks, not independent sites.
Posterior agreement includes measurements already assimilated. Pre-update agreement compares
before the current arrival batch. The positive-delay masked-target column selects an artificial
mask at the current physical row, whose measurement has not yet arrived even without masking;
it is not independent heldout validation. Both still compare with noisy observations. Trust-EKF **underperforms** the
fixed-gain baseline and ordinary EKF here. Plausible causes include unmodeled forcing, mismatch,
uncalibrated noise and rejection of real dynamics. Those mechanisms require separate ablations;
this experiment does not identify a unique cause or justify final-set tuning.

Remaining work is to map/align measured forcing and actions, calibrate on separate data, reserve
new unseen evaluation records, and examine diagnosis sensitivity. There is no hardware reliability,
real-world energy/crop benefit or claim that the new methods universally improve control.

## Credibility fixes and offline viewer (2026-10-27)

Current evidence is under `results/credibility_3d_validation/current/`; earlier `v2_validation/`
artifacts are retained. This is a regression audit, not a new untouched public-data evaluation.
The package remains 2.0.0 and artifact semantics advance to 2.1; use actual saved source hashes
rather than the package version alone to identify the implementation.

Confirmed and corrected:

- Time-indexed dropout draws on **unsampled** steps incorrectly activated sensor fault labels.
  Now configured windows, generated exposure/missingness, received exposure, health diagnosis
  and actual component assimilation have distinct records. Prior fault-conditioned statistics
  and diagnosis denominators from sparse sampling must be recomputed before reuse. The old
  sampled-count/resource/overall-error numbers are retained, not silently relabelled.
- The replay mask and error had the same physical row; no arithmetic off-by-one was found.
  However, positive-delay `heldout_agreement` concealed that all current targets were delayed.
  It now has null statistics/count zero at positive delay. Explicit
  `masked_target_prediction_agreement` preserves the original conditional numerical calculation.
  Generation/arrival/state/evaluation timestamps and per-component assimilation are recorded.
  Arrival or cache acceptance alone does not prove a measurement was used. Superseded EKF batch
  components are recorded as not assimilated; numerical estimation equations are unchanged.
- Pooled outage errors were insufficient to identify local versus remote link behavior. Both
  now have separate error, stale-data and violation metrics. Remote local-estimation recovery
  was an inappropriate interpretation and is now N/A; remote resynchronization/censoring remains.
  Six explicit terminal transport statuses separate random loss, expiry, disconnection and pending
  messages. Actuator events now retain actual output as well as requests/status.
- No public-data split/timezone/raw-value change was justified. Saved source and prepared hashes
  match the preparation audit, development/final UTC ranges are nonoverlapping, and raw files
  remain unchanged. The timezone remains an assumption, not independently verified station metadata.

Executed again: nominal 48 steps, sensor fault and remote outage 288 steps; default full
five-seed/two-controller comparison (10 runs, 576 steps each); sampling comparison (15 runs,
288 steps, seeds 11/22/33); and frozen public-temperature comparison (40 replay runs, 859 rows,
seeds 101/202/303/404/505) in `public_final_semantics21/`. A separate 24-run, three-seed regression
check in `public_final/` is retained but is not the frozen final protocol. An earlier 40-run
instrumentation audit also remains in the parent validation directory.

`regression_evidence.json` checks saved aggregate means against per-seed CSVs for all three
comparisons. The frozen public posterior/pre-update statistics equal the previous values, and
new masked-target MAE/RMSE/bias/count equal the old conditional masked calculation. The table
above therefore retains its numbers with a corrected label, now backed by regenerated CSVs
and plots. Trust-EKF still underperforms: delayed posterior MAE 4.7809 ± 0.0140 °C versus
fixed-gain 1.6068 ± 0.0254 °C. No final-set retuning was performed. Earlier A–H groups not rerun
here retain their historical source/version and are not evidence for changed conditional metrics.

The 96-step seed-11 viewer demo is an actual synthetic run saved in `current/demo_semantics21/`, exported
with config/metadata/events into `frontend/public/demo/`. It is a user-interface example, not
research evidence for superiority. WebGL rendering, sensor/actuator picking, timeline seeking,
play/pause, recovery-event jump and local multi-file public replay import are checked in-browser.
The latter displays 859 measurement frames and no simulated-truth curve. The scene is schematic,
not a spatially calibrated greenhouse. See FRONTEND_DATA.md for the exact interface contract.
