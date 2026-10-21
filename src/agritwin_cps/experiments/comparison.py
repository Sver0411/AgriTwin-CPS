"""Sample statistics and paired controller deltas, without selecting favorable seeds."""

import pandas as pd

IDENTIFIERS = ["experiment", "scenario", "controller", "seed"]


def summarize(per_seed: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    metrics = [c for c in per_seed.columns if c not in IDENTIFIERS]
    long = per_seed.melt(id_vars=groups, value_vars=metrics, var_name="metric", value_name="value")
    long["value"] = pd.to_numeric(long.value, errors="coerce")
    grouped = long.groupby([*groups, "metric"], dropna=False).value
    summary = grouped.agg(["mean", "std", "count", "size"]).reset_index()
    return summary.rename(columns={"count": "n_valid", "size": "n_total"}).assign(
        n_missing=lambda f: f.n_total - f.n_valid
    )


def paired_differences(per_seed: pd.DataFrame) -> pd.DataFrame:
    keys = ["experiment", "scenario", "seed"]
    a = per_seed[per_seed.controller == "threshold"].set_index(keys)
    b = per_seed[per_seed.controller == "twin_assisted"].set_index(keys)
    metrics = [c for c in per_seed.columns if c not in IDENTIFIERS]
    delta = b[metrics].apply(pd.to_numeric, errors="coerce") - a[metrics].apply(
        pd.to_numeric, errors="coerce"
    )
    return delta.reset_index().assign(controller="twin_minus_threshold")
