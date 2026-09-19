"""
app.py -- BIOGAP entry point.

Run with:  streamlit run app.py

This file sets global page config and renders the same Overview content
that appears in pages/01_Overview.py (via src/appui/overview.py), so the
app shows something meaningful immediately, and the sidebar-based
multipage navigation (Streamlit's built-in pages/ convention) gives access
to every other page.
"""

import streamlit as st

st.set_page_config(
    page_title="BIOGAP -- Biodiversity Observation Gap Analytics",
    page_icon="\U0001F33F",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.appui.overview import render  # noqa: E402  (import after set_page_config, as Streamlit requires)

render()
