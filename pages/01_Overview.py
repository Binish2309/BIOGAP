import streamlit as st

st.set_page_config(page_title="BIOGAP -- Overview", page_icon="\U0001F33F", layout="wide")

from src.appui.overview import render  # noqa: E402

render()
