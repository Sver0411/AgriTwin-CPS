"""Explicit CSV mappings and units. No interpolation, calibration or truth labels are implied."""

import hashlib
import io
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import Field, model_validator

from agritwin_cps.config import Channel, Settings
from agritwin_cps.models.greenhouse import CHANNELS


class ImportConfig(Settings):
    dataset_id: str = Field(min_length=1)
    origin: Literal["external_unverified", "public_measurements", "synthetic_fixture"] = (
        "external_unverified"
    )
    source_url: str | None = None
    license: str | None = None
    timestamp_column: str = "timestamp"
    timestamp_unit: Literal["datetime", "s", "ms"] = "datetime"
    timestamp_format: str | None = None
    timezone: str = "UTC"
    columns: dict[Channel, str | None] = Field(
        default_factory=lambda: dict(zip(CHANNELS, CHANNELS, strict=True))
    )
    temperature_unit: Literal["C", "F", "K"] = "C"
    humidity_unit: Literal["percent", "fraction"] = "percent"
    moisture_unit: Literal["fraction", "percent"] = "fraction"
    missing_policy: Literal["preserve", "drop_all_missing", "error"] = "preserve"
    expected_interval_seconds: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def mapped(self):
        if not any(self.columns.values()):
            raise ValueError("Map at least one measured channel")
        return self


def import_csv(source: Path | bytes, config: ImportConfig) -> tuple[pd.DataFrame, dict]:
    raw = source if isinstance(source, bytes) else source.read_bytes()
    frame = pd.read_csv(io.BytesIO(raw))
    required = [config.timestamp_column, *[v for v in config.columns.values() if v]]
    absent = set(required) - set(frame.columns)
    if absent:
        raise ValueError(f"Missing mapped CSV columns: {sorted(absent)}")
    values = frame[config.timestamp_column]
    if config.timestamp_unit != "datetime":
        timestamps = pd.to_datetime(values, unit=config.timestamp_unit, utc=True, errors="raise")
    else:
        timestamps = pd.to_datetime(values, format=config.timestamp_format, errors="raise")
        if timestamps.dt.tz is None:
            timestamps = timestamps.dt.tz_localize(
                config.timezone, ambiguous="raise", nonexistent="raise"
            )
        timestamps = timestamps.dt.tz_convert("UTC")
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError(
            "Timestamps must be present and unique; duplicates require explicit preprocessing"
        )
    result = pd.DataFrame({"timestamp": timestamps})
    for channel in CHANNELS:
        column = config.columns.get(channel)
        result[channel] = pd.to_numeric(frame[column], errors="raise") if column else np.nan
    if config.temperature_unit == "F":
        result.temperature = (result.temperature - 32) * 5 / 9
    elif config.temperature_unit == "K":
        result.temperature -= 273.15
    if config.humidity_unit == "fraction":
        result.humidity *= 100
    if config.moisture_unit == "percent":
        result.moisture /= 100
    result = result.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if np.isinf(result[list(CHANNELS)].to_numpy()).any():
        raise ValueError(
            "Infinite measurements are not supported; use empty cells for missing values"
        )
    if (
        config.missing_policy == "error"
        and result[[c for c in CHANNELS if config.columns.get(c)]].isna().any().any()
    ):
        raise ValueError("Missing measurements violate missing_policy=error")
    if config.missing_policy == "drop_all_missing":
        result = result.dropna(subset=list(CHANNELS), how="all").reset_index(drop=True)
    if len(result) < 2:
        raise ValueError("At least two timestamped rows are required")
    intervals = result.timestamp.diff().dt.total_seconds().dropna()
    stats = {
        "dataset_id": config.dataset_id,
        "origin": config.origin,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "input_rows": len(frame),
        "processed_rows": len(result),
        "start_time": result.timestamp.iloc[0].isoformat(),
        "end_time": result.timestamp.iloc[-1].isoformat(),
        "missing_count": {c: int(result[c].isna().sum()) for c in CHANNELS},
        "interval_min_seconds": float(intervals.min()),
        "interval_max_seconds": float(intervals.max()),
        "interval_median_seconds": float(intervals.median()),
        "unexpected_interval_count": int(
            (~np.isclose(intervals, config.expected_interval_seconds)).sum()
        )
        if config.expected_interval_seconds is not None
        else None,
        "units": {"temperature": "degC", "humidity": "%RH", "moisture": "fraction"},
        "configuration": config.model_dump(mode="json"),
    }
    return result, stats


def load_data_config(path: Path):
    from agritwin_cps.data_io.replay import ReplayConfig

    data = yaml.safe_load(path.read_text())
    return ImportConfig.model_validate(data["import"]), ReplayConfig.model_validate(
        data.get("replay", {})
    )
