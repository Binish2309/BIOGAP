import streamlit as st

st.set_page_config(page_title="BIOGAP -- Taxonomic Gaps", page_icon="\U0001F98B", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note
from src.appui.gate import require_real_data
from src.appui.filters import sidebar_filters
from src.analysis.taxonomic import group_representation, pielou_evenness, species_representation
from src.visualization.charts import taxonomic_bar_chart

inject_theme()
topbar("Taxonomic Gaps")
hero("Taxonomic observation gaps", "Which groups are over- or under-represented in the record?")

df = require_real_data()
if df is None:
    st.stop()

filtered, _ = sidebar_filters(df, include_grid_size=False)
if filtered.empty:
    st.info("No records match the current filters.")
    st.stop()

rep = group_representation(filtered)
st.plotly_chart(taxonomic_bar_chart(rep), width='stretch')

evenness = pielou_evenness(rep.set_index("major_group")["record_count"])
c1, c2 = st.columns(2)
c1.metric("Groups represented", len(rep))
c2.metric("Evenness (Pielou's J')", f"{evenness:.3f}" if evenness is not None else "n/a")

tab1, tab2 = st.tabs(["Most-recorded species", "Full breakdown"])
with tab1:
    st.dataframe(species_representation(filtered, top_n=20), width='stretch', hide_index=True)
with tab2:
    st.dataframe(rep, width='stretch', hide_index=True)

note("\u201cUnderrepresented\u201d is relative to other groups in this dataset, not a verified regional checklist.")
