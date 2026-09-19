import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

st.set_page_config(page_title="BIOGAP -- Blind Spot Evidence", page_icon="\U0001F50D", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note, detail, status_pill
from src.appui.gate import require_real_data
from src.appui.filters import sidebar_filters
from src.config import CONFIG
from src.utils.data_status import load_osm_context_data, get_osm_provenance
from src.ingestion.osm_context import run_osm_context_ingestion
from src.analysis.blind_spot_evidence import (
    observation_vs_accessibility, cross_platform_disagreement_by_cell,
    CATEGORY_LABELS, CATEGORY_LIKELY_GAP, CATEGORY_AMBIGUOUS,
    CATEGORY_WELL_SAMPLED, CATEGORY_RECORDED_DESPITE_LOW_ACCESS,
)
from src.analysis.gap_metrics import run_component
from src.visualization.maps import build_blind_spot_map

inject_theme()
topbar("Blind Spot Evidence")
hero(
    "Is this a biodiversity gap, or a recording gap?",
    "Testing whether sparse areas are genuinely under-recorded, or simply under-visited.",
)

st.write(
    "A grid cell with few observations could mean two very different things: fewer organisms "
    "there, or fewer *people who happened to record*. This page tests that directly by "
    "comparing observation density against a real accessibility proxy \u2014 road and path "
    "network presence, the single strongest predictor of recording effort found in the "
    "citizen-science bias literature (see Methodology)."
)

df = require_real_data()
if df is None:
    st.stop()

filtered, grid_size = sidebar_filters(df)
if filtered.empty:
    st.info("No records match the current filters.")
    st.stop()

# ---------------------------------------------------------------------------
# Step 1: road/path context data
# ---------------------------------------------------------------------------
st.markdown("### Step 1 \u2014 Road & path network (accessibility proxy)")
osm_df = load_osm_context_data()
osm_prov = get_osm_provenance()

if osm_df is None:
    if osm_prov is not None and osm_prov.get("status") != "SUCCESS":
        status_pill(f"Last attempt: {osm_prov.get('status')}", kind="failed")
        if osm_prov.get("error_detail"):
            st.error(osm_prov["error_detail"])
    else:
        status_pill("Not yet fetched", kind="pending")
    st.caption(
        "This is a single, heavier request (not paginated) -- for the full study area it can "
        "take anywhere from several seconds to a couple of minutes. Fetched once and cached; "
        "you won't need to repeat this for future visits."
    )
    if st.button("Fetch road & path network data", type="primary"):
        with st.spinner("Querying OpenStreetMap (Overpass API) \u2014 this may take a minute..."):
            result = run_osm_context_ingestion(bbox=CONFIG.bbox)
        if result.status == "SUCCESS":
            st.success(f"Retrieved {result.records_retained:,} road/path features.")
            st.rerun()
        else:
            st.error(f"{result.status}: {result.error_detail}")
    st.stop()
else:
    status_pill(f"{osm_df['way_id'].nunique():,} road/path features loaded", kind="ok")
    detail("Data source detail", (
        f"Accessed: {osm_prov.get('access_datetime_utc', 'n/a') if osm_prov else 'n/a'}\n\n"
        f"{osm_prov.get('extra_notes', '') if osm_prov else ''}\n\n"
        "This measures OSM way-geometry vertex density as an accessibility proxy, "
        "not true road length per cell -- see `src/ingestion/osm_context.py`."
    ))

# ---------------------------------------------------------------------------
# Step 2: the actual evidence
# ---------------------------------------------------------------------------
st.markdown("### Step 2 \u2014 Accessibility vs. observation density")

result = observation_vs_accessibility(filtered, osm_df, CONFIG.bbox, grid_size_deg=grid_size)

if result["status"] == "INSUFFICIENT_DATA":
    st.info(result["reason"])
    st.stop()

corr = result["correlation"]
if corr is not None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Spearman correlation (r)", f"{corr['spearman_r']:.3f}")
    c2.metric("p-value", f"{corr['p_value']:.4f}")
    c3.metric("Grid cells tested", f"{corr['n_cells']:,}")
    if corr["spearman_r"] > 0.2 and corr["p_value"] < 0.05:
        st.success(
            "A meaningful positive correlation is exactly what the accessibility-bias literature "
            "predicts \u2014 this dataset's recording pattern is consistent with being driven by "
            "where people can easily go, not purely by where organisms are."
        )
    elif corr["p_value"] >= 0.05:
        st.info(
            "No statistically significant correlation was found in this filtered selection. "
            "This does not rule out accessibility bias \u2014 it may mean too few cells/records "
            "are currently available to detect it. Revisit once more data is ingested."
        )
    else:
        st.info(f"Correlation observed: r={corr['spearman_r']:.3f} (p={corr['p_value']:.4f}).")
else:
    st.caption("Correlation not computable (no variance in one or both variables for this selection).")

st.markdown("#### Cell classification")
cat_counts = result["category_counts"]
cols = st.columns(4)
for i, cat in enumerate([CATEGORY_LIKELY_GAP, CATEGORY_AMBIGUOUS, CATEGORY_WELL_SAMPLED, CATEGORY_RECORDED_DESPITE_LOW_ACCESS]):
    cols[i].metric(CATEGORY_LABELS[cat].split("\u2014")[0].strip(), cat_counts.get(cat, 0))

m = build_blind_spot_map(result["grid"], CONFIG.bbox, grid_size)
st_folium(m, width=None, height=550, returned_objects=[])
st.caption(
    "\U0001F534 Likely recording gap \u00b7 \u26AA Ambiguous (low access) \u00b7 "
    "\U0001F7E2 Well sampled \u00b7 \U0001F535 Recorded despite low access"
)

with st.expander(f"Cells flagged as likely recording gaps ({cat_counts.get(CATEGORY_LIKELY_GAP, 0)})"):
    gap_cells = result["grid"][result["grid"]["category"] == CATEGORY_LIKELY_GAP]
    st.dataframe(gap_cells[["grid_cell", "record_count", "road_vertex_count"]],
                 width='stretch', hide_index=True)
    st.caption(
        "These cells have high accessibility (top 30% of road-vertex density in this dataset) "
        "but low recording (bottom 30% of record density) \u2014 the strongest evidence pattern "
        "this analysis can produce for \u201Cpeople could have recorded here and largely didn't.\u201D"
    )

detail("Thresholds used for this classification", (
    f"Low/high quantile cutoffs: {result['thresholds_used']['low_quantile']:.0%} / "
    f"{result['thresholds_used']['high_quantile']:.0%} of this dataset's own distribution.\n\n"
    f"- Observation count \u2264 {result['thresholds_used']['obs_low_cut']:.1f} = low\n"
    f"- Observation count \u2265 {result['thresholds_used']['obs_high_cut']:.1f} = high\n"
    f"- Road vertices \u2264 {result['thresholds_used']['road_low_cut']:.1f} = low\n"
    f"- Road vertices \u2265 {result['thresholds_used']['road_high_cut']:.1f} = high\n\n"
    "These are relative to THIS dataset, not externally validated absolute thresholds."
))

# ---------------------------------------------------------------------------
# Step 3: corroborating evidence
# ---------------------------------------------------------------------------
st.markdown("### Step 3 \u2014 Corroborating evidence")

tab1, tab2 = st.tabs(["Cross-platform disagreement", "Survey completeness"])

with tab1:
    st.write(
        "If an area were genuinely unvisited, no platform would have records there. A cell "
        "where GBIF has many records but iNaturalist has none (or vice versa) is corroborating "
        "evidence of platform-specific recording bias rather than a true absence."
    )
    disagreement = cross_platform_disagreement_by_cell(filtered, grid_size_deg=grid_size)
    if disagreement.empty:
        st.caption("No occupied cells to compare.")
    else:
        single_platform_pct = disagreement["is_single_platform_only"].mean()
        st.metric("Occupied cells recorded by only one platform", f"{single_platform_pct:.0%}")
        st.dataframe(disagreement, width='stretch', hide_index=True)

with tab2:
    st.write(
        "For cells with enough records to test, does the species-accumulation curve still rise "
        "steeply (more species keep appearing) or has it flattened (further recording finds "
        "little new)? A steep curve despite a high record count suggests genuine undersampling, "
        "not just a low record count."
    )
    min_records = st.slider("Minimum records per cell to include", 5, 30, 10)
    completeness = run_component("completeness_index_knowbr_style", filtered,
                                  grid_size_deg=grid_size, min_records_per_cell=min_records)
    if completeness["n_cells_analysed"] == 0:
        st.info(f"No cells have at least {min_records} records yet \u2014 lower the threshold "
                "or ingest more data.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("Cells analysed", completeness["n_cells_analysed"])
        c2.metric("Mean completeness estimate", f"{completeness['mean_completeness_estimate']:.2f}")
        st.dataframe(completeness["per_cell_completeness"], width='stretch', hide_index=True)
    st.caption(
        "Completeness estimate near 1 = accumulation curve has flattened (little new being "
        "found). Near 0 = still climbing steeply (likely undersampled). Method-standard "
        "(KnowBR/Hortal et al.), applied here for the first time to this data \u2014 not "
        "independently validated against a known-complete reference area."
    )

note("Everything above is evidence for an argument, not proof. See Methodology for exactly what is and isn't validated.")
