import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="BIOGAP -- Explore Map", page_icon="\U0001F5FA", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note
from src.appui.gate import require_real_data
from src.appui.filters import sidebar_filters
from src.config import CONFIG
from src.visualization.maps import build_point_map, build_density_heatmap, build_grid_coverage_map
from src.analysis.spatial import observation_density_by_cell

inject_theme()
topbar("Explore Map")
hero("Explore the map", "Every recorded observation in the current filter selection.")

df = require_real_data()
if df is None:
    st.stop()

filtered, grid_size = sidebar_filters(df)

layer = st.radio("Map layer", ["Individual observations", "Density heatmap", "Grid coverage"], horizontal=True)

if filtered.empty:
    st.info("No records match the current filters.")
else:
    if layer == "Individual observations":
        n_valid = int((filtered["latitude"].notna() & filtered["longitude"].notna()).sum())
        st.caption(f"Plotting up to 5,000 of {n_valid:,} georeferenced records matching the current filters.")
        m = build_point_map(filtered, CONFIG.bbox)
    elif layer == "Density heatmap":
        m = build_density_heatmap(filtered, CONFIG.bbox)
    else:
        grid_df = observation_density_by_cell(filtered, grid_size)
        st.caption(f"{len(grid_df):,} occupied grid cells at {grid_size}\u00b0 resolution.")
        m = build_grid_coverage_map(grid_df, CONFIG.bbox, grid_size)

    st_folium(m, width=None, height=600, returned_objects=[])

note("Dashed rectangle = current study-area bounding box (feasibility approximation, not an official MMR boundary).")
