"""
src/appui/overview.py

Shared render function for the Overview / landing content, called by both
app.py and pages/01_Overview.py so the two entry points cannot drift out
of sync.

Staged ingestion (GBIF primary + optional iNaturalist tab), live
progress via st.status(), and persistence to disk so status survives page
switches -- unchanged from the working version. This revision focuses on
DISPLAY: shorter always-visible copy, detail moved into collapsed
expanders (src.visualization.theme.detail/note), and provenance shown as
formatted key/value rows instead of raw Python dict text.
"""

from __future__ import annotations

import streamlit as st

from src.config import CONFIG
from src.visualization.theme import inject_theme, hero, status_pill, note, detail
from src.utils.data_status import get_run_summary, load_combined_data, data_status_message, dataset_summary_stats
from src.pipeline import run_source_pipeline, DISPLAY_NAMES


def _status_kind(prov: dict) -> str:
    if prov.get("status") == "SUCCESS" and prov.get("records_retained", 0) > 0:
        return "ok"
    if prov.get("status") == "UNTESTED":
        return "pending"
    if prov.get("status") == "SUCCESS" and prov.get("records_retained", 0) == 0:
        return "pending"
    return "failed"


def _kv_rows(d: dict | None) -> str:
    """Render a dict as clean 'key: value' markdown lines instead of a raw
    Python dict repr -- avoids dumping code-looking text on the page."""
    if not d:
        return "_none_"
    lines = []
    for k, v in d.items():
        if isinstance(v, dict):
            inner = ", ".join(f"{ik}: {iv}" for ik, iv in v.items())
            lines.append(f"- **{k}**: {inner}")
        else:
            lines.append(f"- **{k}**: {v}")
    return "\n".join(lines)


def _render_source_row(display_name: str, prov: dict) -> None:
    kind = _status_kind(prov)
    st.markdown(f"**{display_name}**")
    status_pill(f"{prov.get('status')} \u2014 {prov.get('records_retrieved', 0):,} retrieved, "
                f"{prov.get('records_retained', 0):,} retained", kind=kind)
    if prov.get("error_detail"):
        st.error(prov["error_detail"])
    if prov.get("extra_notes"):
        st.caption(prov["extra_notes"])
    with st.expander("Query details"):
        st.caption(f"Accessed: {prov.get('access_datetime_utc', 'n/a')}")
        st.caption(f"Endpoint: {prov.get('source_url_or_api', 'n/a')}")
        st.markdown(_kv_rows(prov.get("query_parameters")))
        st.markdown(_kv_rows(prov.get("geographic_filter")))


def _run_staged_ingestion(source_key: str, **ingestion_kwargs) -> None:
    display_name = DISPLAY_NAMES[source_key]
    with st.status(f"Running {display_name} ingestion...", expanded=True) as status_box:
        def on_progress(message: str) -> None:
            status_box.write(message)

        result = run_source_pipeline(source_key, on_progress=on_progress, **ingestion_kwargs)
        prov = result["provenance_by_source"].get(display_name, {})
        if prov.get("status") == "SUCCESS":
            status_box.update(label=f"{display_name} ingestion complete.", state="complete")
        elif prov.get("status") == "UNTESTED":
            status_box.update(label=f"{display_name} not run (see below).", state="complete")
        else:
            status_box.update(label=f"{display_name} ingestion failed.", state="error")

    _render_source_row(display_name, prov)
    overall = "Real data available" if result["data_status"] == "REAL_DATA_AVAILABLE" else "No real data yet"
    st.caption(f"**{overall}** \u2014 {result['combined_row_count']:,} records combined from "
               f"{', '.join(result['sources_in_combined_dataset']) or 'no sources yet'}.")


def render() -> None:
    inject_theme()
    hero(
        "Where don't we know enough about biodiversity?",
        "Mapping the geographic, taxonomic, and temporal blind spots in biodiversity "
        "data for the Mumbai Metropolitan Region.",
    )

    st.write(
        "Biodiversity databases reflect where people happened to look, not where "
        "organisms actually are. BIOGAP finds and measures those recording gaps -- "
        "it does not claim to measure biodiversity itself."
    )
    detail("Research question & approach", (
        "Given publicly accessible biodiversity occurrence data for the Mumbai "
        "Metropolitan Region, can we systematically identify and quantify where "
        "recording effort is too sparse, too uneven, or too narrowly distributed to "
        "support reliable inference about biodiversity patterns -- using only real, "
        "traceable, open data and previously-validated methods, rather than an "
        "invented and unvalidated scoring formula?"
    ))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Data sources**")
        st.caption("GBIF \u00b7 iNaturalist")
    with col2:
        st.markdown("**Study area**")
        bbox = CONFIG.bbox
        st.caption(f"Lat {bbox.min_lat}\u2013{bbox.max_lat}, Lon {bbox.min_lon}\u2013{bbox.max_lon}"
                   + ("" if bbox.is_official_polygon else " (feasibility box)"))
    with col3:
        st.markdown("**Method**")
        st.caption("Spatial \u00b7 Taxonomic \u00b7 Temporal \u00b7 Cross-platform")

    st.markdown("### Data status")
    summary = get_run_summary()
    df = load_combined_data()

    if df is not None:
        status_pill(f"Real data available \u2014 {len(df):,} records", kind="ok")
        stats = dataset_summary_stats(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Records", f"{stats['n_records']:,}")
        c2.metric("Species (named)", f"{stats['n_species']:,}" if stats["n_species"] is not None else "n/a")
        c3.metric("Date coverage", stats["date_coverage"] or "n/a")
        c4.metric("Primary source", max(stats["records_by_source"], key=stats["records_by_source"].get)
                  if stats["records_by_source"] else "n/a")
        detail("Dataset detail", _kv_rows(stats["records_by_source"]) +
               f"\n\nLast ingestion run: {summary.get('pipeline_run_finished_utc', 'n/a') if summary else 'n/a'}")
    elif summary is not None:
        status_pill("No usable records yet", kind="failed")
        st.caption(data_status_message())
    else:
        status_pill("Awaiting real dataset", kind="pending")
        st.caption(data_status_message())

    st.markdown("### Get real data")
    tab_gbif, tab_inat = st.tabs(["GBIF", "iNaturalist"])

    with tab_gbif:
        st.caption(f"Fetches up to {CONFIG.gbif_interactive_record_limit:,} real observations "
                   "\u2014 enough on its own to unlock every page.")
        if st.button("Fetch GBIF observations", type="primary", key="btn_gbif"):
            _run_staged_ingestion("gbif")

    with tab_inat:
        st.caption(f"Optional \u2014 adds up to {CONFIG.inaturalist_interactive_record_limit:,} "
                   "observations. Never removes GBIF data already ingested.")
        if st.button("Add iNaturalist observations", key="btn_inat"):
            _run_staged_ingestion("inaturalist")

    if summary is not None:
        with st.expander("Per-source status detail"):
            for display_name, prov in summary["provenance_by_source"].items():
                _render_source_row(display_name, prov)
