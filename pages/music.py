"""Music page — listening timeline and activity charts."""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from pandas import DataFrame

from analysis_utils import get_cumulative_plays, get_listening_intensity
from components.theme import apply_dark_theme


def render_timeline_analysis(df: DataFrame) -> None:
    """Render listening timeline and cumulative growth charts.

    Args:
        df: Loaded listening history DataFrame.
    """
    st.header("Activity Over Time")
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq_label = st.selectbox("Select grouping frequency", list(freq_map.keys()))
    intensity = get_listening_intensity(df, freq_map[freq_label])
    fig_intensity = px.line(intensity, x="date", y="Plays", title=f"Plays per {freq_label}")
    apply_dark_theme(fig_intensity)
    st.plotly_chart(fig_intensity, width="stretch")
    st.subheader("Cumulative Growth")
    cumulative = get_cumulative_plays(df)
    fig_cumulative = px.area(cumulative, x="date", y="CumulativePlays", title="Total Plays Growth")
    apply_dark_theme(fig_cumulative)
    st.plotly_chart(fig_cumulative, width="stretch")


def render_music() -> None:
    """Render the Music page: timeline and cumulative listening charts.

    Reads the active DataFrame from ``st.session_state['df']``.
    Shows an empty state when no data has been loaded.
    """
    df = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    render_timeline_analysis(df)
