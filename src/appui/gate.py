"""
src/appui/gate.py

Shared "do we have real data yet" gate. Every analysis page calls this
first; if it returns None, the page has already rendered the honest
pending-state message and should st.stop() immediately.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from src.utils.data_status import load_combined_data


def require_real_data() -> Optional[pd.DataFrame]:
    df = load_combined_data()
    if df is None:
        st.warning(
            "**Verified dataset pending.** No real ingestion run has produced usable "
            "records yet. Go to the **Overview** page and run the ingestion pipeline, "
            "or run `python -m src.pipeline` from the command line."
        )
        st.caption(
            "This message is shown instead of a chart because BIOGAP does not display "
            "placeholder, sample, or simulated data as if it were research output."
        )
        return None
    return df
