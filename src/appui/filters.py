"""
src/appui/filters.py

Shared sidebar filter controls (source, taxonomic group, year range, grid
resolution) used by every page that shows real analysis, so filtering
behaves identically everywhere.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.config import CONFIG
from src.processing.taxonomy import assign_major_group


def sidebar_filters(df: pd.DataFrame, include_grid_size: bool = True) -> tuple[pd.DataFrame, float]:
    st.sidebar.markdown("### Filters")

    sources = sorted(df["source"].dropna().unique().tolist())
    selected_sources = st.sidebar.multiselect("Source", sources, default=sources)

    working = df.copy()
    working["major_group"] = assign_major_group(working["kingdom"], working["taxon_class"])
    groups = sorted(working["major_group"].dropna().unique().tolist())
    selected_groups = st.sidebar.multiselect("Taxonomic group", groups, default=groups)

    years = working["year"].dropna()
    if not years.empty:
        y_min, y_max = int(years.min()), int(years.max())
        if y_min == y_max:
            st.sidebar.caption(f"All records are from {y_min}.")
            year_range = (y_min, y_max)
        else:
            year_range = st.sidebar.slider("Year range", min_value=y_min, max_value=y_max,
                                            value=(y_min, y_max))
    else:
        year_range = None

    grid_size = CONFIG.spatial_default_grid_size_deg
    if include_grid_size:
        grid_size = st.sidebar.select_slider(
            "Spatial grid resolution (degrees)",
            options=[0.01, 0.02, 0.05, 0.1, 0.2, 0.5],
            value=CONFIG.spatial_default_grid_size_deg,
            help="~0.01deg ≈ 1.1km, ~0.05deg ≈ 5.5km, ~0.1deg ≈ 11km at this latitude "
                 "(rough planar approximation, for grid sizing only).",
        )

    filtered = working[working["source"].isin(selected_sources) & working["major_group"].isin(selected_groups)]
    if year_range is not None:
        filtered = filtered[filtered["year"].between(year_range[0], year_range[1]) | filtered["year"].isna()]

    st.sidebar.caption(f"{len(filtered):,} of {len(df):,} records match current filters.")
    return filtered, grid_size
