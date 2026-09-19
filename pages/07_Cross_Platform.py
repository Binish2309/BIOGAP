import streamlit as st
import pandas as pd

st.set_page_config(page_title="BIOGAP -- Cross-Platform", page_icon="\U0001F500", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note
from src.appui.gate import require_real_data
from src.appui.filters import sidebar_filters
from src.analysis.cross_platform import cross_platform_summary
from src.visualization.charts import cross_platform_taxonomic_chart

inject_theme()
topbar("Cross-Platform")
hero("Cross-platform differences", "How do GBIF and iNaturalist differ in what they record?")

df = require_real_data()
if df is None:
    st.stop()

filtered, grid_size = sidebar_filters(df)
if filtered.empty:
    st.info("No records match the current filters.")
    st.stop()

sources_present = sorted(filtered["source"].dropna().unique().tolist())
if len(sources_present) < 2:
    st.info(f"Only {sources_present[0] if sources_present else 'one source'} has data in this "
            "selection. Add another source on the Overview page to compare.")
    st.stop()

summary = cross_platform_summary(filtered, grid_size)

with st.expander("Platform methodology caveats \u2014 read before interpreting the charts"):
    for source in summary["sources_present"]:
        st.markdown(f"**{source}**")
        st.write(summary["platform_structure_caveats"][source])

st.markdown("### Taxonomic composition")
st.caption("Share of each platform's own records \u2014 not raw counts.")
composition_df = pd.DataFrame(summary["taxonomic_composition"])
st.plotly_chart(cross_platform_taxonomic_chart(composition_df), width='stretch')

tab1, tab2 = st.tabs(["Temporal range", "Spatial extent"])
with tab1:
    st.dataframe(pd.DataFrame(summary["temporal_range"]), width='stretch', hide_index=True)
with tab2:
    st.dataframe(pd.DataFrame(summary["spatial_extent"]), width='stretch', hide_index=True)

note("Raw record-count totals aren't compared directly \u2014 platforms differ too much in structure and effort for that to be meaningful.")
