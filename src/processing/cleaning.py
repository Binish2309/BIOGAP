"""
src/processing/cleaning.py

Two responsibilities, kept clearly separate:

1. normalise_<source>(): map a source's RAW column layout (as written by
   the ingestion connectors, unmodified) into the STANDARD_COLUMNS schema.
   This is a renaming/reshaping step -- it does not drop rows and does not
   invent values. Effort fields are populated only for sources that
   actually provide them.

2. clean_standard_frame(): once data is in the standard schema (whether
   from one source or concatenated from several), apply the same minimal,
   documented, non-destructive cleaning used in the Stage 2 GBIF script:
   whitespace trimming, empty-string -> <NA> normalisation, year coercion,
   coordinate validity flagging (NOT removal), duplicate flagging +
   removal (exact same-source duplicates only), and missing-value
   indicator columns. Every operation is logged in the returned report.

Per project rules: no row is ever dropped because a field is missing.
Rows are only ever dropped for being an exact duplicate within the same
source, and that is logged with a count and reason every time.
"""

from __future__ import annotations

import pandas as pd

from src.processing.schema import STANDARD_COLUMNS, empty_standard_frame
from src.processing.validation import (
    flag_invalid_coordinates, flag_duplicate_records, parse_year_safe,
    validate_year_range,
)
from src.processing.taxonomy import normalise_text_field


def normalise_gbif(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return empty_standard_frame()
    out = pd.DataFrame({
        "source": "GBIF",
        "record_id": raw_df["gbif_key"].astype("string"),
        "scientific_name": raw_df["scientificName"],
        "taxonomic_rank": pd.NA,  # GBIF search results don't reliably include a plain rank field in this connector's extract
        "kingdom": raw_df["kingdom"],
        "phylum": raw_df["phylum"],
        "taxon_class": raw_df["class"],
        "order": raw_df["order"],
        "family": raw_df["family"],
        "genus": raw_df["genus"],
        "latitude": pd.to_numeric(raw_df["decimalLatitude"], errors="coerce"),
        "longitude": pd.to_numeric(raw_df["decimalLongitude"], errors="coerce"),
        "observation_date": raw_df["eventDate"],
        "year": parse_year_safe(raw_df["year"]),
        "basis_of_record": raw_df["basisOfRecord"],
        "dataset": raw_df["datasetKey"],
        "publisher": raw_df["publishingOrgKey"],
        "license": raw_df["license"],
        "has_media": raw_df["has_media"],
        "effort_distance_km": pd.NA,       # GBIF does not provide structured effort data
        "effort_duration_min": pd.NA,
        "effort_complete_checklist": pd.NA,
        "is_test_data": False,
    })
    return out[STANDARD_COLUMNS]


def normalise_inaturalist(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return empty_standard_frame()
    out = pd.DataFrame({
        "source": "iNaturalist",
        "record_id": raw_df["inat_id"].astype("string"),
        "scientific_name": raw_df["taxon_name"],
        "taxonomic_rank": raw_df["taxon_rank"],
        "kingdom": pd.NA,       # iNaturalist's /observations response (as parsed here) exposes
        "phylum": pd.NA,        # iconic_taxon_name, not the full Linnaean hierarchy; a fuller
        "taxon_class": pd.NA,   # hierarchy requires an extra per-taxon lookup (taxa/{id}) not
        "order": pd.NA,         # implemented in this connector -- left explicitly missing
        "family": pd.NA,        # rather than guessed from iconic_taxon_name.
        "genus": pd.NA,
        "latitude": pd.to_numeric(raw_df["latitude"], errors="coerce"),
        "longitude": pd.to_numeric(raw_df["longitude"], errors="coerce"),
        "observation_date": raw_df["observed_on"],
        "year": parse_year_safe(pd.to_datetime(raw_df["observed_on"], errors="coerce").dt.year),
        "basis_of_record": "HUMAN_OBSERVATION",  # iNaturalist observations are consistently this
        "dataset": "iNaturalist",
        "publisher": "iNaturalist",
        "license": raw_df["license_code"],
        "has_media": raw_df["photo_count"].apply(lambda n: n > 0 if pd.notna(n) else "UNKNOWN"),
        "effort_distance_km": pd.NA,
        "effort_duration_min": pd.NA,
        "effort_complete_checklist": pd.NA,
        "is_test_data": False,
    })
    # iconic_taxon_name is retained as a bonus column for reference even
    # though it doesn't map cleanly onto kingdom/class; keep it alongside.
    out["inaturalist_iconic_taxon_name"] = raw_df["iconic_taxon_name"]
    return out[[c for c in out.columns]]


def clean_standard_frame(df: pd.DataFrame, core_fields_to_flag: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """
    Apply minimal, documented, non-destructive cleaning to a DataFrame
    already in the standard schema (from one or several sources
    concatenated together). Returns (cleaned_df, report).
    """
    report = {"rows_before": int(len(df)), "operations": []}
    out = df.copy()

    text_cols = [c for c in ["scientific_name", "taxonomic_rank", "kingdom", "phylum",
                              "taxon_class", "order", "family", "genus", "basis_of_record",
                              "dataset", "publisher", "license", "observation_date"]
                 if c in out.columns]
    for col in text_cols:
        out[col] = normalise_text_field(out[col])
    report["operations"].append({"step": "trim_and_collapse_whitespace", "columns": text_cols})

    blanked = 0
    for col in out.columns:
        if out[col].dtype == object or str(out[col].dtype) == "string":
            mask = out[col].apply(lambda v: isinstance(v, str) and v.strip() == "")
            blanked += int(mask.sum())
            out.loc[mask, col] = pd.NA
    report["operations"].append({"step": "normalise_empty_strings_to_NA", "cells_changed": blanked})

    bad_years = int(validate_year_range(out["year"]).sum()) if "year" in out.columns else 0
    if bad_years:
        out.loc[validate_year_range(out["year"]), "year"] = pd.NA
    report["operations"].append({"step": "flag_and_null_implausible_years",
                                  "range_checked": "1800-2100", "rows_affected": bad_years})

    out["invalid_coordinates_flag"] = flag_invalid_coordinates(out)
    report["operations"].append({
        "step": "flag_invalid_coordinates (NOT removed -- flagged only)",
        "rows_flagged": int(out["invalid_coordinates_flag"].sum()),
    })

    core_fields_to_flag = core_fields_to_flag or [
        "scientific_name", "year", "observation_date", "family", "genus", "license",
    ]
    for col in core_fields_to_flag:
        if col in out.columns:
            out[f"missing_{col}"] = out[col].isna()
    missing_cols = [f"missing_{c}" for c in core_fields_to_flag if f"missing_{c}" in out.columns]
    out["n_missing_core_fields"] = out[missing_cols].sum(axis=1)
    report["operations"].append({"step": "add_missing_value_indicator_columns", "columns_added": missing_cols})

    before_dedup = len(out)
    dup_mask = flag_duplicate_records(out)
    out = out[~dup_mask].copy()
    removed = before_dedup - len(out)
    report["operations"].append({
        "step": "drop_exact_duplicate_source_record_id",
        "rows_removed": int(removed),
        "reason": "exact duplicate (source, record_id) pair -- the only row-removal step performed",
    })

    report["rows_after"] = int(len(out))
    report["rows_removed_total"] = int(report["rows_before"] - report["rows_after"])
    return out, report
