"""Regression checks for time semantics and distinct evidence layers."""

import json

import numpy as np
import pandas as pd
import pytest

from agritwin_cps.config import SimulationConfig
from agritwin_cps.data_io.csv_import import ImportConfig
from agritwin_cps.data_io.replay import ReplayConfig, write_replay
from agritwin_cps.experiments.metrics import compute_metrics
from agritwin_cps.simulation.engine import simulate


@pytest.mark.parametrize("method", ["model_only", "observation_corrected", "ekf", "trust_ekf"])
@pytest.mark.parametrize("delay", [0, 2])
def test_replay_assimilation_and_same_time_masks(tmp_path, method, delay):
    source = "timestamp,T\n" + "".join(
        f"2025-01-01T00:{k * 5:02d}:00Z,{20 + k if k != 3 else ''}\n" for k in range(8)
    )
    mapping = ImportConfig(dataset_id="time-test", columns={"temperature": "T"})
    cfg = SimulationConfig(
        estimator={
            "method": method,
            "replay_history_steps": 3 if method in ("ekf", "trust_ekf") else 0,
        }
    )
    replay = ReplayConfig(delay_rows=delay, dropout_probability=0.4, packet_loss_probability=0.2)
    f, metrics = write_replay(source.encode(), mapping, replay, cfg, 11, tmp_path / "a", False)
    changed = source.replace(",27\n", ",45\n")
    b, _ = write_replay(changed.encode(), mapping, replay, cfg, 11, tmp_path / "b", False)
    np.testing.assert_array_equal(f.estimated_temperature[:7], b.estimated_temperature[:7])
    assert f.state_timestamp.equals(f.evaluation_timestamp)
    schema = json.loads((tmp_path / "a/schema.json").read_text())
    assert schema["trajectory_units"]["observation_age_temperature_steps"] == "original row count"
    events = pd.read_csv(tmp_path / "a/estimator_events.csv")
    used = events[events.assimilated.fillna(False)]
    assert (used.generated_step <= used.received_step).all()
    if method == "model_only":
        assert used.empty and not f.assimilated_temperature.any()
    else:
        for _, e in used.iterrows():
            assert not f.loc[int(e.generated_step), "artificially_heldout_temperature"]
            assert int(e.generated_step) != 3  # Missing source measurement is never assimilated.
            assert e.received_step - e.generated_step == delay
    mask = f.artificially_heldout_temperature
    expected = (f.estimated_temperature - f.measured_temperature)[mask].abs().mean()
    assert metrics["masked_target_prediction_agreement_mae_temperature"] == pytest.approx(expected)
    if delay:
        assert metrics["heldout_agreement_mae_temperature"] is None
        assert metrics["heldout_agreement_valid_count_temperature"] == 0
    else:
        assert metrics["heldout_agreement_mae_temperature"] == pytest.approx(expected)


def test_packet_loss_is_not_assimilation_and_irregular_timestamps(tmp_path):
    source = (
        b"timestamp,T\n2025-01-01T00:00:00Z,20\n2025-01-01T00:02:00Z,25\n2025-01-01T00:12:00Z,30\n"
    )
    mapping = ImportConfig(dataset_id="loss", columns={"temperature": "T"})
    cfg = SimulationConfig()
    f, _ = write_replay(
        source, mapping, ReplayConfig(packet_loss_probability=1), cfg, 11, tmp_path / "lost", False
    )
    assert not f.observation_received.any() and not f.assimilated_temperature.any()
    g, _ = write_replay(
        source, mapping, ReplayConfig(delay_rows=1), cfg, 11, tmp_path / "delayed", False
    )
    assert g.observation_delay_seconds.dropna().tolist() == [120, 600]
    assert g.observed_timestamp.iloc[2] == g.state_timestamp.iloc[1]


def test_unsampled_random_draws_do_not_inject_faults():
    cfg = SimulationConfig(
        steps=30, sensor={"dropout_probability": 1}, sampling={"fixed_interval_steps": 5}
    )
    f = simulate(cfg, 11, "twin_assisted").trajectory
    assert not f.loc[~f.sampled, "sensor_fault_active"].any()
    assert f.loc[f.sampled, "sensor_fault_active"].all()
    assert f.fault_label_temperature.equals(f.sampled)
    assert f.random_dropout_temperature.equals(f.sampled)
    assert not f.sensor_fault_configured.any()


def test_links_status_conservation_and_actual_actuator_evidence():
    cfg = SimulationConfig(
        steps=14,
        communication={
            "remote": {
                "delay_steps": 2,
                "max_age_steps": 1,
                "outages": [{"start_step": 2, "end_step": 5}],
            }
        },
        actuator={"delay_steps": 2, "failures": [{"start_step": 3, "end_step": 6}]},
    )
    result = simulate(cfg, 11, "threshold")
    metrics, recovery = compute_metrics(result, cfg)
    assert metrics["mae_temperature_during_local_outage"] is None
    assert metrics["mae_temperature_during_remote_outage"] is not None
    for link in ("local", "remote"):
        statuses = [
            "delivered",
            "packet_loss",
            "expired",
            "disconnected_at_send",
            "disconnected_at_receive",
            "pending_at_horizon",
        ]
        assert (
            sum(metrics[f"{link}_{s}_message_count"] for s in statuses)
            == metrics[f"{link}_sent_message_count"]
        )
    for _, event in result.actuator_events.iterrows():
        row = result.trajectory.iloc[int(event.execution_step)]
        assert event.actual_ventilation == row.actual_ventilation
        assert event.actual_irrigation == row.actual_irrigation
    assert metrics["failed_actuator_command_count"] == 3
    assert metrics["pending_actuator_command_count"] == 2
    assert recovery.estimation_recovery_seconds.isna().all()
    assert metrics["remote_resync_censored_count"] == 1  # Every remote packet expires.


def test_ekf_records_only_components_actually_used_in_batch():
    from agritwin_cps.config import EstimatorConfig, ModelParameters
    from agritwin_cps.models.greenhouse import Action, Disturbance
    from agritwin_cps.sensors.virtual_sensor import Observation
    from agritwin_cps.twin.ekf import ExtendedKalmanEstimator

    estimator = ExtendedKalmanEstimator(EstimatorConfig(method="ekf"), ModelParameters(), 300)
    estimator.predict(Action(), Disturbance(21, 60, 0, 0))
    estimator.correct([Observation(0, (20, 60, 0.4)), Observation(1, (25, 70, 0.5))], 1)
    used = [e for e in estimator.events if e.get("assimilated")]
    assert len(used) == 3 and all(e["generated_step"] == 1 for e in used)
    superseded = [e for e in estimator.events if e["reason"] == "superseded_in_batch"]
    assert len(superseded) == 3 and not any(e["assimilated"] for e in superseded)


def test_received_fault_exposure_follows_delivery_not_window_start():
    cfg = SimulationConfig(
        steps=6,
        sensor={
            "delay_steps": 2,
            "faults": [
                {"channel": "temperature", "kind": "missing", "start_step": 1, "end_step": 2}
            ],
        },
    )
    f = simulate(cfg, 11, "twin_assisted").trajectory
    assert f.loc[1, "fault_label_temperature"]
    assert not f.loc[1, "received_fault_exposure_temperature"]
    assert f.loc[3, "received_fault_exposure_temperature"]
    assert not f.loc[3, "sensor_fault_configured"]
