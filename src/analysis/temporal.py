"""
src/analysis/temporal.py

Temporal coverage analysis. Reports which years/months have relatively
more or less recording activity WITHIN this dataset. Per project rules,
this does not label any period as having "low biodiversity" -- only as
having lower recorded observation density than other periods in the same
dataset.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.processing.temporal import records_per_year, records_per_month
from src.processing.validation import assert_no_test_data_in_research_path


def yearly_coverage(df: pd.DataFrame) -> pd.DataFrame:
    assert_no_test_data_in_research_path(df, caller="temporal.yearly_coverage")
    counts = records_per_year(df)
    if counts.empty:
        return pd.DataFrame(columns=["year", "record_count", "relative_coverage"])
    out = counts.reset_index()
    out.columns = ["year", "record_count"]
    out["relative_coverage"] = out["record_count"] / out["record_count"].max()
    return out


def monthly_pattern(df: pd.DataFrame, month_col: str = "derived_month") -> pd.DataFrame:
    """Pooled-across-years month-of-year pattern (seasonality of RECORDING
    effort, not of species' actual seasonal presence)."""
    assert_no_test_data_in_research_path(df, caller="temporal.monthly_pattern")
    if month_col not in df.columns:
        return pd.DataFrame(columns=["month", "record_count"])
    counts = records_per_month(df, month_col=month_col)
    out = counts.reset_index()
    out.columns = ["month", "record_count"]
    return out


def low_coverage_years(yearly_df: pd.DataFrame, quantile_threshold: float = 0.25) -> pd.DataFrame:
    """
    Flag years falling at or below a given quantile of this dataset's own
    year-by-year record counts. The threshold is a configurable, relative
    statement about THIS dataset's distribution -- not a claim about an
    externally-validated "adequate sampling" threshold, which does not yet
    exist for this project (see RESEARCH_METHOD.md, gap-score section).
    """
    if yearly_df.empty:
        return yearly_df
    cutoff = yearly_df["record_count"].quantile(quantile_threshold)
    flagged = yearly_df[yearly_df["record_count"] <= cutoff].copy()
    flagged["quantile_threshold_used"] = quantile_threshold
    return flagged


def coefficient_of_variation(counts: pd.Series) -> float | None:
    """
    CV = std / mean of per-period record counts. Higher CV = more uneven
    temporal coverage. A simple, standard dispersion statistic -- not a
    validated "gap" metric on its own.
    """
    if counts.empty or counts.mean() == 0:
        return None
    return float(counts.std(ddof=0) / counts.mean())
