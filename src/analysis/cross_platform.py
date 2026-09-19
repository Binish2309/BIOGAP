"""
src/analysis/cross_platform.py

Cross-platform comparison. Per project rules: "Do NOT directly compare raw
counts without accounting for differences in platform structure,
taxonomic coverage and observation effort." Every function here therefore
returns SHARES, RANGES, or COVERAGE measures within each platform first,
and only compares those normalised quantities across platforms -- plus an
explicit, printed caveat dict that the UI is expected to display alongside
any cross-platform chart.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.taxonomic import group_representation
from src.analysis.spatial import observation_density_by_cell
from src.processing.validation import assert_no_test_data_in_research_path

PLATFORM_STRUCTURE_CAVEATS = {
    "GBIF": (
        "Aggregator of multiple underlying sources (including a Research-Grade-only "
        "mirror of iNaturalist and, in some cases, partner-mediated eBird data). No "
        "structured observation-effort field. Coverage reflects whichever underlying "
        "datasets have been published to GBIF, which can lag their original platforms."
    ),
    "iNaturalist": (
        "Photo/audio-evidence citizen-science platform, identification community-"
        "verified. No structured observation-effort field. This connector does not "
        "filter by quality_grade, so both 'research' and 'needs_id' grade records are "
        "included -- GBIF's iNaturalist mirror includes Research Grade only, so raw "
        "counts between this source and GBIF's iNaturalist-derived records are not "
        "directly comparable for that reason alone."
    ),
}


def taxonomic_composition_by_source(df: pd.DataFrame) -> pd.DataFrame:
    """Per-source share of records by major taxonomic group -- the
    normalised (not raw-count) comparison this module's docstring
    requires."""
    assert_no_test_data_in_research_path(df, caller="cross_platform.taxonomic_composition_by_source")
    frames = []
    for source, sub in df.groupby("source"):
        rep = group_representation(sub)
        rep["source"] = source
        frames.append(rep)
    if not frames:
        return pd.DataFrame(columns=["source", "major_group", "record_count", "unique_species", "share_of_records"])
    return pd.concat(frames, ignore_index=True)


def temporal_range_by_source(df: pd.DataFrame) -> pd.DataFrame:
    """Per-source earliest/latest year and number of distinct years
    represented -- lets you see, e.g., that one source's data spans days
    while another spans decades, BEFORE looking at any count."""
    assert_no_test_data_in_research_path(df, caller="cross_platform.temporal_range_by_source")
    rows = []
    for source, sub in df.groupby("source"):
        years = sub["year"].dropna()
        rows.append({
            "source": source,
            "earliest_year": int(years.min()) if not years.empty else None,
            "latest_year": int(years.max()) if not years.empty else None,
            "n_distinct_years": int(years.nunique()),
            "n_records_with_year": int(years.shape[0]),
            "n_records_missing_year": int(sub["year"].isna().sum()),
        })
    return pd.DataFrame(rows)


def spatial_extent_by_source(df: pd.DataFrame, grid_size_deg: float) -> pd.DataFrame:
    """Per-source count of distinct occupied grid cells and coordinate
    bounding extent -- a normalised (grid-cell) measure of spatial spread,
    rather than a raw point count."""
    assert_no_test_data_in_research_path(df, caller="cross_platform.spatial_extent_by_source")
    rows = []
    for source, sub in df.groupby("source"):
        valid = sub[sub["latitude"].notna() & sub["longitude"].notna()]
        density = observation_density_by_cell(valid, grid_size_deg) if not valid.empty else pd.DataFrame()
        rows.append({
            "source": source,
            "n_occupied_cells": int(len(density)),
            "n_records_with_coordinates": int(len(valid)),
            "lat_range": [float(valid["latitude"].min()), float(valid["latitude"].max())] if not valid.empty else None,
            "lon_range": [float(valid["longitude"].min()), float(valid["longitude"].max())] if not valid.empty else None,
        })
    return pd.DataFrame(rows)


def cross_platform_summary(df: pd.DataFrame, grid_size_deg: float) -> dict:
    """Bundle the three normalised comparisons plus the mandatory caveats,
    for direct use by the Cross-Platform page."""
    assert_no_test_data_in_research_path(df, caller="cross_platform.cross_platform_summary")
    sources_present = sorted(df["source"].dropna().unique().tolist())
    return {
        "sources_present": sources_present,
        "taxonomic_composition": taxonomic_composition_by_source(df).to_dict(orient="records"),
        "temporal_range": temporal_range_by_source(df).to_dict(orient="records"),
        "spatial_extent": spatial_extent_by_source(df, grid_size_deg).to_dict(orient="records"),
        "platform_structure_caveats": {s: PLATFORM_STRUCTURE_CAVEATS.get(s, "No documented caveat on file.")
                                        for s in sources_present},
    }
