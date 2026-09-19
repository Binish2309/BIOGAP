"""
src/processing/schema.py

The standard, source-agnostic internal data model that GBIF / iNaturalist /
occurrence records are normalised into, so downstream analysis code never needs
to know which platform a record came from.

DESIGN NOTES
------------
- `taxon_class` is used instead of the literal word `class`, which is a
  Python reserved word. This is a deliberate, documented naming choice,
  not a data change -- see DATA_DICTIONARY.md.
- Effort-related fields (`effort_distance_km`, `effort_duration_min`,
  `effort_complete_checklist`) are included in the schema but are only
  ever populated for sources that actually provide them (currently:
  a full eBird-style checklist export, not currently ingested by this
  project). For every other source they are left as
  missing (pandas <NA>), never estimated or defaulted to a placeholder
  value. See RESEARCH_METHOD.md, section on cross-platform comparison.
- `is_test_data` is a mandatory boolean column. It is False for every row
  that reaches this schema via a real ingestion module, and True only for
  rows produced inside tests/. Analysis code MUST refuse to run on any
  DataFrame containing is_test_data == True outside of the tests/ folder
  (see processing.validation.assert_no_test_data_in_research_path).
"""

from __future__ import annotations

import pandas as pd

# Canonical column order for the standard schema.
STANDARD_COLUMNS = [
    "source",                    # "GBIF" | "iNaturalist"
    "record_id",                 # source's own stable identifier for the record
    "scientific_name",
    "taxonomic_rank",
    "kingdom",
    "phylum",
    "taxon_class",               # see docstring: "class" is a reserved word
    "order",
    "family",
    "genus",
    "latitude",
    "longitude",
    "observation_date",          # ISO date string where available
    "year",
    "basis_of_record",
    "dataset",
    "publisher",
    "license",
    "has_media",                 # True / False / "UNKNOWN"
    # --- effort fields: populated ONLY where the source actually provides them ---
    "effort_distance_km",
    "effort_duration_min",
    "effort_complete_checklist",
    # --- bookkeeping ---
    "is_test_data",
]

# dtype hints used when constructing an empty standard-schema DataFrame,
# so downstream code can rely on consistent types even with zero rows.
_DTYPES = {
    "source": "string",
    "record_id": "string",
    "scientific_name": "string",
    "taxonomic_rank": "string",
    "kingdom": "string",
    "phylum": "string",
    "taxon_class": "string",
    "order": "string",
    "family": "string",
    "genus": "string",
    "latitude": "float64",
    "longitude": "float64",
    "observation_date": "string",
    "year": "Int64",
    "basis_of_record": "string",
    "dataset": "string",
    "publisher": "string",
    "license": "string",
    "has_media": "object",   # tri-state: True / False / "UNKNOWN"
    "effort_distance_km": "float64",
    "effort_duration_min": "float64",
    "effort_complete_checklist": "object",  # True / False / <NA>
    "is_test_data": "boolean",
}


def empty_standard_frame() -> pd.DataFrame:
    """Return a zero-row DataFrame with the correct columns and dtypes."""
    df = pd.DataFrame({col: pd.Series(dtype=_DTYPES[col]) for col in STANDARD_COLUMNS})
    return df


def validate_columns(df: pd.DataFrame) -> list[str]:
    """Return a list of STANDARD_COLUMNS missing from df (empty list = OK)."""
    return [c for c in STANDARD_COLUMNS if c not in df.columns]
