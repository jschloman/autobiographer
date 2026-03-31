"""Culture page — films, books, and TV from Letterboxd, Goodreads, Trakt, etc."""

from __future__ import annotations

import streamlit as st


def render_culture() -> None:
    """Render the Culture page.

    Shows an empty state until a culture source plugin is loaded.
    """
    st.header("Films & Books")
    st.info(
        "No culture data loaded yet. "
        "Add a Letterboxd, Goodreads, Trakt, or Audible source plugin "
        "and configure it in the sidebar."
    )
