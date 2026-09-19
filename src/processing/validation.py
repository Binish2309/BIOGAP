"""
src/processing/validation.py

Pure validation functions. Nothing here modifies data or drops rows --
these functions classify/flag; callers (cleaning.py) decide what to do
with the flags, and per project rules, "what to do" is never "silently
delete".
"""

from __future__ import annotations

import pandas as pd

from src.processing.schema import STANDARD_COLUMNS, validate_columns


class ResearchIntegrityError(Exception):
    """Raised when code outside tests/ tries to operate on test/mock data."""


def assert_no_test_data_in_research_path(df: pd.DataFrame, caller: str = "") -> None:
    """
    Hard guard used throughout the analysis layer. If a DataFrame carrying
    is_test_data == True reaches an analysis function outside of tests/,
    this raises rather than silently producing results that mix real and
    mock data. This is the code-level enforcement of the project's
    "test data must never appear in research results" rule.
    """
    if "is_test_data" not in df.columns:
        return  # nothing to check; caller is responsible for schema validity separately
    if bool(df["is_test_data"].fillna(False).any()):
        raise ResearchIntegrityError(
            f"Refusing to proceed{' in ' + caller if caller else ''}: this DataFrame "
            f"contains rows flagged is_test_data=True. Test/mock data must never be "
            f"used in research analysis. If you are inside tests/, this guard should "
            f"not be called on the mock frame at all -- call the underlying function "
            f"directly instead of any wrapper that enforces this check."
        )


def check_schema(df: pd.DataFrame) -> dict:
    """Return {'missing_columns': [...], 'ok': bool}."""
    missing = validate_columns(df)
    return {"missing_columns": missing, "ok": len(missing) == 0}


def flag_invalid_coordinates(df: pd.DataFrame) -> pd.Series:
    """
    Return a boolean Series, True where a record's coordinates are
    structurally invalid: out of the valid lat/lon range, exactly (0, 0)
    ("null island" -- a classic sign of a bad default value upstream), or
    missing. This does NOT check whether coordinates fall inside any
    particular study-area boundary -- that is a separate, spatial-analysis
    concern (src/analysis/spatial.py), not a data-quality concern.
    """
    lat, lon = df["latitude"], df["longitude"]
    missing = lat.isna() | lon.isna()
    out_of_range = (~missing) & ((lat < -90) | (lat > 90) | (lon < -180) | (lon > 180))
    null_island = (~missing) & (lat == 0) & (lon == 0)
    return missing | out_of_range | null_island


def flag_duplicate_records(df: pd.DataFrame) -> pd.Series:
    """
    Return a boolean Series, True for rows that are exact duplicates on
    (source, record_id) -- i.e. the same platform reporting the identical
    record twice, e.g. from overlapping paginated requests. This does NOT
    flag cross-platform duplicates (the same real-world observation
    appearing in both GBIF and iNaturalist) -- that is a much harder,
    probabilistic problem (matching on species+coordinates+date within a
    tolerance) that belongs in analysis/cross_platform.py as an explicit,
    documented step, not a silent cleaning operation.
    """
    return df.duplicated(subset=["source", "record_id"], keep="first")


def flag_missing_core_fields(df: pd.DataFrame, core_fields: list[str]) -> pd.DataFrame:
    """
    Return a DataFrame of boolean columns, one per field in core_fields,
    True where that field is missing for that row. Per project rules, this
    is used to ANNOTATE records, never to justify dropping them.
    """
    return pd.DataFrame({f"missing_{f}": df[f].isna() for f in core_fields if f in df.columns})


def parse_year_safe(year_series: pd.Series) -> pd.Series:
    """Coerce to nullable Int64; unparseable values become <NA>, never guessed."""
    return pd.to_numeric(year_series, errors="coerce").astype("Int64")


def validate_year_range(year_series: pd.Series, min_year: int = 1800, max_year: int = 2100) -> pd.Series:
    """
    Return a boolean Series, True where a parsed year is outside a sane
    range (e.g. a data-entry error like year 9999 or year 0). Bounds are
    intentionally generous (1800-2100) since GBIF legitimately holds
    centuries-old museum specimen records.
    """
    return year_series.notna() & ((year_series < min_year) | (year_series > max_year))
