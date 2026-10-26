"""Machine-readable artifact units; matching formulas are in docs/METRICS.md."""


def unit_for(name: str) -> str:
    if name.startswith(("control_valid_", "fault_label_")) or name in (
        "sampled",
        "uncertainty_fallback",
    ):
        return "boolean"
    if "application_bytes" in name:
        return "simulated application-layer byte"
    if name.startswith("trust_") or name.startswith("normalized_squared_error_"):
        return "dimensionless heuristic/diagnostic"
    if name.startswith("diagnosis_") and any(
        f"_{label}_" in name for label in ("precision", "recall", "f1", "false_positive_rate")
    ):
        return "fraction [0,1]"
    if name.endswith("_violation_integral"):
        unit = (
            "degC"
            if name.startswith("temperature")
            else "%RH"
            if name.startswith("humidity")
            else "soil-water fraction"
        )
        return f"{unit} * h"
    if name.endswith("_seconds") or name == "time_seconds":
        return "s"
    if name.endswith("_steps") or name.endswith("_step") or name == "step":
        return "simulation step"
    if name.endswith("_count") or "_count_" in name:
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
        "schema_version": "2.0",
        "time_convention": "left endpoint; action applies over [k,k+1)",
        "missing_values": "CSV: empty cell; JSON: null; never interpreted as zero",
        "trajectory_units": {name: unit_for(name) for name in trajectory_columns},
        "metric_units": {name: unit_for(name) for name in metrics},
        "events": {
            "communication_events.csv": (
                "Times: steps; null receive: undelivered; application_bytes: 34/attempt"
            ),
            "health_events.csv": (
                "step/age/duration: steps; value/prediction/residual: channel units; "
                "trust: heuristic [0,1]"
            ),
            "sampling_events.csv": (
                "Decision once per step; interval: steps; bytes_used: application bytes; "
                "normalized metrics: dimensionless"
            ),
            "estimator_events.csv": (
                "received/generated times: steps; reason includes replay/rejection policy"
            ),
            "observation_events.csv": "component validation with generation and reception steps",
            "actuator_events.csv": "Step timestamps; requested actions [0,1]; status",
            "recovery_events.csv": "Windows: steps; recovery: seconds; errors: channel units",
        },
    }
