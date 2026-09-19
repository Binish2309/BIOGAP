import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="BIOGAP -- Spatial Gaps", page_icon="\U0001F30D", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note, detail
from src.appui.gate import require_real_data
from src.appui.filters import sidebar_filters
from src.config import CONFIG
from src.analysis.spatial import observation_density_by_cell, coverage_summary, nearest_neighbor_index
from src.visualization.maps import build_grid_coverage_map

inject_theme()
topbar("Spatial Gaps")
hero("Spatial observation gaps", "Where are recorded observations concentrated or sparse?")

df = require_real_data()
if df is None:
    st.stop()

filtered, grid_size = sidebar_filters(df)

if filtered.empty:
    st.info("No records match the current filters.")
    st.stop()

summary = coverage_summary(filtered, grid_size)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Occupied grid cells", f"{summary['n_occupied_cells']:,}")
c2.metric("Georeferenced records", f"{summary['n_records_with_coordinates']:,}")
c3.metric("Median records / cell", f"{summary.get('records_per_occupied_cell_median') or 0:.1f}")
c4.metric("Grid resolution", f"{grid_size}\u00b0")

grid_df = observation_density_by_cell(filtered, grid_size)
m = build_grid_coverage_map(grid_df, CONFIG.bbox, grid_size)
st_folium(m, width=None, height=550, returned_objects=[])

st.markdown("### Point-pattern clustering")
nni = nearest_neighbor_index(filtered)
if nni is None:
    st.caption("Need at least 3 georeferenced records to compute clustering.")
else:
    c1, c2 = st.columns(2)
    c1.metric("Nearest Neighbour Index", f"{nni['nni']:.2f}" if nni["nni"] is not None else "n/a")
    c2.metric("Points analysed", f"{nni['n_points']:,}")
    st.caption("Below 1 = clustered \u00b7 above 1 = dispersed \u00b7 around 1 = random. Describes record clustering, not organisms.")

note("This page shows observation density and coverage only \u2014 not a final Gap Score. See Methodology.")
