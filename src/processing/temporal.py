"""
src/processing/temporal.py

Date/time parsing and bucketing helpers shared by cleaning and the
temporal-gap analysis. No date is ever invented: unparseable or absent
dates stay missing (<NA>) all the way through.
"""

from __future__ import annotations

import pandas as pd


def parse_observation_date(date_series: pd.Series) -> pd.Series:
    """
    Parse a column of source-provided date strings into pandas datetime.
    Values that fail to parse become NaT, not a guessed date. Uses
    errors='coerce' explicitly so this is auditable, not silent.
    """
    return pd.to_datetime(date_series, errors="coerce", utc=False)


def extract_year_month(parsed_dates: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        "derived_year": parsed_dates.dt.year.astype("Int64"),
        "derived_month": parsed_dates.dt.month.astype("Int64"),
    })


def records_per_year(df: pd.DataFrame, year_col: str = "year") -> pd.Series:
    """Count of records per year, years with zero records NOT interpolated
    or filled in -- only years that actually appear are reported. Callers
    doing a full-range chart should reindex explicitly against a real
    calendar range themselves and choose how to display true zero-record
    years (as 0, not as missing)."""
    return df[year_col].dropna().astype(int).value_counts().sort_index()


def records_per_month(df: pd.DataFrame, month_col: str = "derived_month") -> pd.Series:
    """Count of records per calendar month (1-12), pooled across all years
    -- describes seasonal reporting concentration, not any one year."""
    return df[month_col].dropna().astype(int).value_counts().sort_index()


def year_coverage_summary(df: pd.DataFrame, year_col: str = "year") -> dict:
    years = df[year_col].dropna()
    if years.empty:
        return {"earliest_year": None, "latest_year": None, "n_distinct_years": 0,
                "n_records_with_year": 0, "n_records_missing_year": int(df[year_col].isna().sum())}
    return {
        "earliest_year": int(years.min()),
        "latest_year": int(years.max()),
        "n_distinct_years": int(years.nunique()),
        "n_records_with_year": int(years.shape[0]),
        "n_records_missing_year": int(df[year_col].isna().sum()),
    }
