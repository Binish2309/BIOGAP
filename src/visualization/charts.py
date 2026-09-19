"""
src/visualization/charts.py

Plotly chart builders, using a single consistent "scientific/nature"
theme (see THEME below) across the whole app, rather than Plotly/Streamlit
defaults.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

THEME = {
    "template": "simple_white",
    "colorway": ["#2E5339", "#74A57F", "#3E5C76", "#B0813E", "#8C7A6B", "#B0413E"],
    "font_family": "Source Sans Pro, Helvetica, Arial, sans-serif",
}


def _apply_theme(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        template=THEME["template"],
        title=dict(text=title, font=dict(size=18, family=THEME["font_family"])),
        font=dict(family=THEME["font_family"], size=13, color="#2B2B2B"),
        colorway=THEME["colorway"],
        margin=dict(l=40, r=20, t=60, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def taxonomic_bar_chart(group_representation_df: pd.DataFrame) -> go.Figure:
    if group_representation_df.empty:
        fig = go.Figure()
        return _apply_theme(fig, "Taxonomic group representation (no data)")
    fig = px.bar(
        group_representation_df.sort_values("record_count", ascending=True),
        x="record_count", y="major_group", orientation="h",
        hover_data=["unique_species", "share_of_records"],
        labels={"record_count": "Recorded observations", "major_group": "Major taxonomic group"},
    )
    return _apply_theme(fig, "Recorded observations by major taxonomic group (recording share, not abundance)")


def temporal_line_chart(yearly_coverage_df: pd.DataFrame) -> go.Figure:
    if yearly_coverage_df.empty:
        fig = go.Figure()
        return _apply_theme(fig, "Observations by year (no data)")
    fig = px.line(
        yearly_coverage_df.sort_values("year"), x="year", y="record_count", markers=True,
        labels={"year": "Year", "record_count": "Recorded observations"},
    )
    return _apply_theme(fig, "Recorded observations by year (recording activity, not a population trend)")


def monthly_pattern_chart(monthly_df: pd.DataFrame) -> go.Figure:
    if monthly_df.empty:
        fig = go.Figure()
        return _apply_theme(fig, "Observations by month (no data)")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    df = monthly_df.copy()
    df["month_name"] = df["month"].apply(lambda m: month_names[int(m) - 1] if pd.notna(m) else "?")
    fig = px.bar(df, x="month_name", y="record_count",
                 category_orders={"month_name": month_names},
                 labels={"month_name": "Month", "record_count": "Recorded observations"})
    return _apply_theme(fig, "Seasonal recording pattern (pooled across all years)")


def cross_platform_taxonomic_chart(composition_df: pd.DataFrame) -> go.Figure:
    if composition_df.empty:
        fig = go.Figure()
        return _apply_theme(fig, "Cross-platform taxonomic composition (no data)")
    fig = px.bar(
        composition_df, x="major_group", y="share_of_records", color="source", barmode="group",
        labels={"share_of_records": "Share of that platform's records", "major_group": "Major taxonomic group"},
    )
    return _apply_theme(fig, "Taxonomic composition by platform (share within each platform, not raw counts)")


def missingness_bar_chart(missing_summary: pd.Series) -> go.Figure:
    if missing_summary.empty:
        fig = go.Figure()
        return _apply_theme(fig, "Missing-field summary (no data)")
    df = missing_summary.reset_index()
    df.columns = ["field", "n_missing"]
    fig = px.bar(df.sort_values("n_missing", ascending=True), x="n_missing", y="field", orientation="h",
                 labels={"n_missing": "Records missing this field", "field": "Field"})
    return _apply_theme(fig, "Missing-value counts by field")
