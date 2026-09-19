import streamlit as st

st.set_page_config(page_title="BIOGAP -- Temporal Gaps", page_icon="\U0001F4C5", layout="wide")

from src.visualization.theme import inject_theme, hero, topbar, note
from src.appui.gate import require_real_data
from src.appui.filters import sidebar_filters
from src.processing.temporal import parse_observation_date, extract_year_month
from src.analysis.temporal import yearly_coverage, monthly_pattern, low_coverage_years, coefficient_of_variation
from src.visualization.charts import temporal_line_chart, monthly_pattern_chart

inject_theme()
topbar("Temporal Gaps")
hero("Temporal observation gaps", "Which periods have strong or weak coverage?")

df = require_real_data()
if df is None:
    st.stop()

filtered, _ = sidebar_filters(df, include_grid_size=False)
if filtered.empty:
    st.info("No records match the current filters.")
    st.stop()

yearly = yearly_coverage(filtered)
st.plotly_chart(temporal_line_chart(yearly), width='stretch')

cv = coefficient_of_variation(yearly["record_count"]) if not yearly.empty else None
c1, c2, c3 = st.columns(3)
c1.metric("Distinct years with records", int(yearly.shape[0]))
c2.metric("Records missing a year value", int(filtered["year"].isna().sum()))
c3.metric("Coefficient of variation (yearly)", f"{cv:.2f}" if cv is not None else "n/a")

st.markdown("### Seasonal pattern")
parsed = parse_observation_date(filtered["observation_date"])
month_df = extract_year_month(parsed)
working = filtered.copy()
working["derived_month"] = month_df["derived_month"]
monthly = monthly_pattern(working)
if monthly.empty:
    st.info("Not enough parseable observation dates to compute a seasonal pattern.")
else:
    st.plotly_chart(monthly_pattern_chart(monthly), width='stretch')

st.markdown("### Relatively low-coverage years")
quantile = st.slider("Flag years at or below this percentile of this dataset's yearly counts",
                      min_value=0.05, max_value=0.5, value=0.25, step=0.05)
low_years = low_coverage_years(yearly, quantile_threshold=quantile)
st.dataframe(low_years, width='stretch', hide_index=True)
note("Relative to other years in this dataset only — not a validated sampling-adequacy threshold.")
