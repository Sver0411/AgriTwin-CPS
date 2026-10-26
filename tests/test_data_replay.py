import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agritwin_cps.config import SimulationConfig
from agritwin_cps.data_io.csv_import import ImportConfig, import_csv, load_data_config
from agritwin_cps.data_io.replay import ReplayConfig, select_partition, write_replay
from agritwin_cps.experiments.adaptive import (
    ADAPTIVE_EXPERIMENTS,
    run_adaptive_experiment,
    variants,
)

ROOT = Path(__file__).resolve().parents[1]


def test_csv_sort_units_missing_and_timestamp_validation():
    mapping = ImportConfig(
        dataset_id="test",
        columns={"temperature": "F", "humidity": "H"},
        temperature_unit="F",
        humidity_unit="fraction",
        missing_policy="preserve",
    )
    source = b"timestamp,F,H\n2025-01-01T00:10:00Z,77,0.5\n2025-01-01T00:00:00Z,68,\n"
    f, stats = import_csv(source, mapping)
    assert f.temperature.tolist() == [20, 25]
    assert np.isnan(f.humidity.iloc[0]) and f.humidity.iloc[1] == 50
    assert f.moisture.isna().all() and stats["interval_median_seconds"] == 600
    assert stats["source_sha256"] and stats["missing_count"]["moisture"] == 2
    with pytest.raises(ValueError, match="Missing measurements"):
        import_csv(source, mapping.model_copy(update={"missing_policy": "error"}))
    with pytest.raises(ValueError, match="unique"):
        import_csv(source.replace(b"00:10:00", b"00:00:00"), mapping)
    with pytest.raises(ValueError, match="Missing mapped"):
        import_csv(source, mapping.model_copy(update={"timestamp_column": "not_here"}))


def test_replay_time_range_holdout_reproducibility_and_no_truth(tmp_path):
    mapping, replay = load_data_config(ROOT / "configs/replay_example.yaml")
    cfg = SimulationConfig(estimator={"method": "ekf", "replay_history_steps": 4})
    source = ROOT / "examples/format_fixture.csv"
    a, metrics = write_replay(source, mapping, replay, cfg, 11, tmp_path / "a", plots=True)
    b, _ = write_replay(source, mapping, replay, cfg, 11, tmp_path / "b", plots=False)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 8 and not any(c.startswith("true_") for c in a)
    assert a.observed_timestamp.iloc[2] == a.timestamp.iloc[0]
    assert a.observation_delay_seconds.dropna().eq(600).all()
    error = a.estimated_temperature - a.measured_temperature
    assert metrics["measurement_agreement_mae_temperature"] == pytest.approx(abs(error).mean())
    metadata = json.loads((tmp_path / "a/metadata.json").read_text())
    assert isinstance(metadata["source_sha256"], dict) and len(metadata["dataset_sha256"]) == 64
    assert not metadata["closed_loop_validation"] and metadata["data_origin"] == "synthetic_fixture"
    assert (tmp_path / "a/replay.json").exists() and (tmp_path / "a/replay.png").exists()
    frame, _ = import_csv(source, mapping)
    selected = select_partition(
        frame,
        ReplayConfig(partition="final_evaluation", development_end_time="2025-01-01T00:20:00Z"),
    )
    assert len(selected) == 4
    with pytest.raises(ValueError, match="boundary"):
        ReplayConfig(partition="final_evaluation")
    with pytest.raises(ValueError, match="gap"):
        select_partition(frame, ReplayConfig(max_gap_seconds=30))


def test_irregular_replay_uses_elapsed_time_and_no_future_rows(tmp_path):
    source = (
        b"timestamp,temperature\n2025-01-01T00:00:00Z,20\n"
        b"2025-01-01T00:02:00Z,21\n2025-01-01T00:12:00Z,22\n"
    )
    mapping = ImportConfig(dataset_id="irregular", columns={"temperature": "temperature"})
    cfg = SimulationConfig(estimator={"method": "ekf"})
    a, _ = write_replay(source, mapping, ReplayConfig(), cfg, 1, tmp_path / "original", plots=False)
    b, _ = write_replay(
        source.replace(b",22", b",40"),
        mapping,
        ReplayConfig(),
        cfg,
        1,
        tmp_path / "changed",
        plots=False,
    )
    np.testing.assert_array_equal(a.estimated_temperature[:2], b.estimated_temperature[:2])
    assert a.timestamp.iloc[2].endswith("00:12:00+00:00")
    assert a.std_temperature.iloc[1] != a.std_temperature.iloc[2]


def test_all_adaptive_groups_and_real_paired_runner(tmp_path):
    cfg = SimulationConfig(
        steps=8, seeds=[11, 22], estimator={"replay_history_steps": 3, "method": "ekf"}
    )
    for group in ADAPTIVE_EXPERIMENTS:
        # Estimator baselines disable the independent replay switch when not supported.
        entries = list(variants(group, cfg))
        assert len(entries) >= 3
        if group not in ("sampling", "budget", "resources"):
            assert all(c.sampling.strategy == "fixed" for _, _, c in entries)
    frame = run_adaptive_experiment("sampling", cfg, tmp_path / "sampling", plots=False)
    assert len(frame) == 10
    paired = pd.read_csv(tmp_path / "sampling/paired_differences.csv")
    change = frame[frame.controller == "change"].set_index("seed")
    fixed = frame[frame.controller == "fixed"].set_index("seed")
    np.testing.assert_allclose(
        paired[paired.controller == "change_minus_fixed"].mae_temperature,
        change.mae_temperature - fixed.mae_temperature,
    )
    assert (tmp_path / "sampling/adaptive_experiment.json").exists()


def test_public_adapter_audits_and_preserves_sources(tmp_path):
    from agritwin_cps.data_io.public_data import TARGET, prepare_south_africa

    source = tmp_path / "download"
    source.mkdir()
    for filename, date in [
        ("Training Set.csv", "2022/11/25"),
        ("Test Set.csv", "2022/12/28"),
        ("Full Data Set.csv", "1931/12/22"),
    ]:
        pd.DataFrame(
            {"Date": [date] * 2, "Time": ["00:00:00", "00:05:00"], TARGET: [20, 21]}
        ).to_csv(source / filename, index=False)
    original = {p.name: p.read_bytes() for p in source.iterdir()}
    audit = prepare_south_africa(source, tmp_path / "prepared")
    assert audit["segments"]["final_evaluation"]["selected_rows"] == 2
    prepared = pd.read_csv(tmp_path / "prepared/final_evaluation.csv")
    assert prepared.temperature.tolist() == [20, 21]
    assert prepared.timestamp.iloc[0].startswith("2022-12-27 22:00:00")
    assert all(p.read_bytes() == original[p.name] for p in source.iterdir())


def test_measurement_comparison_uses_paired_masks_and_cli(tmp_path):
    import subprocess
    import sys

    from agritwin_cps.experiments.measurement import run_measurement_experiment

    mapping, replay = load_data_config(ROOT / "configs/replay_example.yaml")
    cfg = SimulationConfig(seeds=[11, 22], estimator={"method": "ekf", "replay_history_steps": 3})
    source = ROOT / "examples/format_fixture.csv"
    frame = run_measurement_experiment(
        source, mapping, replay, cfg, tmp_path / "compare", plots=True
    )
    assert len(frame) == 16
    for method in ("observation_corrected", "ekf", "trust_ekf"):
        f = pd.read_csv(tmp_path / "compare/as_configured/seed_11" / method / "trajectory.csv")
        reference = pd.read_csv(
            tmp_path / "compare/as_configured/seed_11/model_only/trajectory.csv"
        )
        assert (
            f.artificially_heldout_temperature.tolist()
            == reference.artificially_heldout_temperature.tolist()
        )
    assert (tmp_path / "compare/replay_comparison.json").exists()
    assert (frame.heldout_agreement_valid_count_temperature >= 0).all()
    for mode in ("replay", "replay-experiment"):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "agritwin_cps",
                mode,
                "--csv",
                str(source),
                "--data-config",
                str(ROOT / "configs/replay_example.yaml"),
                "--config",
                str(ROOT / "configs/adaptive.yaml"),
                "--seeds",
                "11",
                "--no-plots",
                "--output",
                str(tmp_path / mode),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
