# External data and offline replay / 外部数据与离线回放

## Generic CSV interface

`ImportConfig` explicitly maps a timestamp and any subset of temperature, humidity and moisture
columns. Datetime timestamps accept a format/timezone; epoch seconds/milliseconds are also
supported. Data are stably sorted in UTC. Duplicate/missing timestamps, nonnumeric selected
values and infinity are rejected. Empty measurement cells remain missing. Policies are preserve,
drop rows with all channels missing, or reject missing **mapped** channels. There is no automatic
interpolation, outlier clipping or replacement with zero.

Units convert F/K to °C, fractional RH to percent RH, and percent moisture to a 0–1 fraction.
Converting a dataset's moisture unit does not establish equivalence to the model's soil proxy.
Import statistics retain SHA-256, original/processed counts, time span, missing counts, interval
statistics and deviations from a declared expected interval. Unmapped channels remain unobserved.

`ReplayConfig` selects a time range and calibration/development/final partition. Final evaluation
requires a frozen development-end boundary. Boundaries without timezones mean UTC. This enforces
separation of selected rows, not researchers' freedom from prior exposure or tuning leakage.

Replay delivers rows chronologically, preserves original timestamps, injects seeded per-component
masking and a fixed delay measured in **rows**, and uses the same estimator/health implementation
as simulation. EKF history/expiry/age settings also use rows. Actual time differences drive physical
prediction, using at most 300-second integration substeps and stored elapsed-time feedback during
historical replay. A configurable maximum gap rejects unintended long propagation.

No plant, controller or physical truth is created in replay. Outdoor temperature/humidity, solar,
evapotranspiration, ventilation and irrigation are explicit **constant assumed inputs**. This
release does not map dataset weather/actuator columns into the proxy model. It is a measurement
consistency experiment under incomplete forcing, not a calibrated greenhouse hindcast.

Metrics distinguish posterior measurement agreement, pre-update agreement and agreement on
artificially withheld components whose original measurement exists. Posterior agreement includes
assimilated measurements and is not independent prediction accuracy. Masked comparisons use
identical masks for paired methods/seeds. The same physical record across seeds is not independent
field replication. There is no empirical precision/recall claim without annotated fault truth.

## Verified public source and actual local use

[Hull, Mabitsela, Phiri and Booysen (2024), *Temperature and Humidity Dataset of an East-Facing
South African Greenhouse Tunnel*, Mendeley Data V2, DOI 10.17632/54htxm94bv.2](https://data.mendeley.com/datasets/54htxm94bv/2)
is licensed CC BY 4.0. Its release describes five-minute sensor aggregates, training/test files
covering 42 days, a 162-day full file, three sensor positions, and fan/wet-wall state. Weather in
the training/test files includes interpolated hourly data. These descriptions are publisher
statements, not results of this platform. This release uses the middle-temperature measurement;
it does not reuse the authors' supplied analytical or empirical predictions.

Direct download returned HTTP 403 in this environment. User-downloaded CSVs were subsequently
read locally and matched byte-for-byte to members in the supplied dataset ZIP. The download is
not distributed in this source repository. Source files have 8,572 training rows, 2,290 test rows
and 45,832 full rows. Inspection found timestamp anomalies, including eight repeated test-file
timestamps (some with differing values), backward jumps and implausible full-file calendar years.
No dates or values are silently repaired.

`scripts/prepare_public_data.py` applies fixed timestamp-quality selections from
`data_io/public_data.py`, preserves original row/date/time identifiers and saves all exclusions:

| Partition | Original file | Local half-open interval | Retained / original rows |
|---|---|---|---|
| Development procedure check | Training Set.csv | 2022-11-25 to 2022-12-01 | 1,717 / 8,572 |
| Final offline measurement comparison | Test Set.csv | 2022-12-28 to 2022-12-31 | 859 / 2,290 |

Timezones are absent in the source; normalization **assumes** Africa/Johannesburg (UTC+2).
Selections use timestamp quality, not estimation outcomes. They limit claims to these segments.
No model/noise/health parameter was fit to these records. Defaults are frozen before final
comparison. Calibration is not performed. The development record is distinct from final rows;
subsequent tuning must use a new, untouched evaluation segment/dataset.

Actual final comparisons use the four estimators, seeds 101/202/303/404/505, unmodified delivery
and 20% artificial component masking plus two-row delay. All are temperature measurement
consistency checks under assumed forcing, **not full-model or closed-loop validation**. Humidity
and moisture metrics are null for these files. See RESULTS.md and local artifacts for outcomes.

## Reproduce with your own downloaded source

```bash
python scripts/prepare_public_data.py --source-dir /path/to/downloaded_csvs --output results/public_data
agritwin replay-experiment --csv results/public_data/development.csv \
  --data-config configs/public_sa_development.yaml --config configs/adaptive.yaml \
  --seeds 11 22 33 --no-plots --output results/public_development
agritwin replay-experiment --csv results/public_data/final_evaluation.csv \
  --data-config configs/public_sa_final.yaml --config configs/adaptive.yaml \
  --seeds 101 202 303 404 505 --output results/public_final
```

`audit.json` records original and selected hashes/counts, timestamp diagnostics, license link and
assumptions. Raw files remain unchanged. Retain attribution and disclose preprocessing if sharing
derived data. A clean checkout has only a clearly labelled handwritten CSV format fixture:

```bash
agritwin replay --csv examples/format_fixture.csv --data-config configs/replay_example.yaml \
  --config configs/adaptive.yaml --output results/format_replay
```

An additional verified candidate is [Hemming et al. (2020), *Autonomous Greenhouse Challenge,
Second Edition (2019)*, V2, 4TU.ResearchData](https://doi.org/10.4121/uuid:88d22c60-21b3-4ea8-90db-20249a5be2a7).
The repository states CC0 and six greenhouse compartments with indoor/outdoor climate, irrigation
and actuator records over six months. This platform has not downloaded or validated those files;
file-level sampling frequency/schema and suitability remain unverified here.
