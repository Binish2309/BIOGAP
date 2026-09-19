"""
src/analysis/spatial.py

Spatial analysis functions. Grid resolution is a required, explicit
parameter everywhere (per project rules: "make spatial resolution
configurable rather than permanently choosing a grid size") -- there is no
hard-coded default grid size baked into the analysis functions themselves;
the UI-facing default lives in src/config.py (CONFIG.spatial_default_grid_size_deg)
and is passed in explicitly.

Terminology: functions here report "observation density" / "recording
concentration" / "grid coverage". None of them use the word "biodiversity"
or "abundance" -- see RESEARCH_METHOD.md for why.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.processing.validation import assert_no_test_data_in_research_path


def assign_grid_cell(df: pd.DataFrame, grid_size_deg: float,
                      lat_col: str = "latitude", lon_col: str = "longitude") -> pd.Series:
    """
    Assign each record to a rectangular grid cell of size grid_size_deg
    (degrees) x grid_size_deg (degrees), identified by its lower-left
    corner as a "lat,lon" string. Records with missing coordinates get
    <NA> and are excluded from grid-based analysis (not silently zeroed).
    """
    assert_no_test_data_in_research_path(df, caller="spatial.assign_grid_cell")
    if grid_size_deg <= 0:
        raise ValueError("grid_size_deg must be > 0")

    lat, lon = df[lat_col], df[lon_col]
    valid = lat.notna() & lon.notna()
    cell_lat = (np.floor(lat / grid_size_deg) * grid_size_deg).round(6)
    cell_lon = (np.floor(lon / grid_size_deg) * grid_size_deg).round(6)
    cell_id = cell_lat.astype(str) + "," + cell_lon.astype(str)
    cell_id = cell_id.where(valid, other=pd.NA)
    return cell_id


def observation_density_by_cell(df: pd.DataFrame, grid_size_deg: float) -> pd.DataFrame:
    """
    Return one row per occupied grid cell: record count, unique species
    count, and unique source count. This is a DESCRIPTIVE density measure
    of what's IN THE DATASET -- explicitly not a biodiversity estimate.
    """
    assert_no_test_data_in_research_path(df, caller="spatial.observation_density_by_cell")
    working = df.copy()
    working["_grid_cell"] = assign_grid_cell(working, grid_size_deg)
    working = working[working["_grid_cell"].notna()]

    if working.empty:
        return pd.DataFrame(columns=["grid_cell", "record_count", "unique_species", "unique_sources"])

    grouped = working.groupby("_grid_cell").agg(
        record_count=("record_id", "count"),
        unique_species=("scientific_name", lambda s: s.dropna().nunique()),
        unique_sources=("source", lambda s: s.dropna().nunique()),
    ).reset_index().rename(columns={"_grid_cell": "grid_cell"})
    return grouped


def coverage_summary(df: pd.DataFrame, grid_size_deg: float) -> dict:
    """
    Summary of how much of the records' own bounding extent is actually
    "occupied" by at least one record, at the given grid resolution. This
    describes RECORD COVERAGE, not habitat suitability or biodiversity
    presence/absence.
    """
    assert_no_test_data_in_research_path(df, caller="spatial.coverage_summary")
    valid = df[df["latitude"].notna() & df["longitude"].notna()]
    if valid.empty:
        return {"n_occupied_cells": 0, "n_records_with_coordinates": 0,
                "lat_extent": None, "lon_extent": None}

    density = observation_density_by_cell(valid, grid_size_deg)
    return {
        "n_occupied_cells": int(len(density)),
        "n_records_with_coordinates": int(len(valid)),
        "lat_extent": [float(valid["latitude"].min()), float(valid["latitude"].max())],
        "lon_extent": [float(valid["longitude"].min()), float(valid["longitude"].max())],
        "grid_size_deg": grid_size_deg,
        "records_per_occupied_cell_mean": float(density["record_count"].mean()) if len(density) else None,
        "records_per_occupied_cell_median": float(density["record_count"].median()) if len(density) else None,
    }


def nearest_neighbor_index(df: pd.DataFrame, lat_col: str = "latitude",
                            lon_col: str = "longitude") -> dict | None:
    """
    Compute a Nearest Neighbour Index (NNI) for point clustering, following
    the standard approach used in the biodiversity-bias literature (e.g.
    the Sardinia GBIF bias study cited in the BIOGAP Stage 1 report):
    NNI = mean observed nearest-neighbour distance / mean expected nearest-
    neighbour distance under complete spatial randomness (CSR) for the same
    point density and study-area extent.

    NNI < 1 indicates clustering; NNI > 1 indicates dispersion; NNI ~= 1 is
    consistent with randomness. Coordinates are treated as planar (degrees
    treated as a flat plane) which is a standard, documented simplification
    for a study area this small and this close to the equator -- it is NOT
    appropriate for continental-scale analysis.

    Returns None if fewer than 3 valid points are available (NNI is not
    meaningful below that).
    """
    assert_no_test_data_in_research_path(df, caller="spatial.nearest_neighbor_index")
    from scipy.spatial import cKDTree  # local import: scipy is an optional-until-needed dependency

    valid = df[df[lat_col].notna() & df[lon_col].notna()]
    points = valid[[lat_col, lon_col]].to_numpy()
    n = len(points)
    if n < 3:
        return None

    tree = cKDTree(points)
    dists, _ = tree.query(points, k=2)  # k=2: nearest neighbour excluding self
    nearest_dists = dists[:, 1]
    mean_observed = float(np.mean(nearest_dists))

    lat_range = points[:, 0].max() - points[:, 0].min()
    lon_range = points[:, 1].max() - points[:, 1].min()
    area = lat_range * lon_range
    if area <= 0:
        return None
    density = n / area
    mean_expected = 0.5 / np.sqrt(density)

    nni = mean_observed / mean_expected if mean_expected > 0 else None
    return {
        "n_points": n,
        "mean_observed_nn_distance_deg": mean_observed,
        "mean_expected_nn_distance_deg_under_CSR": float(mean_expected),
        "nni": float(nni) if nni is not None else None,
        "interpretation": (
            "NNI < 1: clustered; NNI > 1: dispersed; NNI ~= 1: consistent with random. "
            "Units are decimal degrees (planar approximation) -- comparable only within "
            "this dataset/run, not to studies using projected metric distances."
        ),
    }
