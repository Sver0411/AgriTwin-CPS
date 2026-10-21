"""Machine-readable artifact units; matching formulas are in docs/METRICS.md."""


def unit_for(name: str) -> str:
    if name.endswith("_seconds") or name == "time_seconds":
        return "s"
    if name.endswith("_steps") or name.endswith("_step") or name == "step":
        return "simulation step"
    if name.endswith("_count"):
        return "count"
    if "continuity" in name or "coverage" in name:
        return "fraction [0,1]"
    if name.endswith("_hours"):
        return "h (effort proxy)"
    if name == "irrigation_amount_fraction":
        return "cumulative soil-water fraction input (proxy)"
    if "temperature" in name:
        return "degC"
    if "humidity" in name:
        return "%RH (percentage points for errors)"
    if "moisture" in name:
        return "soil-water fraction [0,1] (fraction difference for errors)"
    if "ventilation" in name or "irrigation" in name:
        return "normalized action [0,1]"
    if name.endswith("_proxy"):
        return "dimensionless proxy [0,1]"
    return "boolean"


def artifact_schema(trajectory_columns, metrics) -> dict:
    return {
        "schema_version": "1.0",
        "time_convention": "left endpoint; action applies over [k,k+1)",
        "missing_values": "CSV: empty cell; JSON: null; never interpreted as zero",
        "trajectory_units": {name: unit_for(name) for name in trajectory_columns},
        "metric_units": {name: unit_for(name) for name in metrics},
        "events": {
            "communication_events.csv": "Times: steps; null receive: undelivered",
            "observation_events.csv": "component validation with generation and reception steps",
            "actuator_events.csv": "Step timestamps; requested actions [0,1]; status",
            "recovery_events.csv": "Windows: steps; recovery: seconds; errors: channel units",
        },
    }
