"""Application-layer message transport. This is not a radio/network performance model."""

import struct

from agritwin_cps.config import LinkConfig
from agritwin_cps.sensors.virtual_sensor import Observation

# Version uint8 + timestamp uint64 + three float64 + validity mask uint8; little-endian.
MESSAGE_BYTES = struct.calcsize("<BQ3dB")


class CommunicationLink:
    def __init__(self, config: LinkConfig, name: str):
        self.config = config
        self.name = name
        self.pending: list[tuple[int, Observation, dict]] = []
        self.events: list[dict] = []

    def disconnected(self, step: int) -> bool:
        return any(window.active(step) for window in self.config.outages)

    def send(
        self,
        packet: Observation,
        step: int,
        loss_draw: float,
        jitter_draw: float,
        extra_delay_steps: int = 0,
    ) -> None:
        jitter = min(int(jitter_draw * (self.config.jitter_steps + 1)), self.config.jitter_steps)
        due = step + self.config.delay_steps + extra_delay_steps + jitter
        event = {
            "link": self.name,
            "message_id": len(self.events),
            "generated_step": packet.generated_step,
            "sent_step": step,
            "scheduled_step": due,
            "received_step": None,
            "resolved_step": None,
            "status": "queued",
            "application_bytes": MESSAGE_BYTES,
        }
        if self.disconnected(step):
            event.update(status="disconnected_at_send", resolved_step=step)
        elif loss_draw < self.config.packet_loss:
            event.update(status="packet_loss", resolved_step=step)
        else:
            self.pending.append((due, packet, event))
        self.events.append(event)

    def receive(self, step: int) -> list[Observation]:
        delivered = []
        remaining = []
        for due, packet, event in self.pending:
            if due > step:
                remaining.append((due, packet, event))
                continue
            if self.disconnected(step):
                status = "disconnected_at_receive"
            elif step - packet.generated_step > self.config.max_age_steps:
                status = "expired"
            else:
                status = "delivered"
                event["received_step"] = step
                delivered.append(packet)
            event.update(status=status, resolved_step=step)
        self.pending = remaining
        return delivered

    def finalize(self, horizon_step: int) -> None:
        for _, _, event in self.pending:
            event.update(status="pending_at_horizon", resolved_step=horizon_step)
        self.pending.clear()
