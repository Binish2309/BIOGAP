import streamlit as st

st.set_page_config(page_title="BIOGAP -- Research Export", page_icon="\U0001F4C4", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note
from src.appui.gate import require_real_data
from src.utils.data_status import get_run_summary, load_osm_context_data
from src.analysis.research_export import build_report_data, render_markdown_report

inject_theme()
topbar("Research Export")
hero("Research export", "A methods-and-results summary generated live from your real dataset.")

df = require_real_data()
if df is None:
    st.stop()

st.caption(
    "Every number below is computed directly from the currently-ingested real dataset. "
    "Nothing here is a template filled with placeholder figures."
)

osm_df = load_osm_context_data()
if osm_df is None:
    note("Blind-spot accessibility evidence is not included below \u2014 fetch road/path data on "
         "the Blind Spot Evidence page first if you want that section in this report.")

grid_size = st.select_slider(
    "Spatial grid resolution used for this report",
    options=[0.01, 0.02, 0.05, 0.1, 0.2, 0.5], value=0.05,
)

run_summary = get_run_summary()
data = build_report_data(df, run_summary, grid_size_deg=grid_size, osm_df=osm_df)
report_md = render_markdown_report(data)

st.markdown("### Preview")
with st.container(border=True):
    st.markdown(report_md)

st.markdown("### Download")
c1, c2, c3 = st.columns(3)
with c1:
    st.download_button(
        "Download full report (.md)", data=report_md,
        file_name="biogap_research_summary.md", mime="text/markdown",
        type="primary", width='stretch',
    )
with c2:
    st.download_button(
        "Download taxonomic table (.csv)",
        data=data["taxonomic_representation"].to_csv(index=False),
        file_name="biogap_taxonomic_representation.csv", mime="text/csv",
        width='stretch',
    )
with c3:
    st.download_button(
        "Download yearly coverage (.csv)",
        data=data["yearly_coverage"].to_csv(index=False),
        file_name="biogap_yearly_coverage.csv", mime="text/csv",
        width='stretch',
    )

note("Charts on other pages have their own download icon (top-right of each chart) for figure-quality PNG export.")
