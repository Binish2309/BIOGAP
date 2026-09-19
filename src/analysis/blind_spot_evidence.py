"""
src/analysis/blind_spot_evidence.py

The core "is this a recording gap or a real biodiversity gap" analysis.
Everything here operates on REAL, already-ingested data (biodiversity
records from src.pipeline + road geometry from
src.ingestion.osm_context) -- nothing here invents a number, and every
function that needs both datasets returns an explicit, honest "not enough
data" result rather than guessing when one is missing.

METHODOLOGY, STATED PLAINLY
-----------------------------
The literature (Tiago et al. 2017 and others cited in RESEARCH_METHOD.md)
finds that road/path accessibility is the strongest single predictor of
WHERE citizen-science recording effort concentrates -- stronger than the
underlying biology. This module tests that relationship directly against
THIS dataset for THIS study area:

1. Build a full grid covering the study area (not just occupied cells --
   the whole point is to see cells with ZERO records too).
2. For each cell, compute a real observation-record count and a real
   road-vertex count (the accessibility proxy -- see
   src/ingestion/osm_context.py for exactly what this proxy is and is not).
3. Compute the actual Spearman correlation between the two across all
   cells (scipy.stats.spearmanr) -- a real statistical test, not an
   assumption. A meaningful positive correlation is itself evidence that
   THIS dataset is accessibility-biased in the way the literature predicts.
4. Classify each cell into one of four evidence categories based on where
   it falls relative to the OTHER cells in the SAME dataset (quantile
   thresholds, not absolute/arbitrary numbers):
     - LIKELY_RECORDING_GAP: low observation density, high accessibility
       -- people could plausibly have recorded here and didn't.
     - AMBIGUOUS_LOW_ACCESS: low observation density, low accessibility
       -- could be a real gap, could be genuinely hard to reach; this
       analysis cannot distinguish the two on its own.
     - WELL_SAMPLED: high observation density, high accessibility.
     - RECORDED_DESPITE_LOW_ACCESS: high observation density, low
       accessibility -- notable; worth a closer look in its own right.

This produces EVIDENCE FOR AN ARGUMENT, not a proof. The wording used
throughout (and enforced in the Streamlit page and the research-export
report) is "evidence consistent with", never "this cell has no
biodiversity" or any claim this analysis cannot actually support.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.config import BoundingBox
from src.analysis.spatial import assign_grid_cell, observation_density_by_cell
from src.processing.validation import assert_no_test_data_in_research_path

CATEGORY_LIKELY_GAP = "LIKELY_RECORDING_GAP"
CATEGORY_AMBIGUOUS = "AMBIGUOUS_LOW_ACCESS"
CATEGORY_WELL_SAMPLED = "WELL_SAMPLED"
CATEGORY_RECORDED_DESPITE_LOW_ACCESS = "RECORDED_DESPITE_LOW_ACCESS"

CATEGORY_LABELS = {
    CATEGORY_LIKELY_GAP: "Likely recording gap \u2014 high accessibility, low recording",
    CATEGORY_AMBIGUOUS: "Ambiguous \u2014 low accessibility, low recording (cannot distinguish cause)",
    CATEGORY_WELL_SAMPLED: "Well sampled \u2014 high accessibility, high recording",
    CATEGORY_RECORDED_DESPITE_LOW_ACCESS: "Recorded despite low accessibility \u2014 notable",
}


def build_full_grid(bbox: BoundingBox, grid_size_deg: float) -> pd.DataFrame:
    """
    Every grid cell covering the bounding box, INCLUDING cells with zero
    observations and zero roads -- unlike observation_density_by_cell(),
    which only returns occupied cells. This is essential here: the whole
    point of this module is to look at cells with LOW/ZERO recording.

    Cell counts are computed via integer step counts (round((max-min)/step)),
    NOT np.arange(min, max, step) -- np.arange with float bounds is prone to
    off-by-one errors at the boundary due to floating-point rounding (e.g.
    a bbox spanning an exact multiple of grid_size_deg can unpredictably
    include or exclude the final row/column depending on float precision).
    """
    n_lat_steps = max(1, round((bbox.max_lat - bbox.min_lat) / grid_size_deg))
    n_lon_steps = max(1, round((bbox.max_lon - bbox.min_lon) / grid_size_deg))
    cells = [
        f"{round(bbox.min_lat + i * grid_size_deg, 6)},{round(bbox.min_lon + j * grid_size_deg, 6)}"
        for i in range(n_lat_steps) for j in range(n_lon_steps)
    ]
    return pd.DataFrame({"grid_cell": cells})


def road_density_by_cell(osm_raw_df: pd.DataFrame, grid_size_deg: float) -> pd.DataFrame:
    """
    Count OSM road/path geometry VERTICES per grid cell -- the
    accessibility proxy. See src/ingestion/osm_context.py for exactly what
    this does and does not measure (vertex count, not true road length).
    """
    if osm_raw_df.empty:
        return pd.DataFrame(columns=["grid_cell", "road_vertex_count", "distinct_ways"])
    working = osm_raw_df.copy()
    working["grid_cell"] = assign_grid_cell(working, grid_size_deg)
    working = working[working["grid_cell"].notna()]
    grouped = working.groupby("grid_cell").agg(
        road_vertex_count=("way_id", "count"),
        distinct_ways=("way_id", "nunique"),
    ).reset_index()
    return grouped


def observation_vs_accessibility(df: pd.DataFrame, osm_raw_df: pd.DataFrame,
                                  bbox: BoundingBox, grid_size_deg: float,
                                  low_quantile: float = 0.3,
                                  high_quantile: float = 0.7) -> dict:
    """
    The main analysis. Returns a dict with:
      - status: "OK" or "INSUFFICIENT_DATA" (never fabricates a result)
      - grid: the full per-cell DataFrame (grid_cell, record_count,
        road_vertex_count, category)
      - correlation: {"spearman_r": float, "p_value": float, "n_cells": int}
        or None if not computable
      - category_counts: dict of category -> cell count
      - thresholds_used: the actual quantile cutoffs applied, for
        transparency in any report/figure built from this
    """
    assert_no_test_data_in_research_path(df, caller="blind_spot_evidence.observation_vs_accessibility")

    if osm_raw_df is None or osm_raw_df.empty:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "No road/path context data has been ingested yet. Run the OSM ingestion "
                      "on this page before this analysis can run.",
            "grid": None, "correlation": None, "category_counts": {}, "thresholds_used": None,
        }
    if df is None or df.empty:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "No biodiversity observation data has been ingested yet.",
            "grid": None, "correlation": None, "category_counts": {}, "thresholds_used": None,
        }

    full_grid = build_full_grid(bbox, grid_size_deg)
    obs_density = observation_density_by_cell(df, grid_size_deg)
    road_density = road_density_by_cell(osm_raw_df, grid_size_deg)

    grid = full_grid.merge(obs_density[["grid_cell", "record_count"]], on="grid_cell", how="left")
    grid = grid.merge(road_density[["grid_cell", "road_vertex_count"]], on="grid_cell", how="left")
    grid["record_count"] = grid["record_count"].fillna(0).astype(int)
    grid["road_vertex_count"] = grid["road_vertex_count"].fillna(0).astype(int)

    if len(grid) < 8:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": f"Only {len(grid)} grid cells at this resolution -- too few for a "
                      "meaningful quantile split or correlation. Try a smaller grid size.",
            "grid": grid, "correlation": None, "category_counts": {}, "thresholds_used": None,
        }

    obs_low_cut = grid["record_count"].quantile(low_quantile)
    obs_high_cut = grid["record_count"].quantile(high_quantile)
    road_low_cut = grid["road_vertex_count"].quantile(low_quantile)
    road_high_cut = grid["road_vertex_count"].quantile(high_quantile)

    def _classify(row) -> str:
        low_obs = row["record_count"] <= obs_low_cut
        high_obs = row["record_count"] >= obs_high_cut
        low_road = row["road_vertex_count"] <= road_low_cut
        high_road = row["road_vertex_count"] >= road_high_cut
        if low_obs and high_road:
            return CATEGORY_LIKELY_GAP
        if low_obs and low_road:
            return CATEGORY_AMBIGUOUS
        if high_obs and high_road:
            return CATEGORY_WELL_SAMPLED
        if high_obs and low_road:
            return CATEGORY_RECORDED_DESPITE_LOW_ACCESS
        return "MIDDLE_RANGE"  # neither extreme on one or both axes -- not classified either way

    grid["category"] = grid.apply(_classify, axis=1)

    correlation = None
    if grid["road_vertex_count"].std() > 0 and grid["record_count"].std() > 0:
        from scipy.stats import spearmanr
        r, p = spearmanr(grid["road_vertex_count"], grid["record_count"])
        correlation = {"spearman_r": float(r), "p_value": float(p), "n_cells": int(len(grid))}

    category_counts = grid["category"].value_counts().to_dict()

    return {
        "status": "OK",
        "grid": grid,
        "correlation": correlation,
        "category_counts": {str(k): int(v) for k, v in category_counts.items()},
        "thresholds_used": {
            "low_quantile": low_quantile, "high_quantile": high_quantile,
            "obs_low_cut": float(obs_low_cut), "obs_high_cut": float(obs_high_cut),
            "road_low_cut": float(road_low_cut), "road_high_cut": float(road_high_cut),
        },
    }


def cross_platform_disagreement_by_cell(df: pd.DataFrame, grid_size_deg: float) -> pd.DataFrame:
    """
    For each occupied grid cell, which sources recorded there. A cell
    where one platform has many records and another has none is
    corroborating (not conclusive) evidence of platform-specific bias
    rather than a genuine absence -- if the area were truly unvisited by
    anyone, BOTH platforms would be empty there.
    """
    assert_no_test_data_in_research_path(df, caller="blind_spot_evidence.cross_platform_disagreement_by_cell")
    working = df.copy()
    working["grid_cell"] = assign_grid_cell(working, grid_size_deg)
    working = working[working["grid_cell"].notna()]
    if working.empty:
        return pd.DataFrame(columns=["grid_cell", "sources_present", "n_sources", "is_single_platform_only"])

    grouped = working.groupby("grid_cell")["source"].apply(lambda s: sorted(s.dropna().unique())).reset_index()
    grouped.columns = ["grid_cell", "sources_present"]
    grouped["n_sources"] = grouped["sources_present"].apply(len)
    grouped["is_single_platform_only"] = grouped["n_sources"] == 1
    return grouped
