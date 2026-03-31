"""Beer page — check-in history from Untappd."""

from __future__ import annotations

import streamlit as st


def render_beer() -> None:
    """Render the Beer page.

    Shows an empty state until the Untappd source plugin is loaded.
    """
    st.header("Beer")
    st.info(
        "No beer data loaded yet. Add the Untappd source plugin and configure it in the sidebar."
    )
