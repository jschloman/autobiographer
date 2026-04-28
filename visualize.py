"""Autobiographer dashboard entrypoint.

Configures the page, renders the shared sidebar, and runs the multi-page
navigation. All chart logic lives in the ``pages/`` modules; shared data
loading lives in ``components/sidebar``.

Run with::

    streamlit run visualize.py
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from components.sidebar import render_sidebar
from pages.beer import render_beer
from pages.culture import render_culture
from pages.fitness import render_fitness
from pages.insights import render_insights, render_insights_and_narrative  # noqa: F401
from pages.music import render_music, render_timeline_analysis  # noqa: F401
from pages.overview import render_overview, render_top_charts  # noqa: F401
from pages.places import render_places, render_spatial_analysis  # noqa: F401

load_dotenv()

_SIDEBAR_CSS = """
<style>
/* ── Data Sources section header ──────────────────────────────────────────
   Matches the st.navigation group-label style: small, uppercase, muted.    */
.autobio-section-header {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    opacity: 0.55;
    margin: 0.5rem 0 0.15rem 0;
    padding-left: 0.5rem;
    line-height: 1.5;
}

/* ── Plugin expanders ─────────────────────────────────────────────────────
   Strip the bordered-box styling so each plugin reads as a flat list item
   (matching the visual weight of "Listening" / "Check-ins" nav items).     */
section[data-testid="stSidebar"] div[data-testid="stExpander"] > details {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
}

/* Summary row (collapsed toggle) — same size and padding as a nav item */
section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
    font-size: 0.875rem;
    font-weight: 400;
    padding: 0.35rem 0.6rem;
    border-radius: 0.4rem;
}

section[data-testid="stSidebar"] div[data-testid="stExpander"] summary:hover {
    background-color: rgba(255, 255, 255, 0.07);
}

/* Indent the expanded content slightly, like a nav sub-section */
section[data-testid="stSidebar"] div[data-testid="stExpander"] details > div {
    padding-left: 0.75rem;
}
</style>
"""


def main() -> None:
    """Configure and launch the Autobiographer multi-page dashboard."""
    st.set_page_config(page_title="Autobiographer", layout="wide")
    st.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)

    render_sidebar()

    pg = st.navigation(
        {
            "Overview": [
                st.Page(render_overview, title="Overview", icon=":material/dashboard:"),
            ],
            "Music": [
                st.Page(render_music, title="Listening", icon=":material/headphones:"),
                st.Page(render_insights, title="Insights", icon=":material/auto_stories:"),
            ],
            "Places": [
                st.Page(render_places, title="Check-ins", icon=":material/location_on:"),
            ],
            "Health": [
                st.Page(render_fitness, title="Fitness", icon=":material/fitness_center:"),
            ],
            "Culture": [
                st.Page(render_culture, title="Films & Books", icon=":material/local_library:"),
                st.Page(render_beer, title="Beer", icon=":material/sports_bar:"),
            ],
        }
    )
    pg.run()


if __name__ == "__main__":
    main()
