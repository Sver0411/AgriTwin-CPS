import numpy as np
import pytest

from agritwin_cps.communication.simulator import MESSAGE_BYTES
from agritwin_cps.config import SamplingConfig, SimulationConfig
from agritwin_cps.experiments.adaptive_metrics import diagnosis_statistics
from agritwin_cps.experiments.metrics import compute_metrics
from agritwin_cps.sampling.scheduler import SamplingScheduler
from agritwin_cps.simulation.engine import simulate


@pytest.mark.parametrize("strategy", ["fixed", "change", "uncertainty", "trust_change", "event"])
def test_intervals_and_separate_budgets(strategy):
    c = SamplingConfig(
        strategy=strategy,
        min_interval_steps=2,
        fixed_interval_steps=3,
        max_interval_steps=5,
        sample_budget=4,
        local_byte_budget=2 * MESSAGE_BYTES,
    )
    scheduler = SamplingScheduler(c)
    for step in range(30):
        scheduler.decide(
            step,
            [24 + step, 65, 0.4],
            np.array([2, 5, 0.03]),
            [0.2, 1, 1],
            [step] * 3,
            [(16, 32), (35, 90), (0.25, 0.75)],
            False,
        )
    events = scheduler.events
    sampled = [e["step"] for e in events if e["sampled"]]
    assert len(sampled) == 4 and sum(e["sent"] for e in events) == 2
    assert (np.diff(sampled) >= 2).all() and (np.diff(sampled) <= 5).all()
    assert scheduler.bytes_sent == 2 * MESSAGE_BYTES
    assert events[-1]["reason"] == "sample_budget_exhausted"


def test_policy_trigger_changes_decisions():
    kwargs = dict(min_interval_steps=1, fixed_interval_steps=4, max_interval_steps=6)
    bounds = [(16, 32), (35, 90), (0.25, 0.75)]
    for strategy, std, trust, prediction in [
        ("change", [0.1] * 3, [1] * 3, [26, 65, 0.4]),
        ("uncertainty", [3, 10, 0.08], [1] * 3, [24, 65, 0.4]),
        ("trust_change", [0.1] * 3, [0.1, 1, 1], [24, 65, 0.4]),
        ("event", [0.1] * 3, [1] * 3, [33, 65, 0.4]),
    ]:
        adaptive = SamplingScheduler(SamplingConfig(strategy=strategy, **kwargs))
        fixed = SamplingScheduler(SamplingConfig(**kwargs))
        for scheduler in (adaptive, fixed):
            scheduler.decide(0, [24, 65, 0.4], [0.1] * 3, [1] * 3, [0] * 3, bounds, False)
        assert adaptive.decide(1, prediction, std, trust, [0] * 3, bounds, False)["sampled"]
        assert not fixed.decide(1, prediction, std, trust, [0] * 3, bounds, False)["sampled"]


def test_sampling_sending_delivery_counts_and_common_noise():
    cfg = SimulationConfig(
        steps=36,
        estimator={"method": "ekf"},
        sampling={"fixed_interval_steps": 3, "local_byte_budget": 5 * MESSAGE_BYTES},
        communication={
            "local": {
                "packet_loss": 0.3,
                "delay_steps": 2,
                "outages": [{"start_step": 3, "end_step": 4}],
            }
        },
    )
    result = simulate(cfg, 7, "twin_assisted")
    m, _ = compute_metrics(result, cfg)
    assert m["sample_count"] == 12
    assert m["local_sent_message_count"] == 5
    assert m["local_application_bytes"] == 5 * MESSAGE_BYTES
    assert (
        m["local_lost_message_count"]
        + m["local_received_message_count"]
        + m["local_pending_message_count"]
    ) == 5
    assert m["remote_sent_message_count"] == 36  # Independent monitoring remains explicit.
    assert m["local_received_message_count"] < m["local_sent_message_count"] < m["sample_count"]
    assert m["temperature_violation_integral"] == pytest.approx(
        (
            np.maximum(16 - result.trajectory.true_temperature, 0)
            + np.maximum(result.trajectory.true_temperature - 32, 0)
        ).sum()
        * 300
        / 3600
    )
    full = cfg.model_copy(deep=True)
    full.sampling = SamplingConfig()
    baseline = simulate(full, 7, "twin_assisted").trajectory
    sampled = result.trajectory[result.trajectory.sampled]
    for channel in ("temperature", "humidity", "moisture"):
        np.testing.assert_allclose(
            sampled[f"sensor_{channel}"] - sampled[f"true_{channel}"],
            (baseline[f"sensor_{channel}"] - baseline[f"true_{channel}"]).loc[sampled.index],
            atol=1e-12,
        )
    assert diagnosis_statistics([1, 1, 0, 0], [1, 0, 1, 0])["f1"] == 0.5
    assert diagnosis_statistics([], [])["recall"] is None
