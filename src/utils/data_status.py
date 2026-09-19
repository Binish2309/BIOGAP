"""
src/utils/data_status.py

Single source of truth the Streamlit pages use to decide whether to show
real analysis or an honest "Verified dataset pending" state. No page
should independently decide "there's probably data" -- they all call
get_data_status() / load_combined_data().
"""

from __future__ import annotations

import json
from typing import Optional

import pandas as pd

from src.pipeline import COMBINED_PROCESSED_PATH, RUN_SUMMARY_PATH
from src.config import RAW_DIR, METADATA_DIR

OSM_RAW_PATH = RAW_DIR / "osm_roads_raw.csv"
OSM_PROVENANCE_PATH = METADATA_DIR / "osm_context_provenance.json"


def get_run_summary() -> Optional[dict]:
    if not RUN_SUMMARY_PATH.exists():
        return None
    try:
        return json.loads(RUN_SUMMARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_combined_data() -> Optional[pd.DataFrame]:
    """
    Returns the combined, cleaned, standard-schema DataFrame if a real
    pipeline run has produced one with at least one row, else None.
    Never returns a synthetic/mock frame.
    """
    if not COMBINED_PROCESSED_PATH.exists():
        return None
    df = pd.read_csv(COMBINED_PROCESSED_PATH)
    if df.empty:
        return None
    return df


def data_status_message() -> str:
    """Short, honest, user-facing string describing current data status."""
    summary = get_run_summary()
    if summary is None:
        return "Awaiting real dataset -- no ingestion run has completed yet."
    status = summary.get("data_status")
    if status == "REAL_DATA_AVAILABLE":
        n = summary.get("combined_row_count", 0)
        return f"Verified real data available -- {n:,} records from the last pipeline run."
    return "Verified data not available -- the last pipeline run retrieved zero usable records. See the Methodology page for per-source status."


def dataset_summary_stats(df: pd.DataFrame) -> dict:
    """
    Honest, real-data-only summary statistics computed directly from the
    combined DataFrame, for the Overview page's "REAL DATA AVAILABLE"
    panel. Every value here is derived from the actual dataset on disk --
    nothing is estimated or assumed.
    """
    n_records = int(len(df))
    n_species = int(df["scientific_name"].dropna().nunique()) if "scientific_name" in df.columns else None

    years = df["year"].dropna() if "year" in df.columns else pd.Series(dtype="float64")
    date_coverage = None
    if not years.empty:
        date_coverage = f"{int(years.min())}\u2013{int(years.max())}"

    geo_coverage = None
    if "latitude" in df.columns and "longitude" in df.columns:
        lat = pd.to_numeric(df["latitude"], errors="coerce").dropna()
        lon = pd.to_numeric(df["longitude"], errors="coerce").dropna()
        if not lat.empty and not lon.empty:
            geo_coverage = {
                "min_lat": float(lat.min()), "max_lat": float(lat.max()),
                "min_lon": float(lon.min()), "max_lon": float(lon.max()),
            }

    by_source = df["source"].value_counts().to_dict() if "source" in df.columns else {}

    return {
        "n_records": n_records,
        "n_species": n_species,
        "date_coverage": date_coverage,
        "geo_coverage": geo_coverage,
        "records_by_source": {str(k): int(v) for k, v in by_source.items()},
    }


def load_osm_context_data() -> Optional[pd.DataFrame]:
    """
    Returns the raw OSM road/path geometry DataFrame if a real ingestion
    run has produced one, else None. Never returns synthetic data. See
    src/ingestion/osm_context.py for what this data is and is not.
    """
    if not OSM_RAW_PATH.exists():
        return None
    df = pd.read_csv(OSM_RAW_PATH)
    if df.empty:
        return None
    return df


def get_osm_provenance() -> Optional[dict]:
    if not OSM_PROVENANCE_PATH.exists():
        return None
    try:
        return json.loads(OSM_PROVENANCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
