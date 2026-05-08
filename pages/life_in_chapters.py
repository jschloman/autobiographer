"""Life in Chapters page — geographic autobiography timeline.

Renders a vertical scrolling timeline of life chapters derived from the
assumptions file (residency + trips).  Each chapter card shows date range,
location, total plays, top-5 artists, discovery count, chapter-exclusive
artists, and top album.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from analysis_utils import build_life_chapters, load_assumptions
from components.theme import (
    ACCENT_INDIGO,
    AMBER,
    CARD_BG,
    TEAL,
    TEXT_DIM,
    TEXT_PRIMARY,
)


def _format_date_range(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Format a start/end timestamp pair as a human-readable date range string.

    Args:
        start: Chapter start timestamp.
        end: Chapter end timestamp.

    Returns:
        String like ``"Jan 2019 – Mar 2020"`` or ``"1 Jan – 15 Mar 2024"``.
    """
    if start.year == end.year:
        return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%b %Y')} – {end.strftime('%b %Y')}"


def _duration_label(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Return a short duration string for a chapter.

    Args:
        start: Chapter start timestamp.
        end: Chapter end timestamp.

    Returns:
        String like ``"2 years 3 months"`` or ``"18 days"``.
    """
    delta = end - start
    days = delta.days
    if days < 1:
        return "< 1 day"
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''}"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''}"
    years = months // 12
    remainder = months % 12
    if remainder == 0:
        return f"{years} year{'s' if years != 1 else ''}"
    return f"{years} yr {remainder} mo"


def _render_chapter_card(chapter: dict[str, Any], index: int, total: int) -> None:
    """Render a single chapter as a styled Streamlit card with a connector line.

    Args:
        chapter: Chapter dict from ``build_life_chapters()``.
        index: Zero-based position of this chapter in the list.
        total: Total number of chapters (used to suppress the trailing line).
    """
    start: pd.Timestamp = chapter["start"]
    end: pd.Timestamp = chapter["end"]
    label: str = chapter["label"]
    location: str = chapter["location"]
    total_plays: int = chapter["total_plays"]
    top_artists: list[str] = chapter["top_artists"]
    top_album: str | None = chapter["top_album"]
    discovery_count: int = chapter["discovery_count"]
    exclusive_artists: list[str] = chapter["exclusive_artists"]

    date_str = _format_date_range(start, end)
    duration = _duration_label(start, end)

    # ── Connector line above each card (except the first) ───────────────────
    if index > 0:
        st.markdown(
            f"""
            <div style="display:flex; justify-content:center; margin: 0; padding: 0;">
              <div style="width:2px; height:32px; background:{ACCENT_INDIGO}; opacity:0.5;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Chapter bullet ───────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
          <div style="width:14px; height:14px; border-radius:50%;
                      background:{ACCENT_INDIGO}; flex-shrink:0; margin:auto;
                      box-shadow: 0 0 0 3px {CARD_BG}, 0 0 0 5px {ACCENT_INDIGO}44;"></div>
          <span style="color:{TEXT_DIM}; font-size:0.8rem; letter-spacing:0.05em;
                        text-transform:uppercase; font-weight:600;">
            {date_str} &nbsp;·&nbsp; {duration}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Card body ─────────────────────────────────────────────────────────────
    with st.container(border=True):
        # Header row: chapter title + play count badge
        col_title, col_badge = st.columns([4, 1])
        with col_title:
            st.subheader(label)
            st.caption(f":material/location_on: {location}")
        with col_badge:
            st.metric("Plays", f"{total_plays:,}")

        if total_plays == 0:
            st.info("No listening data found for this period.")
            return

        st.divider()

        # Stats row
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown(
                f"**Discoveries**\n\n"
                f"<span style='font-size:1.6rem; color:{TEAL}; font-weight:700;'>"
                f"{discovery_count}</span> new artists",
                unsafe_allow_html=True,
            )
        with col_b:
            if top_album:
                st.markdown(
                    f"**Top Album**\n\n"
                    f"<span style='color:{AMBER}; font-weight:600;'>{top_album}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("**Top Album**\n\n—")
        with col_c:
            exclusive_str = ", ".join(exclusive_artists[:3]) if exclusive_artists else "—"
            st.markdown(
                f"**Chapter-Exclusive Artists**\n\n"
                f"<span style='color:{TEXT_DIM};'>{exclusive_str}</span>",
                unsafe_allow_html=True,
            )

        # Top-5 artists
        if top_artists:
            st.markdown("**Top Artists**")
            artist_cols = st.columns(min(len(top_artists), 5))
            for i, (col, artist) in enumerate(zip(artist_cols, top_artists)):
                rank_color = ACCENT_INDIGO if i == 0 else TEXT_DIM
                col.markdown(
                    f"<div style='text-align:center;'>"
                    f"<span style='color:{rank_color}; font-weight:700; font-size:0.9rem;'>"
                    f"#{i + 1}</span><br>"
                    f"<span style='font-size:0.8rem; color:{TEXT_PRIMARY};'>{artist}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )


def render_life_in_chapters() -> None:
    """Render the Life in Chapters geographic autobiography timeline page.

    Reads listening history from ``st.session_state['df']`` and the
    assumptions file path from ``st.session_state['_loaded_config']``.
    Shows an empty state when no data has been loaded or no assumptions
    file is configured.
    """
    df: pd.DataFrame | None = st.session_state.get("df")

    st.header("Life in Chapters")
    st.caption(
        "A geographic autobiography: each chapter represents a distinct period "
        "and place, illustrated through your listening history."
    )

    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    # Resolve assumptions file path from loaded config
    loaded_config = st.session_state.get("_loaded_config")
    assumptions_path: str | None = loaded_config[2] if loaded_config else None
    assumptions = load_assumptions(assumptions_path)

    has_residency = bool(assumptions.get("residency"))
    has_trips = bool(assumptions.get("trips"))

    if not has_residency and not has_trips:
        st.warning(
            "No residency or trip data found in your assumptions file. "
            "Add `residency` and/or `trips` entries to see your life chapters."
        )
        return

    chapters = build_life_chapters(df, assumptions)

    if not chapters:
        st.info("No chapters could be built from the assumptions data.")
        return

    # ── Summary banner ────────────────────────────────────────────────────────
    total_chapter_plays = sum(c["total_plays"] for c in chapters)
    total_discoveries = sum(c["discovery_count"] for c in chapters)
    first_start = chapters[0]["start"]
    last_end = chapters[-1]["end"]
    span_years = (last_end - first_start).days / 365.25

    banner_cols = st.columns(4)
    banner_cols[0].metric("Chapters", len(chapters))
    banner_cols[1].metric("Plays Across Chapters", f"{total_chapter_plays:,}")
    banner_cols[2].metric("Artist Discoveries", total_discoveries)
    banner_cols[3].metric("Years Covered", f"{span_years:.1f}")

    st.divider()

    # ── Expandable filter ─────────────────────────────────────────────────────
    with st.expander("Filter chapters", expanded=False):
        min_plays_filter = st.slider(
            "Minimum plays in chapter",
            min_value=0,
            max_value=max(c["total_plays"] for c in chapters),
            value=0,
            step=10,
            key="chapters_min_plays",
        )
        chapters = [c for c in chapters if c["total_plays"] >= min_plays_filter]

    if not chapters:
        st.info("No chapters match the current filter.")
        return

    # ── Timeline ─────────────────────────────────────────────────────────────
    for i, chapter in enumerate(chapters):
        _render_chapter_card(chapter, i, len(chapters))

    # Trailing connector end-cap
    st.markdown(
        f"""
        <div style="display:flex; justify-content:center; margin: 0; padding: 0;">
          <div style="width:2px; height:20px; background:{ACCENT_INDIGO}; opacity:0.3;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
