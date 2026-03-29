"""Autobiographer dashboard entrypoint.

Configures the page, renders the shared sidebar, and runs the multi-page
navigation. All chart logic lives in the ``pages/`` modules; shared data
loading lives in ``components/sidebar``.

Run with::

    streamlit run visualize.py
"""

from __future__ import annotations

import streamlit as st

from components.sidebar import render_sidebar
from pages.beer import render_beer
from pages.culture import render_culture
from pages.fitness import render_fitness
from pages.insights import render_insights, render_insights_and_narrative  # noqa: F401
from pages.music import render_music, render_timeline_analysis  # noqa: F401
from pages.overview import render_overview, render_top_charts  # noqa: F401
from pages.places import render_places, render_spatial_analysis  # noqa: F401


def main() -> None:
    """Configure and launch the Autobiographer multi-page dashboard."""
    st.set_page_config(page_title="Autobiographer", layout="wide")

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
