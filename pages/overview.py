"""Overview page — hero card and top-entity charts."""

from __future__ import annotations

import datetime

import plotly.express as px
import streamlit as st
from pandas import DataFrame

from analysis_utils import get_top_entities
from components.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_INDIGO,
    ACCENT_ORANGE,
    ACCENT_PINK,
    ACCENT_PURPLE,
    ACCENT_YELLOW,
    TEXT_DIM,
    apply_dark_theme,
    card_container,
)


def _stat_html(value: str, label: str, color: str) -> str:
    """Return HTML for a single secondary stat inside the hero card."""
    return (
        f'<div style="text-align:center">'
        f'<p style="font-size:24px;font-weight:700;color:{color};margin:0;line-height:1">'
        f"{value}</p>"
        f'<p style="font-size:11px;color:{TEXT_DIM};margin:4px 0 0 0">{label}</p>'
        f"</div>"
    )


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
    """Render the Overview page: hero card and top-entity charts.

    Reads ``st.session_state['df']`` (Last.fm) and optionally
    ``st.session_state['swarm_df']`` (Foursquare/Swarm).  Shows an empty
    state when no data has been loaded.
    """
    df: DataFrame | None = st.session_state.get("df")
    swarm_df: DataFrame | None = st.session_state.get("swarm_df")

    year = (
        df["date_text"].dt.year.max()
        if df is not None and not df.empty
        else datetime.date.today().year
    )

    # ── Page header ──────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <h1 style="font-size:22px;font-weight:700;margin-bottom:2px;color:#f0f4ff">Overview</h1>
        <p style="font-size:12px;color:{TEXT_DIM};margin-top:0;margin-bottom:1rem">
            Your complete personal data &middot; {year}
        </p>
        """,
        unsafe_allow_html=True,
    )

    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    # ── Last.fm stats ─────────────────────────────────────────────────────────
    total_scrobbles = len(df)
    music_stats = "".join(
        [
            _stat_html(f"{df['artist'].nunique():,}", "artists", ACCENT_INDIGO),
            _stat_html(f"{df['album'].nunique():,}", "albums", ACCENT_CYAN),
            _stat_html(f"{df['track'].nunique():,}", "tracks", ACCENT_PINK),
            _stat_html(f"{df['date_text'].dt.date.nunique():,}", "days", ACCENT_PURPLE),
        ]
    )

    # ── Hero card — built as a flat joined string so the Markdown renderer
    # never sees indented lines (4+ spaces = code block in CommonMark).  ─────
    parts = [
        '<div class="autobio-hero-card">',
        '<div style="display:flex;justify-content:space-between;'
        'align-items:center;flex-wrap:wrap;gap:1.5rem">',
        "<div>",
        f'<p style="font-size:48px;font-weight:700;color:#f0f4ff;'
        f'margin:0;line-height:1">{total_scrobbles:,}</p>',
        f'<p style="font-size:13px;color:{TEXT_DIM};margin:4px 0 0.75rem 0">Last.fm scrobbles</p>',
        f'<div style="display:flex;gap:2rem;flex-wrap:wrap">{music_stats}</div>',
        "</div>",
    ]

    if swarm_df is not None and not swarm_df.empty:
        total_checkins = len(swarm_df)
        unique_venues = swarm_df["venue"].nunique() if "venue" in swarm_df.columns else 0
        unique_cities = swarm_df["city"].nunique() if "city" in swarm_df.columns else 0
        unique_countries = swarm_df["country"].nunique() if "country" in swarm_df.columns else 0
        swarm_stats = "".join(
            [
                _stat_html(f"{unique_venues:,}", "venues", ACCENT_GREEN),
                _stat_html(f"{unique_cities:,}", "cities", ACCENT_ORANGE),
                _stat_html(f"{unique_countries:,}", "countries", ACCENT_YELLOW),
            ]
        )
        parts += [
            '<div style="border-left:1px solid #2d3a52;padding-left:2.5rem;margin-left:1rem">',
            f'<p style="font-size:11px;font-weight:600;color:{TEXT_DIM};'
            f"letter-spacing:0.08em;text-transform:uppercase;"
            f'margin:0 0 0.75rem 0">Foursquare</p>',
            '<div style="display:flex;flex-direction:column;align-items:flex-start;gap:0.5rem">',
            '<div style="display:flex;align-items:baseline;gap:0.5rem">',
            f'<p style="font-size:32px;font-weight:700;color:#f0f4ff;'
            f'margin:0;line-height:1">{total_checkins:,}</p>',
            f'<p style="font-size:13px;color:{TEXT_DIM};margin:0">check-ins</p>',
            "</div>",
            f'<div style="display:flex;gap:1.5rem;flex-wrap:wrap">{swarm_stats}</div>',
            "</div>",
            "</div>",
        ]

    parts += ["</div>", "</div>"]
    st.markdown("".join(parts), unsafe_allow_html=True)

    # ── Top charts (card grid) ────────────────────────────────────────────────
    with card_container():
        render_top_charts(df)
