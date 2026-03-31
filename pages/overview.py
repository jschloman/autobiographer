"""Overview page — top-level metrics and top charts."""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from pandas import DataFrame

from analysis_utils import get_top_entities
from components.theme import apply_dark_theme


def render_top_charts(df: DataFrame) -> None:
    """Render top entity charts with a type toggle.

    Args:
        df: Loaded listening history DataFrame.
    """
    st.header("Top Charts")
    entity_type = st.radio("Select chart type", ["artist", "album", "track"], horizontal=True)
    limit = st.slider(f"Top {entity_type.capitalize()}s to show", 5, 50, 10)
    top_data = get_top_entities(df, entity_type, limit=limit)
    col1, col2 = st.columns([2, 1])
    with col1:
        fig_bar = px.bar(
            top_data,
            x="Plays",
            y=entity_type,
            orientation="h",
            title=f"Top {limit} {entity_type.capitalize()}s",
        )
        fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
        apply_dark_theme(fig_bar)
        st.plotly_chart(fig_bar, width="stretch")
    with col2:
        fig_pie = px.pie(
            top_data.head(10), values="Plays", names=entity_type, title="Market Share (Top 10)"
        )
        apply_dark_theme(fig_pie)
        st.plotly_chart(fig_pie, width="stretch")


def render_overview() -> None:
    """Render the Overview page: key metrics and top-entity charts.

    Reads the active DataFrame from ``st.session_state['df']``.
    Shows an empty state when no data has been loaded.
    """
    st.header("Overview")

    df = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tracks", len(df))
    col2.metric("Unique Artists", df["artist"].nunique())
    col3.metric("Unique Albums", df["album"].nunique())

    render_top_charts(df)
