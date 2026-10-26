"""Audited adapter for user-downloaded Mendeley 54htxm94bv v2 CSVs; never repairs dates."""

import hashlib
from pathlib import Path

import pandas as pd

from agritwin_cps.simulation.runner import reserve_output, write_json

SOURCE_URL = "https://data.mendeley.com/datasets/54htxm94bv/2"
TARGET = "Actual Temperature Middle ((T[n])"
# Contiguous date ranges chosen from timestamp quality alone, before evaluating estimators.
SEGMENTS = {
    "development": ("Training Set.csv", "2022-11-25", "2022-12-01"),
    "final_evaluation": ("Test Set.csv", "2022-12-28", "2022-12-31"),
}


def prepare_south_africa(source_directory: Path, output: Path) -> dict:
    reserve_output(output)
    audit = {
        "source_url": SOURCE_URL,
        "license": "CC BY 4.0",
        "timezone_assumption": "Africa/Johannesburg; source CSV has no timezone",
        "selection_basis": "timestamp quality only; no value-based filtering or date repair",
        "files": {},
        "segments": {},
    }
    frames = {}
    for filename in ("Training Set.csv", "Test Set.csv", "Full Data Set.csv"):
        path = source_directory / filename
        frame = pd.read_csv(path)
        timestamps = pd.to_datetime(frame.Date + " " + frame.Time, format="%Y/%m/%d %H:%M:%S")
        differences = timestamps.diff().dt.total_seconds()
        audit["files"][filename] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": len(frame),
            "duplicate_timestamps": int(timestamps.duplicated().sum()),
            "backward_intervals": int((differences < 0).sum()),
            "gaps_over_one_hour": int((differences > 3600).sum()),
            "earliest_timestamp": timestamps.min().isoformat(),
            "latest_timestamp": timestamps.max().isoformat(),
            "median_interval_seconds": float(differences.median()),
        }
        frames[filename] = (frame, timestamps)
    for partition, (filename, start, end) in SEGMENTS.items():
        frame, timestamps = frames[filename]
        mask = (timestamps >= start) & (timestamps < end)
        chosen = frame.loc[mask].copy()
        selected = timestamps[mask]
        if len(selected) < 2:
            raise ValueError(f"Declared {partition} segment needs at least two rows")
        if selected.duplicated().any() or not selected.is_monotonic_increasing:
            raise ValueError(f"Declared {partition} segment has duplicate or backward timestamps")
        if selected.diff().dt.total_seconds().max() > 3600:
            raise ValueError(f"Declared {partition} segment contains a gap longer than one hour")
        normalized = pd.DataFrame(
            {
                "timestamp": selected.dt.tz_localize("Africa/Johannesburg").dt.tz_convert("UTC"),
                "temperature": chosen[TARGET],
                "original_row": chosen.index,
                "original_date": chosen.Date,
                "original_time": chosen.Time,
            }
        )
        normalized.to_csv(output / f"{partition}.csv", index=False)
        audit["segments"][partition] = {
            "source": filename,
            "local_start_inclusive": start,
            "local_end_exclusive": end,
            "selected_rows": len(normalized),
            "excluded_rows": int((~mask).sum()),
            "target_column": TARGET,
            "sha256": hashlib.sha256((output / f"{partition}.csv").read_bytes()).hexdigest(),
        }
    write_json(output / "audit.json", audit)
    return audit
