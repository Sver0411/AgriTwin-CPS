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

No public-data or hardware validation, confidence interval, significance claim, crop-yield result,
physical energy saving, research novelty or superiority over published work is established.
Before using results in a paper, freeze source/configuration, preserve every seed and failure,
separate development from evaluation, and review the assumptions and formulas.

To regenerate evidence:

```bash
python scripts/run_experiment.py --name controller_comparison --output results/reproduce_comparison
python scripts/run_all_experiments.py --output results/reproduce_suite --summary-plots-only
```
