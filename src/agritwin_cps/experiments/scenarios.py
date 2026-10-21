"""Predeclared evaluation sweeps; scenario changes are not tuned to observed outcomes."""

from agritwin_cps.config import SimulationConfig

EXPERIMENTS = (
    "nominal",
    "sensor_noise",
    "missing_observations",
    "sensor_drift",
    "communication_outage",
    "model_mismatch",
    "controller_comparison",
)


def scenarios(experiment: str, base: SimulationConfig) -> list[SimulationConfig]:
    if experiment not in EXPERIMENTS:
        raise ValueError(f"unknown experiment: {experiment}")
    cases = []

    def add(label: str, changes: dict):
        # Re-validate every constructed scenario rather than bypassing Pydantic constraints.
        data = base.model_dump()
        for key, value in changes.items():
            if isinstance(value, dict):
                data[key].update(value)
            else:
                data[key] = value
        data["name"] = f"{experiment}_{label}"
        cases.append(SimulationConfig.model_validate(data))

    start = base.steps // 3

    def missing(length):
        return [
            {
                "channel": c,
                "kind": "missing",
                "start_step": start,
                "end_step": min(base.steps - 1, start + length),
            }
            for c in ("temperature", "humidity", "moisture")
        ]

    if experiment == "nominal":
        add(
            "clean",
            {
                "sensor": {
                    "noise_std": (0, 0, 0),
                    "dropout_probability": 0,
                    "faults": [],
                    "delay_steps": 0,
                },
                "process_noise_std_per_sqrt_h": (0, 0, 0),
            },
        )
    elif experiment == "sensor_noise":
        for scale in (0.0, 1.0, 3.0, 6.0):
            add(
                f"scale_{scale:g}",
                {"sensor": {"noise_std": (0.3 * scale, 1.5 * scale, 0.01 * scale)}},
            )
    elif experiment == "missing_observations":
        for probability in (0.0, 0.2, 0.5):
            add(f"drop_{probability:g}", {"sensor": {"dropout_probability": probability}})
        for length in (6, 24, 72):
            add(f"burst_{length}", {"sensor": {"faults": missing(length)}})
    elif experiment == "sensor_drift":
        for rate in (0.0, 0.2, 0.6):
            add(
                f"rate_{rate:g}",
                {
                    "sensor": {
                        "faults": [
                            {
                                "channel": "temperature",
                                "kind": "drift",
                                "magnitude": rate,
                                "start_step": start,
                                "end_step": 2 * base.steps // 3,
                            }
                        ]
                    }
                },
            )
        add(
            "bias",
            {
                "sensor": {
                    "faults": [
                        {
                            "channel": "moisture",
                            "kind": "bias",
                            "magnitude": -0.08,
                            "start_step": start,
                            "end_step": 2 * base.steps // 3,
                        }
                    ]
                }
            },
        )
    elif experiment == "communication_outage":
        for link in ("remote", "local"):
            for length in (12, 48, 96):
                communication = base.communication.model_dump()
                communication[link].update(
                    delay_steps=2,
                    jitter_steps=3,
                    packet_loss=0.1,
                    outages=[
                        {"start_step": start, "end_step": min(base.steps - 1, start + length)}
                    ],
                )
                add(f"{link}_{length}", {"communication": communication})
    elif experiment == "model_mismatch":
        for multiplier in (0.5, 1.0, 1.5, 2.0):
            add(
                f"factor_{multiplier:g}",
                {
                    "twin": {
                        "solar_heat_c_per_h": base.plant.solar_heat_c_per_h * multiplier,
                        "moisture_loss_per_h": base.plant.moisture_loss_per_h * multiplier,
                    },
                    "sensor": {"faults": missing(min(72, max(1, base.steps // 6)))},
                },
            )
    else:
        add("noisy", {"sensor": {"noise_std": (1.5, 7.5, 0.05), "dropout_probability": 0.2}})
    return cases
