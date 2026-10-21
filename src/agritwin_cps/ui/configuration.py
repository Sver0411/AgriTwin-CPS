"""Native experiment controls and a draft independent from completed run snapshots."""

import json
import math
from pathlib import Path

import streamlit as st
import yaml
from pydantic import ValidationError

from agritwin_cps.config import CommunicationConfig, SimulationConfig, load_config
from agritwin_cps.ui.workspace import CONTROLLERS, ESTIMATORS, PRESETS, request_signature


def new_draft(project_root: Path, preset="Nominal Operation") -> dict:
    data = load_config(project_root / "configs" / PRESETS[preset]).model_dump(mode="json")
    data["seeds"] = [data["seeds"][0]]
    return {
        "preset": preset,
        "preset_data": json.loads(json.dumps(data)),
        "data": data,
        "controllers": list(CONTROLLERS),
        "sensor_choice": "Preset faults",
        "communication_choice": "Preset link settings",
        "fault_start_hours": 10.0,
        "fault_duration_hours": 3.0,
        "yaml_mode": False,
        "yaml": "",
        "seeds_text": ", ".join(map(str, data["seeds"])),
    }


def preset_widget_values(draft: dict) -> dict:
    """Assign widget state explicitly: deleting a key can resurrect its browser-side value."""
    data = draft["data"]
    return {
        "input_duration": data["steps"] * data["dt_seconds"] / 3600,
        "input_dt": data["dt_seconds"],
        "input_seeds": draft["seeds_text"],
        "input_controllers": draft["controllers"],
        "input_estimator": data["estimator"]["method"],
        "input_sensor_fault": draft["sensor_choice"],
        **{f"input_noise_{i}": float(value) for i, value in enumerate(data["sensor"]["noise_std"])},
        "input_dropout": float(data["sensor"]["dropout_probability"]),
        "input_communication": draft["communication_choice"],
        "input_fault_start": draft["fault_start_hours"],
        "input_fault_duration": draft["fault_duration_hours"],
        "input_plant_solar": float(data["plant"]["solar_heat_c_per_h"]),
        "input_twin_solar": float(data["twin"]["solar_heat_c_per_h"]),
        "input_sensor_delay": data["sensor"]["delay_steps"],
        "input_actuator_delay": data["actuator"]["delay_steps"],
        "input_yaml_mode": False,
        "input_yaml": "",
    }


def configuration(project_root: Path):
    """Edit a lightweight draft on reruns; run nothing until the explicit button is pressed."""
    draft = st.session_state.lab_draft

    def change_preset():
        updated = new_draft(project_root, st.session_state.input_preset)
        st.session_state.lab_draft = updated
        st.session_state.update(preset_widget_values(updated))

    st.selectbox(
        "Scenario preset",
        list(PRESETS),
        index=list(PRESETS).index(draft["preset"]),
        key="input_preset",
        on_change=change_preset,
    )
    draft = st.session_state.lab_draft
    data = json.loads(json.dumps(draft["data"]))
    yaml_mode = st.session_state.get("input_yaml_mode", draft["yaml_mode"])
    a, b = st.columns(2)
    hours = a.number_input(
        "Duration (h)",
        min_value=0.05,
        value=data["steps"] * data["dt_seconds"] / 3600,
        step=1.0,
        key="input_duration",
        disabled=yaml_mode,
        help="Requested horizon, rounded up to complete simulation steps.",
    )
    dt = b.number_input(
        "Time step (s)",
        min_value=1,
        max_value=300,
        value=data["dt_seconds"],
        step=1,
        key="input_dt",
        disabled=yaml_mode,
        help="Integration interval. Model coefficients use hours internally.",
    )
    seeds_text = st.text_input(
        "Random seeds",
        value=draft["seeds_text"],
        key="input_seeds",
        disabled=yaml_mode,
        help="Comma-separated integers. Multiple seeds enable paired statistics.",
    )
    controllers = st.multiselect(
        "Controllers",
        list(CONTROLLERS),
        default=draft["controllers"],
        format_func=CONTROLLERS.get,
        key="input_controllers",
        help="Both controllers share weather, disturbance and fault random draws.",
    )
    method = st.selectbox(
        "State estimator",
        list(ESTIMATORS),
        format_func=ESTIMATORS.get,
        index=list(ESTIMATORS).index(data["estimator"]["method"]),
        key="input_estimator",
        disabled=yaml_mode,
        help="Fixed-gain correction or model-only propagation. Neither is a Kalman filter.",
    )
    with st.expander("Sensing & fault scenarios"):
        sensor_options = [
            "Preset faults",
            "No injected sensor fault",
            "Missing observations",
            "Temperature drift",
            "Temperature stuck-at",
        ]
        sensor_choice = st.selectbox(
            "Sensor fault",
            sensor_options,
            index=sensor_options.index(draft["sensor_choice"]),
            key="input_sensor_fault",
            disabled=yaml_mode,
        )
        noise = []
        for i, (label, step, fmt) in enumerate(
            (
                ("Temperature noise SD (°C)", 0.1, "%.2f"),
                ("Humidity noise SD (%RH)", 0.5, "%.2f"),
                ("Moisture noise SD (fraction)", 0.005, "%.4f"),
            )
        ):
            noise.append(
                st.number_input(
                    label,
                    min_value=0.0,
                    value=float(data["sensor"]["noise_std"][i]),
                    step=step,
                    format=fmt,
                    key=f"input_noise_{i}",
                    disabled=yaml_mode,
                )
            )
        dropout = st.slider(
            "Independent channel dropout",
            0.0,
            1.0,
            float(data["sensor"]["dropout_probability"]),
            0.05,
            key="input_dropout",
            disabled=yaml_mode,
            help="Probability of a missing sample per channel and step.",
        )
        comm_options = [
            "Preset link settings",
            "No link faults",
            "Remote monitoring outage",
            "Local sensor outage",
        ]
        communication_choice = st.selectbox(
            "Communication scenario",
            comm_options,
            index=comm_options.index(draft["communication_choice"]),
            key="input_communication",
            disabled=yaml_mode,
            help="Remote telemetry and local sensing are independent links.",
        )
        start = st.number_input(
            "Custom fault start (h)",
            min_value=0.0,
            value=draft["fault_start_hours"],
            step=1.0,
            key="input_fault_start",
            disabled=yaml_mode,
        )
        duration = st.number_input(
            "Custom fault duration (h)",
            min_value=0.05,
            value=draft["fault_duration_hours"],
            step=1.0,
            key="input_fault_duration",
            disabled=yaml_mode,
        )
        st.caption(
            "Custom windows apply to custom sensor/link faults. Preset windows stay unchanged."
        )
    with st.expander("Advanced Settings"):
        plant_solar = st.number_input(
            "Plant solar heating (°C/h)",
            min_value=0.0,
            max_value=20.0,
            value=float(data["plant"]["solar_heat_c_per_h"]),
            step=0.5,
            key="input_plant_solar",
            disabled=yaml_mode,
        )
        twin_solar = st.number_input(
            "Twin solar heating (°C/h)",
            min_value=0.0,
            max_value=20.0,
            value=float(data["twin"]["solar_heat_c_per_h"]),
            step=0.5,
            key="input_twin_solar",
            disabled=yaml_mode,
            help="Change independently to explore model mismatch.",
        )
        sensor_delay = st.number_input(
            "Sensor measurement delay (steps)",
            min_value=0,
            max_value=10000,
            value=data["sensor"]["delay_steps"],
            key="input_sensor_delay",
            disabled=yaml_mode,
        )
        actuator_delay = st.number_input(
            "Actuator delay (steps)",
            min_value=0,
            max_value=10000,
            value=data["actuator"]["delay_steps"],
            key="input_actuator_delay",
            disabled=yaml_mode,
        )
        use_yaml = st.checkbox(
            "Use full YAML configuration", value=draft["yaml_mode"], key="input_yaml_mode"
        )
        if use_yaml:
            st.caption("YAML controls settings, seeds and time. Controller selection stays active.")
            yaml_text = st.text_area(
                "Full configuration YAML",
                value=draft["yaml"] or yaml.safe_dump(data, sort_keys=False),
                height=320,
                key="input_yaml",
            )
        else:
            yaml_text = draft["yaml"]
    data.update(steps=math.ceil(hours * 3600 / dt), dt_seconds=dt)
    data["estimator"]["method"] = method
    data["sensor"].update(noise_std=noise, dropout_probability=dropout, delay_steps=sensor_delay)
    data["actuator"]["delay_steps"] = actuator_delay
    data["plant"]["solar_heat_c_per_h"] = plant_solar
    data["twin"]["solar_heat_c_per_h"] = twin_solar
    first, last = math.ceil(start * 3600 / dt), math.ceil((start + duration) * 3600 / dt)
    if sensor_choice == "Preset faults":
        data["sensor"]["faults"] = draft["preset_data"]["sensor"]["faults"]
    else:
        faults = []
        if sensor_choice == "Missing observations":
            faults = [
                {"channel": c, "kind": "missing", "start_step": first, "end_step": last}
                for c in ("temperature", "humidity", "moisture")
            ]
        elif sensor_choice in ("Temperature drift", "Temperature stuck-at"):
            faults = [
                {
                    "channel": "temperature",
                    "kind": "drift" if sensor_choice == "Temperature drift" else "stuck",
                    "magnitude": 0.4 if sensor_choice == "Temperature drift" else 24.0,
                    "start_step": first,
                    "end_step": last,
                }
            ]
        data["sensor"]["faults"] = faults
    if communication_choice == "Preset link settings":
        data["communication"] = draft["preset_data"]["communication"]
    else:
        data["communication"] = CommunicationConfig().model_dump(mode="json")
        if communication_choice != "No link faults":
            link = "remote" if communication_choice == "Remote monitoring outage" else "local"
            data["communication"][link]["outages"] = [{"start_step": first, "end_step": last}]
    draft.update(
        data=data,
        controllers=controllers,
        seeds_text=seeds_text,
        sensor_choice=sensor_choice,
        communication_choice=communication_choice,
        fault_start_hours=start,
        fault_duration_hours=duration,
        yaml_mode=use_yaml,
        yaml=yaml_text,
    )
    try:
        if use_yaml:
            candidate = yaml.safe_load(yaml_text)
        else:
            candidate = json.loads(json.dumps(data))
            candidate["seeds"] = [int(s.strip()) for s in seeds_text.split(",")]
        config = SimulationConfig.model_validate(candidate)
        if not controllers:
            raise ValueError("Select at least one controller.")
    except (ValidationError, ValueError, yaml.YAMLError) as exc:
        st.error("Check the draft configuration before running.")
        with st.expander("Configuration details"):
            st.code(str(exc))
        st.session_state.lab_draft_invalid = True
        st.session_state.lab_draft_signature = None
        return None, controllers
    st.session_state.lab_draft_invalid = False
    st.session_state.lab_draft_signature = request_signature(config, controllers)
    st.caption(
        f"{config.steps:,} steps · {config.steps * config.dt_seconds / 3600:g} h · "
        f"{len(config.seeds) * len(controllers)} simulation run(s)"
    )
    with st.expander("Resolved run configuration"):
        st.code(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False), language="yaml")
    return config, controllers
