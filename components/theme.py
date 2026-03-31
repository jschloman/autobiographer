"""Shared dark-theme palette and Plotly helpers for all pages.

All visual components — Plotly charts, pydeck maps, and map overlays — pull
their colours from this module so the application looks consistent.

Palette rationale
-----------------
The anchor colours are teal (#00C8C8) and amber (#FFA014).  Both read clearly
against Streamlit's dark background (#0e1117) and against the pydeck "dark"
basemap.  The teal end of the spectrum is used for low / cool values; amber for
high / hot values.  Supporting hues (purple, coral, mint, gold) are chosen to
complement this axis without clashing.
"""

from __future__ import annotations

import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Core palette
# ---------------------------------------------------------------------------

TEAL = "#00C8C8"  # low / cool / primary accent
AMBER = "#FFA014"  # high / warm / secondary accent

# Categorical colour sequence — used by bar, pie, and line charts.
COLORWAY: list[str] = [
    TEAL,
    AMBER,
    "#7B61FF",  # violet
    "#FF6060",  # coral
    "#4ECDC4",  # mint
    "#FFD700",  # gold
    "#C975FF",  # orchid
    "#FF9E6D",  # peach
]

# Sequential scale for continuous heatmaps and imshow plots.
# Runs dark-teal → teal → amber so low values are cool and high values warm.
SEQUENTIAL_SCALE: list[list[object]] = [
    [0.0, "#003838"],
    [0.5, TEAL],
    [1.0, AMBER],
]

# Plotly base template — provides dark grid lines and panel backgrounds that
# sit within Streamlit's dark UI without introducing jarring white regions.
PLOTLY_TEMPLATE = "plotly_dark"

# ---------------------------------------------------------------------------
# Map colours (for pydeck layers in places.py)
# ---------------------------------------------------------------------------

# Country overlay: visited countries get a teal wash; unvisited are invisible.
MAP_COUNTRY_VISITED_RGBA: list[int] = [0, 200, 200, 70]
MAP_COUNTRY_UNVISITED_RGBA: list[int] = [30, 30, 35, 30]

# Border colours on the dark basemap.
MAP_COUNTRY_BORDER_RGB: list[int] = [70, 70, 80]
MAP_STATE_BORDER_RGBA: list[int] = [80, 80, 90, 100]

# Column/scatter fallback colour when the data is empty.
MAP_COLUMN_DEFAULT_RGBA: list[int] = [0, 180, 180, 180]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def apply_dark_theme(fig: go.Figure) -> go.Figure:
    """Apply the standard dark theme and colour palette to a Plotly figure.

    Sets the base template to ``plotly_dark``, overrides the categorical
    colour sequence, and makes the paper / plot backgrounds transparent so
    figures blend into Streamlit's dark panel rather than showing a grey box.

    Args:
        fig: Any Plotly Figure object.

    Returns:
        The same figure, mutated in place and returned for chaining.
    """
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        colorway=COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
