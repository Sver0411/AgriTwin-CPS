"""Causal sampling policies with separate sample and local application-byte budgets."""

import numpy as np

from agritwin_cps.communication.simulator import MESSAGE_BYTES
from agritwin_cps.config import SamplingConfig


class SamplingScheduler:
    def __init__(self, config: SamplingConfig):
        self.config = config
        self.last_sample = -1
        self.anchor = None
        self.samples = 0
        self.bytes_sent = 0
        self.events: list[dict] = []

    def decide(self, step, prediction, standard_deviation, trust, valid_ages, bounds, outage):
        c = self.config
        elapsed = step - self.last_sample
        change = (
            float(np.max(np.abs(np.asarray(prediction) - self.anchor) / c.change_scale))
            if self.anchor is not None
            else 0.0
        )
        available = np.isfinite(standard_deviation).all()
        uncertainty = (
            float(np.max(np.asarray(standard_deviation) / c.uncertainty_scale))
            if available
            else None
        )
        low_trust = bool(np.min(trust) < c.trust_threshold)
        risk = any(
            value <= low or value >= high
            for value, (low, high) in zip(prediction, bounds, strict=True)
        )
        changed = change >= c.change_threshold
        uncertain = uncertainty is not None and uncertainty >= c.uncertainty_threshold
        stale = bool(np.max(valid_ages) >= c.max_valid_age_steps)
        triggers = {
            "fixed": False,
            "change": changed,
            "uncertainty": uncertain,
            "trust_change": changed or low_trust,
            "event": risk or low_trust or uncertain,
        }
        trigger = triggers[c.strategy]
        interval = (
            c.fixed_interval_steps
            if c.strategy == "fixed"
            else (c.min_interval_steps if trigger else c.max_interval_steps)
        )
        due = self.last_sample < 0 or elapsed >= interval or (stale and c.strategy != "fixed")
        sample = due and (self.last_sample < 0 or elapsed >= c.min_interval_steps)
        reason = "initial" if self.last_sample < 0 else "interval" if due else "waiting"
        if c.strategy != "fixed" and due:
            reason = (
                ";".join(
                    k
                    for k, v in {
                        "change": changed,
                        "uncertainty": uncertain,
                        "low_trust": low_trust,
                        "risk": risk,
                        "stale": stale,
                        "max_interval": elapsed >= c.max_interval_steps,
                    }.items()
                    if v
                )
                or reason
            )
        if c.sample_budget is not None and self.samples >= c.sample_budget:
            sample, reason = False, "sample_budget_exhausted"
        send = sample
        if sample:
            self.samples += 1
            self.last_sample, self.anchor = step, np.array(prediction, copy=True)
            if c.suppress_send_during_outage and outage:
                send, reason = False, reason + ";outage_send_suppressed"
            elif (
                c.local_byte_budget is not None
                and self.bytes_sent + MESSAGE_BYTES > c.local_byte_budget
            ):
                send, reason = False, reason + ";byte_budget_exhausted"
            else:
                self.bytes_sent += MESSAGE_BYTES
        event = dict(
            step=step,
            sampled=bool(sample),
            generated=bool(sample),
            sent=bool(send),
            planned_interval_steps=interval,
            reason=reason,
            change_metric=change,
            uncertainty_metric=uncertainty,
            minimum_trust=float(np.min(trust)),
            risk=bool(risk),
            local_outage=bool(outage),
            samples_used=self.samples,
            local_bytes_used=self.bytes_sent,
            valid_generated=False,
            valid_received=False,
        )
        self.events.append(event)
        return event
