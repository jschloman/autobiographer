"""Overview page — hero card, KPI metrics, and top-entity charts."""

from __future__ import annotations

import datetime

import plotly.express as px
import streamlit as st
from pandas import DataFrame

from analysis_utils import get_top_entities
from components.theme import (
    ACCENT_CYAN,
    ACCENT_INDIGO,
    ACCENT_PINK,
    ACCENT_PURPLE,
    TEXT_DIM,
    apply_dark_theme,
    card_container,
)

try:
    from streamlit_extras.metric_cards import style_metric_cards

    _HAS_METRIC_CARDS = True
except ImportError:
    _HAS_METRIC_CARDS = False


def _pct_delta(current: float, previous: float) -> float | None:
    """Return percentage change, or None when previous is zero."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _last30_delta(df: DataFrame, func: object) -> tuple[int, str | None]:
    """Return (total_value, delta_str) comparing last 30 days to prior 30 days.

    Args:
        df: DataFrame with a ``date_text`` datetime column.
        func: Callable that accepts a DataFrame and returns a scalar count.

    Returns:
        Tuple of (total across full df, formatted delta string or None).
    """
    import typing

    f = typing.cast("typing.Callable[[DataFrame], int]", func)
    total: int = f(df)

    if df.empty:
        return total, None

    max_date: datetime.date = df["date_text"].dt.date.max()
    cur_start = max_date - datetime.timedelta(days=29)
    prev_end = cur_start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=29)

    cur_val: int = f(df[df["date_text"].dt.date >= cur_start])
    prev_val: int = f(
        df[(df["date_text"].dt.date >= prev_start) & (df["date_text"].dt.date <= prev_end)]
    )

    pct = _pct_delta(cur_val, prev_val)
    delta_str = f"{pct:+.0f}%" if pct is not None else None
    return total, delta_str


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
    """Render the Overview page: hero card, KPI metrics, and top-entity charts.

    Reads the active DataFrame from ``st.session_state['df']``.
    Shows an empty state when no data has been loaded.
    """
    df: DataFrame | None = st.session_state.get("df")

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

    total_scrobbles = len(df)
    unique_artists = df["artist"].nunique()
    unique_albums = df["album"].nunique()
    unique_tracks = df["track"].nunique()
    listening_days = df["date_text"].dt.date.nunique()

    # ── Hero card ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div class="autobio-hero-card">
            <div style="display:flex;justify-content:space-between;align-items:center;
                        flex-wrap:wrap;gap:1.5rem">
                <div>
                    <p style="font-size:48px;font-weight:700;color:#f0f4ff;
                               margin:0;line-height:1">{total_scrobbles:,}</p>
                    <p style="font-size:14px;color:{TEXT_DIM};margin:4px 0 0 0">total scrobbles</p>
                </div>
                <div style="display:flex;gap:2.5rem;flex-wrap:wrap">
                    <div style="text-align:center">
                        <p style="font-size:24px;font-weight:700;color:{ACCENT_INDIGO};
                                   margin:0;line-height:1">{unique_artists:,}</p>
                        <p style="font-size:11px;color:{TEXT_DIM};margin:4px 0 0 0">artists</p>
                    </div>
                    <div style="text-align:center">
                        <p style="font-size:24px;font-weight:700;color:{ACCENT_CYAN};
                                   margin:0;line-height:1">{unique_albums:,}</p>
                        <p style="font-size:11px;color:{TEXT_DIM};margin:4px 0 0 0">albums</p>
                    </div>
                    <div style="text-align:center">
                        <p style="font-size:24px;font-weight:700;color:{ACCENT_PINK};
                                   margin:0;line-height:1">{unique_tracks:,}</p>
                        <p style="font-size:11px;color:{TEXT_DIM};margin:4px 0 0 0">tracks</p>
                    </div>
                    <div style="text-align:center">
                        <p style="font-size:24px;font-weight:700;color:{ACCENT_PURPLE};
                                   margin:0;line-height:1">{listening_days:,}</p>
                        <p style="font-size:11px;color:{TEXT_DIM};margin:4px 0 0 0">days</p>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPI metric row ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    scrobbles_total, scrobbles_delta = _last30_delta(df, len)
    artists_total, artists_delta = _last30_delta(df, lambda d: d["artist"].nunique())
    albums_total, albums_delta = _last30_delta(df, lambda d: d["album"].nunique())
    days_total, days_delta = _last30_delta(df, lambda d: d["date_text"].dt.date.nunique())

    c1.metric("Total Scrobbles", f"{scrobbles_total:,}", delta=scrobbles_delta)
    c2.metric("Unique Artists", f"{artists_total:,}", delta=artists_delta)
    c3.metric("Unique Albums", f"{albums_total:,}", delta=albums_delta)
    c4.metric("Listening Days", f"{days_total:,}", delta=days_delta)

    if _HAS_METRIC_CARDS:
        style_metric_cards(
            background_color="#141c2f",
            border_color="#2d3a52",
            border_left_color="#6366f1",
            border_radius_px=12,
            box_shadow=True,
        )

    # ── Top charts (card grid) ────────────────────────────────────────────────
    with card_container():
        render_top_charts(df)
