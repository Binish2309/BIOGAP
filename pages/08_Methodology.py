import streamlit as st

st.set_page_config(page_title="BIOGAP -- Methodology", page_icon="\U0001F4D0", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, label
from src.config import CONFIG
from src.analysis.gap_metrics import list_components
from src.utils.data_status import get_run_summary

inject_theme()
topbar("Methodology")
hero("Methodology", "What's implemented, what's proposed, and what's not yet validated.")

st.info(
    "Can we systematically identify and quantify where biodiversity recording effort is too "
    "sparse, uneven, or narrow to support reliable inference \u2014 using only real, traceable "
    "data and previously-validated methods, not an invented scoring formula?"
)

tab_data, tab_method, tab_metric, tab_status = st.tabs(
    ["Data & sources", "Analysis methods", "Gap Score components", "Live pipeline status"]
)

with tab_data:
    st.markdown(
        "- **GBIF** \u2014 real REST API v1 via `pygbif`. " + label("IMPLEMENTED", "IMPLEMENTED") + "\n"
        "- **iNaturalist** \u2014 real REST API v1, bounding-box query. " + label("IMPLEMENTED", "IMPLEMENTED"),
        unsafe_allow_html=True,
    )
    st.caption(
        "eBird was deliberately not included \u2014 its public API only offers recent "
        "(\u226430-day), radius-based observations rather than the historical, "
        "bounding-box data GBIF/iNaturalist provide, and needs a separately-requested "
        "key. See RESEARCH_METHOD.md."
    )
    st.markdown(
        "- **OpenStreetMap roads/paths** (contextual, not a biodiversity source) \u2014 real "
        "Overpass API query, used as an accessibility proxy on the Blind Spot Evidence page. "
        + label("IMPLEMENTED", "IMPLEMENTED") + " \u2014 counts geometry vertices per grid cell "
        "as a density proxy, NOT true road length. Population density (e.g. WorldPop) remains "
        + label("NOT IMPLEMENTED", "NOT_IMPLEMENTED") + " -- would require raster processing "
        "and large downloads out of scope for the current Streamlit Cloud deployment.",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"**Study area**: hand-built bounding box (lat {CONFIG.bbox.min_lat}\u2013{CONFIG.bbox.max_lat}, "
        f"lon {CONFIG.bbox.min_lon}\u2013{CONFIG.bbox.max_lon}) " + label("FEASIBILITY-ONLY", "PROPOSED")
        + " \u2014 swapping in an official MMR polygon needs only a config change, "
        + label("NOT YET DONE", "NOT_IMPLEMENTED") + ".",
        unsafe_allow_html=True,
    )
    st.markdown(
        "**Cleaning**: whitespace/empty-string normalisation, implausible-year nulling, "
        "invalid-coordinate flagging (never silent removal), missing-value indicators, "
        "same-source duplicate removal. " + label("IMPLEMENTED", "IMPLEMENTED"),
        unsafe_allow_html=True,
    )

with tab_method:
    st.markdown(
        "- Spatial density, grid coverage, Nearest Neighbour Index \u2014 " + label("IMPLEMENTED", "IMPLEMENTED") + "\n"
        "- Taxonomic representation, Pielou's evenness \u2014 " + label("IMPLEMENTED", "IMPLEMENTED") + "\n"
        "- Temporal coverage, coefficient of variation \u2014 " + label("IMPLEMENTED", "IMPLEMENTED") + "\n"
        "- Cross-platform normalised comparison \u2014 " + label("IMPLEMENTED", "IMPLEMENTED") + "\n"
        "- Accessibility-vs-density correlation and 4-category blind-spot classification "
        "(Spearman correlation, quantile-based classification against road-vertex density) \u2014 "
        + label("IMPLEMENTED", "IMPLEMENTED") + " \u2014 see the Blind Spot Evidence page.\n"
        "- Species-accumulation-curve completeness estimate (KnowBR/Hortal et al. slope method) "
        "\u2014 " + label("IMPLEMENTED", "IMPLEMENTED") + ", method-standard but "
        + label("NOT YET VALIDATED for this region", "NOT_YET_VALIDATED") + " against a "
        "known-complete reference area.",
        unsafe_allow_html=True,
    )
    st.markdown(
        "**Observation effort**: fields exist in the schema but are populated only where a "
        "source provides them \u2014 currently empty for both sources as implemented. "
        + label("PROPOSED (not yet available from GBIF/iNaturalist)", "PROPOSED"),
        unsafe_allow_html=True,
    )

with tab_metric:
    st.dataframe(list_components(), width='stretch', hide_index=True)
    st.caption(
        "No final composite Gap Score exists yet. NOT_IMPLEMENTED components raise an error "
        "rather than return a guessed number."
    )
    st.error(
        "No metric here has been validated against ground truth. \u201cIMPLEMENTED_DESCRIPTIVE\u201d "
        "means correctly computed from real data with a cited formula \u2014 not shown to predict "
        "true biodiversity completeness."
    )

with tab_status:
    summary = get_run_summary()
    if summary is None:
        st.caption("No pipeline run has been executed yet.")
    else:
        for source, prov in summary["provenance_by_source"].items():
            st.markdown(f"**{source}**: {prov.get('status')} \u2014 {prov.get('records_retained', 0):,} retained")
