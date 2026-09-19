import streamlit as st

st.set_page_config(page_title="BIOGAP -- About", page_icon="\u2139\ufe0f", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar

inject_theme()
topbar("About")
hero("About BIOGAP", "Biodiversity Observation Gap Analytics Platform")

tab1, tab2, tab3 = st.tabs(["Project", "Technology", "Research integrity"])

with tab1:
    st.markdown("""
**Academic context**  
Final-year Data Science major project and research paper, working title *"Quantifying
Biodiversity Observation Blind Spots: A Data-Driven Framework for Spatial, Taxonomic and
Temporal Gaps."*

**Research purpose**  
Biodiversity databases reflect where and what people chose to record, not nature itself.
BIOGAP identifies where that recording process has left geographic, taxonomic, or temporal
blind spots for the Mumbai Metropolitan Region, using only real, publicly accessible data.
""")

with tab2:
    st.markdown("""
Python \u00b7 Streamlit \u00b7 Pandas \u00b7 NumPy \u00b7 SciPy \u00b7 Shapely \u00b7 Plotly \u00b7 Folium.
No cloud infrastructure, containers, or paid APIs \u2014 runs with `streamlit run app.py`.

Every ingestion run records its exact query, access timestamp, endpoint, record counts, and
licensing to `data/metadata/`. Raw downloads are never modified after being written; cleaning
happens on a separate copy. See `DATA_PROVENANCE.md`.
""")

with tab3:
    st.markdown("""
- No observation, species record, coordinate, date, count, or statistic here is fabricated.
- Missing real data shows **"Verified data not available"** \u2014 never a placeholder number.
- Synthetic data exists only in `tests/`, never mixed with real data or shown on research pages.
- Observation counts are recorded occurrences, never claimed as biodiversity abundance.
- No research gap or metric is claimed novel or validated without literature support.

See `RESEARCH_METHOD.md` for the full accounting.
""")
