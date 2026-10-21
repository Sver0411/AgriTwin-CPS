from agritwin_cps.communication.simulator import CommunicationLink
from agritwin_cps.config import LinkConfig, Window
from agritwin_cps.sensors.virtual_sensor import Observation


def test_delay_expiry_loss_and_outage_recovery():
    link = CommunicationLink(LinkConfig(delay_steps=2, max_age_steps=1), "local")
    obs = Observation(0, (24, 60, 0.4))
    link.send(obs, 0, 0.5, 0)
    assert link.receive(0) == []
    assert link.receive(2) == []
    assert link.events[0]["status"] == "expired"
    link = CommunicationLink(LinkConfig(outages=[Window(start_step=1, end_step=3)]), "remote")
    link.send(Observation(1, obs.values), 1, 0.5, 0)
    assert link.events[-1]["status"] == "disconnected_at_send"
    link.send(Observation(3, obs.values), 3, 0.5, 0)
    assert len(link.receive(3)) == 1
    assert link.events[-1]["received_step"] == 3
    link = CommunicationLink(LinkConfig(packet_loss=1), "remote")
    link.send(obs, 0, 0, 0)
    assert link.receive(0) == [] and link.events[-1]["status"] == "packet_loss"


def test_inflight_outage_and_jitter_reordering():
    link = CommunicationLink(
        LinkConfig(jitter_steps=3, outages=[Window(start_step=3, end_step=4)]), "local"
    )
    link.send(Observation(0, (24, 60, 0.4)), 0, 0.5, 0.99)
    link.send(Observation(1, (25, 60, 0.4)), 1, 0.5, 0)
    assert link.receive(1)[0].generated_step == 1
    assert link.receive(3) == []
    assert link.events[0]["status"] == "disconnected_at_receive"
