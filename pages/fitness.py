"""Fitness page — activity from Strava, Garmin, Runkeeper, etc."""

from __future__ import annotations

import streamlit as st


def render_fitness() -> None:
    """Render the Fitness page.

    Shows an empty state until a fitness source plugin is loaded.
    """
    st.header("Fitness")
    st.info(
        "No fitness data loaded yet. "
        "Add a Strava, Garmin, or Runkeeper source plugin and configure it in the sidebar."
    )
