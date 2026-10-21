"""Delayed, rate-limited actuators with separate command and actual action records."""

from agritwin_cps.config import ActuatorConfig
from agritwin_cps.models.greenhouse import Action


class Actuator:
    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.actual = Action()
        self.pending: list[tuple[int, int, Action]] = []
        self.last_switch = [-(10**9), -(10**9)]
        self.events: list[dict] = []

    def step(self, command: Action, step: int) -> Action:
        self.pending.append((step + self.config.delay_steps, step, command))
        values = [self.actual.ventilation, self.actual.irrigation]
        remaining = []
        for due, generated, requested in self.pending:
            if due > step:
                remaining.append((due, generated, requested))
                continue
            failed = any(window.active(step) for window in self.config.failures)
            status = "failed" if failed else "applied"
            if not failed:
                limited = False
                for i, target in enumerate((requested.ventilation, requested.irrigation)):
                    if values[i] != target:
                        if step - self.last_switch[i] >= self.config.min_interval_steps:
                            values[i] = target
                            self.last_switch[i] = step
                        else:
                            limited = True
                if limited:
                    status = "limited"
            self.events.append(
                {
                    "generated_step": generated,
                    "execution_step": step,
                    "status": status,
                    "ventilation": requested.ventilation,
                    "irrigation": requested.irrigation,
                }
            )
        self.pending = remaining
        self.actual = Action(*values)
        return self.actual
