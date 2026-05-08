"""Life in Chapters page — geographic autobiography timeline.

Renders a vertical scrolling timeline of life chapters derived from the
assumptions file (residency + trips).  Each chapter card shows date range,
location, total plays, top-5 artists, discovery count, chapter-exclusive
artists, and top album.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis_utils import build_life_chapters, detect_trips_from_swarm, load_assumptions
from components.theme import (
    ACCENT_INDIGO,
    AMBER,
    CARD_BG,
    TEAL,
    TEXT_DIM,
    TEXT_PRIMARY,
    apply_dark_theme,
)

_DETECTED_TRIPS_CACHE = os.path.join("data", "cache", "detected_trips.json")


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


def _load_detected_trips_cache(path: str = _DETECTED_TRIPS_CACHE) -> list[dict[str, Any]]:
    """Load previously detected trips from the JSON cache file.

    Args:
        path: Path to the cache file.

    Returns:
        List of trip dicts, or an empty list if the file does not exist.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data: list[dict[str, Any]] = json.load(fh)
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_detected_trips_cache(
    trips: list[dict[str, Any]], path: str = _DETECTED_TRIPS_CACHE
) -> None:
    """Persist detected trips to a JSON cache file.

    Args:
        trips: List of trip dicts from ``detect_trips_from_swarm()``.
        path: Destination file path.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(trips, fh, indent=2)


def _render_chapter_map(chapter: dict[str, Any], swarm_df: pd.DataFrame | None) -> None:
    """Render a compact scatter map for a single chapter.

    Uses Swarm check-ins from the chapter's date range when available;
    falls back to a single marker at the chapter's lat/lng if present.
    Skips silently if no geographic data exists for the chapter.

    Args:
        chapter: Chapter dict (must include ``start``, ``end``, ``label``,
            and optionally ``lat`` / ``lng``).
        swarm_df: Raw Swarm check-in DataFrame with ``timestamp``, ``lat``,
            ``lng``, and ``city`` columns, or ``None`` if unavailable.
    """
    chapter_lat: float | None = chapter.get("lat")
    chapter_lng: float | None = chapter.get("lng")

    map_df: pd.DataFrame | None = None

    if swarm_df is not None and not swarm_df.empty:
        required = {"timestamp", "lat", "lng"}
        if required.issubset(swarm_df.columns):
            dt = pd.to_datetime(swarm_df["timestamp"], unit="s", utc=True).dt.date
            mask = (dt >= chapter["start"].date()) & (dt <= chapter["end"].date())
            chapter_swarm = swarm_df[mask].dropna(subset=["lat", "lng"])
            chapter_swarm = chapter_swarm[chapter_swarm["lat"] != 0]
            if not chapter_swarm.empty:
                group_cols = [c for c in ["city", "lat", "lng"] if c in chapter_swarm.columns]
                map_df = chapter_swarm.groupby(group_cols).size().reset_index(name="checkins")
                if "city" not in map_df.columns:
                    map_df["city"] = chapter["label"]

    if map_df is None or map_df.empty:
        if chapter_lat is None or chapter_lng is None:
            return
        map_df = pd.DataFrame(
            [{"city": chapter["label"], "lat": chapter_lat, "lng": chapter_lng, "checkins": 1}]
        )

    center_lat = chapter_lat if chapter_lat is not None else float(map_df["lat"].mean())
    center_lng = chapter_lng if chapter_lng is not None else float(map_df["lng"].mean())

    fig = px.scatter_map(
        map_df,
        lat="lat",
        lon="lng",
        size="checkins",
        size_max=20,
        hover_name="city",
        color_discrete_sequence=[ACCENT_INDIGO],
        zoom=5,
        center={"lat": center_lat, "lon": center_lng},
    )
    fig.update_layout(
        map_style="carto-darkmatter",
        height=220,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_chapter_card(
    chapter: dict[str, Any],
    index: int,
    total: int,
    swarm_df: pd.DataFrame | None = None,
) -> None:
    """Render a single chapter as a styled Streamlit card with a connector line.

    Args:
        chapter: Chapter dict from ``build_life_chapters()``.
        index: Zero-based position of this chapter in the list.
        total: Total number of chapters (used to suppress the trailing line).
        swarm_df: Raw Swarm check-in DataFrame used to populate the chapter map.
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

        # Chapter map
        _render_chapter_map(chapter, swarm_df)


def _render_trip_detector(assumptions: dict[str, Any], detected_trips_path: str) -> None:
    """Render the Swarm-based trip detection section.

    Allows the user to detect trips from Swarm check-in data by clustering
    check-ins that are far from their home residency location.  Results are
    saved to ``detected_trips_path`` and the page is refreshed so the new
    trips immediately appear on the timeline and year dropdown.

    Args:
        assumptions: Parsed assumptions dict (provides home residency lat/lng).
        detected_trips_path: File path where detected trips JSON is saved/loaded.
    """
    swarm_df: pd.DataFrame | None = st.session_state.get("swarm_df")
    if swarm_df is None or swarm_df.empty:
        st.info(
            "No Swarm check-in data loaded. "
            "Add a Swarm source in the sidebar to enable trip detection."
        )
        return

    cached = _load_detected_trips_cache(detected_trips_path)
    if cached:
        st.caption(
            f"Last run detected {len(cached)} trip(s). Results saved to `{detected_trips_path}`."
        )

    col_a, col_b = st.columns(2)
    with col_a:
        radius_km = st.slider(
            "Distance from home (km)",
            min_value=20,
            max_value=300,
            value=80,
            step=10,
            key="trip_radius_km",
        )
    with col_b:
        gap_days = st.slider(
            "Days gap between trips",
            min_value=1,
            max_value=14,
            value=2,
            step=1,
            key="trip_gap_days",
        )

    if st.button(":material/travel_explore: Detect trips", key="detect_trips_btn"):
        with st.status("Detecting trips from Swarm check-ins…", expanded=True) as status:
            trips = detect_trips_from_swarm(
                swarm_df,
                assumptions,
                radius_km=float(radius_km),
                gap_days=int(gap_days),
                progress_cb=st.write,
            )
            _save_detected_trips_cache(trips, detected_trips_path)
            label = f"Done — {len(trips)} trip(s) detected" if trips else "Done — no trips detected"
            status.update(label=label, state="complete")
        st.rerun()


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

    # Resolve detected trips file path (configurable via Location Assumptions plugin)
    detected_trips_path: str = (
        st.session_state.get("assumptions_detected_trips_file") or _DETECTED_TRIPS_CACHE
    )

    # ── Trip detector (collapsed by default) ──────────────────────────────────
    with st.expander(":material/travel_explore: Detect trips from Swarm data", expanded=False):
        _render_trip_detector(assumptions, detected_trips_path)

    has_residency = bool(assumptions.get("residency"))
    has_trips = bool(assumptions.get("trips"))

    # Merge auto-detected trips from cache into assumptions so they appear on the timeline
    detected_trips = _load_detected_trips_cache(detected_trips_path)
    if detected_trips:
        merged_assumptions: dict[str, Any] = dict(assumptions)
        merged_assumptions["trips"] = list(assumptions.get("trips", [])) + detected_trips
    else:
        merged_assumptions = assumptions

    if not has_residency and not (has_trips or detected_trips):
        st.warning(
            "No residency or trip data found in your assumptions file. "
            "Add `residency` and/or `trips` entries to see your life chapters."
        )
        return

    chapters = build_life_chapters(df, merged_assumptions)

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

    # ── Plays range filter ────────────────────────────────────────────────────
    with st.expander("Filter chapters", expanded=False):
        max_plays_val = max(c["total_plays"] for c in chapters)
        # Guard against all-zero case (slider requires min < max or a fixed value)
        slider_max = max_plays_val if max_plays_val > 0 else 1
        min_plays, max_plays = st.slider(
            "Plays range",
            min_value=0,
            max_value=slider_max,
            value=(0, slider_max),
            step=10,
            key="chapters_plays_range",
        )
        chapters = [c for c in chapters if min_plays <= c["total_plays"] <= max_plays]

    # ── Year pagination ───────────────────────────────────────────────────────
    all_years = sorted({yr for c in chapters for yr in range(c["start"].year, c["end"].year + 1)})
    if len(all_years) > 1:
        year_options = ["All years"] + [str(y) for y in all_years]
        selected_year = st.selectbox(
            "Jump to year",
            year_options,
            index=0,
            key="chapter_year",
            label_visibility="collapsed",
        )
        if selected_year != "All years":
            yr = int(selected_year)
            chapters = [c for c in chapters if c["start"].year <= yr <= c["end"].year]

    if not chapters:
        st.info("No chapters match the current filter.")
        return

    # ── Timeline ─────────────────────────────────────────────────────────────
    page_swarm_df: pd.DataFrame | None = st.session_state.get("swarm_df")
    for i, chapter in enumerate(chapters):
        _render_chapter_card(chapter, i, len(chapters), swarm_df=page_swarm_df)

    # Trailing connector end-cap
    st.markdown(
        f"""
        <div style="display:flex; justify-content:center; margin: 0; padding: 0;">
          <div style="width:2px; height:20px; background:{ACCENT_INDIGO}; opacity:0.3;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
