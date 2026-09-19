"""
src/visualization/maps.py

Folium-based map builders. Kept deliberately simple (Folium over
PyDeck) since Folium's dependency footprint is lighter and it renders
well inside Streamlit via streamlit-folium, consistent with the
"simplest reliable stack" principle.
"""

from __future__ import annotations

import folium
import pandas as pd
from folium.plugins import MarkerCluster, HeatMap

from src.config import BoundingBox

# A restrained, "scientific/nature" palette rather than default Folium
# bright primaries -- used consistently across all maps in the app.
SOURCE_COLORS = {
    "GBIF": "#2E5339",       # deep forest green
    "iNaturalist": "#74A57F",  # sage green
}
DEFAULT_COLOR = "#8C7A6B"


def _base_map(bbox: BoundingBox, tiles: str = "OpenStreetMap") -> folium.Map:
    center = bbox.center()
    m = folium.Map(location=center, zoom_start=10, tiles=tiles, control_scale=True)
    folium.Rectangle(
        bounds=[(bbox.min_lat, bbox.min_lon), (bbox.max_lat, bbox.max_lon)],
        color="#B0413E", weight=1.5, fill=False, dash_array="6,6",
        tooltip="Feasibility bounding box (NOT an official MMR boundary)" if not bbox.is_official_polygon else "MMR boundary",
    ).add_to(m)
    return m


def build_point_map(df: pd.DataFrame, bbox: BoundingBox, max_points: int = 5000) -> folium.Map:
    """
    Cluster-marker map of individual observations, coloured by source.
    Silently caps the number of plotted points (does not drop them from
    the underlying data, only from this one map render) to keep the map
    responsive; the cap and true count are shown by the caller in the UI.
    """
    m = _base_map(bbox)
    valid = df[df["latitude"].notna() & df["longitude"].notna()]
    if valid.empty:
        return m

    plotted = valid.sample(n=min(max_points, len(valid)), random_state=42) if len(valid) > max_points else valid
    cluster = MarkerCluster().add_to(m)
    for _, row in plotted.iterrows():
        color = SOURCE_COLORS.get(row.get("source"), DEFAULT_COLOR)
        popup = folium.Popup(
            html=(
                f"<b>{row.get('scientific_name') or 'Unidentified'}</b><br>"
                f"Source: {row.get('source')}<br>"
                f"Year: {row.get('year') if pd.notna(row.get('year')) else 'unknown'}<br>"
                f"Record ID: {row.get('record_id')}"
            ),
            max_width=250,
        )
        folium.CircleMarker(
            location=(row["latitude"], row["longitude"]),
            radius=4, color=color, fill=True, fill_color=color, fill_opacity=0.8,
            popup=popup,
        ).add_to(cluster)
    return m


def build_density_heatmap(df: pd.DataFrame, bbox: BoundingBox) -> folium.Map:
    """Observation-density heatmap -- explicitly a density-of-RECORDS
    layer, labelled as such wherever it's shown in the UI."""
    m = _base_map(bbox)
    valid = df[df["latitude"].notna() & df["longitude"].notna()]
    if valid.empty:
        return m
    HeatMap(
        data=valid[["latitude", "longitude"]].values.tolist(),
        radius=12, blur=18, max_zoom=13,
    ).add_to(m)
    return m


def build_grid_coverage_map(grid_density_df: pd.DataFrame, bbox: BoundingBox,
                             grid_size_deg: float) -> folium.Map:
    """
    Draw one rectangle per occupied grid cell, shaded by record count.
    grid_density_df must have columns: grid_cell ("lat,lon" of lower-left
    corner), record_count.
    """
    m = _base_map(bbox)
    if grid_density_df.empty:
        return m

    max_count = grid_density_df["record_count"].max()
    for _, row in grid_density_df.iterrows():
        lat_str, lon_str = row["grid_cell"].split(",")
        lat0, lon0 = float(lat_str), float(lon_str)
        intensity = row["record_count"] / max_count if max_count else 0
        # Nature-inspired sequential scale: pale sand -> deep forest green
        color = _sequential_color(intensity)
        folium.Rectangle(
            bounds=[(lat0, lon0), (lat0 + grid_size_deg, lon0 + grid_size_deg)],
            color=color, weight=0.5, fill=True, fill_color=color, fill_opacity=0.65,
            tooltip=f"{int(row['record_count'])} records, {int(row.get('unique_species', 0))} species",
        ).add_to(m)
    return m


def build_blind_spot_map(grid_df: pd.DataFrame, bbox: BoundingBox,
                          grid_size_deg: float) -> folium.Map:
    """
    Draw one rectangle per grid cell (the FULL grid, including empty
    cells), coloured by blind-spot evidence category. grid_df comes from
    src.analysis.blind_spot_evidence.observation_vs_accessibility()'s
    "grid" result -- columns: grid_cell, record_count, road_vertex_count,
    category.
    """
    from src.analysis.blind_spot_evidence import (
        CATEGORY_LIKELY_GAP, CATEGORY_AMBIGUOUS, CATEGORY_WELL_SAMPLED,
        CATEGORY_RECORDED_DESPITE_LOW_ACCESS,
    )
    category_colors = {
        CATEGORY_LIKELY_GAP: "#B0413E",                    # rust -- draws the eye, the key finding
        CATEGORY_AMBIGUOUS: "#B7AFA1",                      # neutral grey-sand
        CATEGORY_WELL_SAMPLED: "#2E5339",                   # deep forest
        CATEGORY_RECORDED_DESPITE_LOW_ACCESS: "#3E5C76",    # slate blue
        "MIDDLE_RANGE": "#E5DFD3",                           # pale, recedes visually
    }
    m = _base_map(bbox)
    if grid_df is None or grid_df.empty:
        return m

    for _, row in grid_df.iterrows():
        lat_str, lon_str = row["grid_cell"].split(",")
        lat0, lon0 = float(lat_str), float(lon_str)
        color = category_colors.get(row["category"], "#CCCCCC")
        opacity = 0.75 if row["category"] not in ("MIDDLE_RANGE",) else 0.25
        folium.Rectangle(
            bounds=[(lat0, lon0), (lat0 + grid_size_deg, lon0 + grid_size_deg)],
            color=color, weight=0.4, fill=True, fill_color=color, fill_opacity=opacity,
            tooltip=(f"{row['category'].replace('_', ' ').title()} \u2014 "
                     f"{int(row['record_count'])} records, {int(row['road_vertex_count'])} road vertices"),
        ).add_to(m)
    return m


def _sequential_color(intensity: float) -> str:
    """Interpolate between pale sand (#F2E9DC) and deep forest (#1F3A2E)."""
    intensity = max(0.0, min(1.0, intensity))
    c0 = (0xF2, 0xE9, 0xDC)
    c1 = (0x1F, 0x3A, 0x2E)
    rgb = tuple(int(c0[i] + (c1[i] - c0[i]) * intensity) for i in range(3))
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
