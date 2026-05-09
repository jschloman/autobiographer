"""Life in Chapters page — geographic autobiography timeline with Home vs. Trip comparison.

Renders a vertical scrolling timeline of life chapters derived from the
assumptions file (residency + trips).  Each chapter card shows date range,
location, total plays, top-5 artists, discovery count, chapter-exclusive
artists, and top album.  Residency chapters that contain trip periods also
display an expandable Home vs. Trip breakdown.  A page-level summary section
compares listening behaviour across all detected trip periods.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis_utils import (
    build_life_chapters,
    compute_vacation_stats,
    detect_trip_periods,
    label_listening_context,
    load_assumptions,
)
from components.theme import (
    ACCENT_INDIGO,
    ACCENT_ORANGE,
    AMBER,
    CARD_BG,
    COLORWAY,
    TEAL,
    TEXT_DIM,
    TEXT_PRIMARY,
    apply_dark_theme,
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


def _render_on_the_road(
    df_labeled: pd.DataFrame,
    chapter_start: pd.Timestamp,
    chapter_end: pd.Timestamp,
    chapter_trips: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    """Render an expandable Home vs. Trip comparison for a residency chapter.

    Args:
        df_labeled: Full labeled listening history with a ``context`` column.
        chapter_start: Chapter start date.
        chapter_end: Chapter end date.
        chapter_trips: Trip periods that overlap this chapter's date range.
    """
    dates = df_labeled["date_text"].dt.normalize()
    mask = (dates >= chapter_start.normalize()) & (dates <= chapter_end.normalize())
    chapter_df = df_labeled[mask]

    if chapter_df.empty:
        return

    stats = compute_vacation_stats(chapter_df)
    home_s = stats.get("home", {})
    trip_s = stats.get("trip", {})

    if not trip_s:
        return

    trip_count = len(chapter_trips)
    trip_days = sum((e - s).days + 1 for s, e in chapter_trips)
    expander_label = (
        f"On the Road — {trip_count} trip{'s' if trip_count != 1 else ''}, "
        f"{trip_days} day{'s' if trip_days != 1 else ''}"
    )

    with st.expander(expander_label, expanded=False):
        col_h, col_t = st.columns(2)

        numeric_metrics = [
            ("Avg Daily Scrobbles", "avg_daily_scrobbles"),
            ("Unique Artists / Day", "unique_artists_per_day"),
        ]

        with col_h:
            st.markdown(
                f"<span style='color:{TEXT_DIM}; font-size:0.75rem; "
                f"text-transform:uppercase; font-weight:600; letter-spacing:0.05em;'>"
                f"At Home</span>",
                unsafe_allow_html=True,
            )
            for label, key in numeric_metrics:
                val = home_s.get(key, "—")
                st.metric(label, str(val) if val != "—" else "—")
            st.metric("Top Artist", str(home_s.get("top_artist", "—")))

        with col_t:
            st.markdown(
                f"<span style='color:{ACCENT_ORANGE}; font-size:0.75rem; "
                f"text-transform:uppercase; font-weight:600; letter-spacing:0.05em;'>"
                f"On Trip</span>",
                unsafe_allow_html=True,
            )
            for label, key in numeric_metrics:
                val = trip_s.get(key, "—")
                home_val = home_s.get(key)
                delta = None
                if isinstance(val, (int, float)) and isinstance(home_val, (int, float)):
                    delta = round(val - home_val, 1)
                st.metric(label, str(val) if val != "—" else "—", delta=delta)
            st.metric("Top Artist", str(trip_s.get("top_artist", "—")))


def _render_timeline_chart(
    df: pd.DataFrame,
    trip_periods: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    """Daily scrobble bar chart colored by listening context with trip periods shaded.

    Args:
        df: Labeled listening history with ``date_text`` and ``context`` columns.
        trip_periods: List of ``(start, end)`` Timestamp pairs for shading.
    """
    if "context" not in df.columns or df.empty:
        return

    daily = (
        df.groupby([df["date_text"].dt.normalize().rename("date"), "context"])
        .size()
        .reset_index(name="Plays")
    )

    if daily.empty:
        return

    color_map = {"home": ACCENT_INDIGO, "trip": ACCENT_ORANGE}
    fig = px.bar(
        daily,
        x="date",
        y="Plays",
        color="context",
        color_discrete_map=color_map,
        title="Daily Scrobbles — Home vs. Trip",
        labels={"context": "Context", "date": ""},
    )
    for start, end in trip_periods:
        fig.add_vrect(
            x0=str(start.date()),
            x1=str(end.date()),
            fillcolor=ACCENT_ORANGE,
            opacity=0.08,
            line_width=0,
        )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_discovery_chart(df: pd.DataFrame) -> None:
    """Bar chart comparing new-artist discovery rate between Home and Trip contexts.

    Args:
        df: Labeled listening history with ``date_text``, ``artist``, and
            ``context`` columns.
    """
    if "artist" not in df.columns or "context" not in df.columns or df.empty:
        return

    records = []
    for ctx, sub in df.groupby("context"):
        sub = sub.sort_values("date_text")
        seen: set[str] = set()
        for _, day_df in sub.groupby(sub["date_text"].dt.normalize()):
            artists_today = set(day_df["artist"].dropna())
            new_artists = artists_today - seen
            seen |= artists_today
            records.append(
                {
                    "context": ctx,
                    "new_artists": len(new_artists),
                    "total_plays": len(day_df),
                }
            )

    if not records:
        return

    disc = pd.DataFrame(records)
    disc["discovery_rate"] = disc["new_artists"] / disc["total_plays"].clip(lower=1)
    summary = disc.groupby("context")["discovery_rate"].mean().reset_index()
    summary.columns = pd.Index(["context", "Avg Discovery Rate"])
    summary["Context"] = summary["context"].str.capitalize()

    color_map = {"home": ACCENT_INDIGO, "trip": ACCENT_ORANGE}
    fig = px.bar(
        summary,
        x="Context",
        y="Avg Discovery Rate",
        color="context",
        color_discrete_map=color_map,
        title="New-Artist Discovery Rate — Home vs. Trip",
        labels={"context": "Context"},
    )
    fig.update_layout(showlegend=False, colorway=COLORWAY)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_home_vs_trip_summary(
    df_labeled: pd.DataFrame,
    trip_periods: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    """Render the page-level Home vs. Trip summary section.

    Shows aggregate stat cards for home and trip contexts, a daily scrobble
    timeline coloured by context, and a discovery-rate comparison chart.

    Args:
        df_labeled: Full labeled listening history.
        trip_periods: All detected trip periods.
    """
    stats = compute_vacation_stats(df_labeled)
    home = stats.get("home", {})
    trip = stats.get("trip", {})

    if not home or not trip:
        return

    st.divider()
    st.subheader("Home vs. Trip")
    st.caption("How your listening shifts when you travel, across all chapters.")

    col_h, col_t = st.columns(2)
    numeric_metrics = [
        ("Avg Daily Scrobbles", "avg_daily_scrobbles"),
        ("Unique Artists / Day", "unique_artists_per_day"),
        ("Estimated Hours", "listening_hours"),
    ]

    with col_h:
        with st.container(border=True):
            st.subheader(":material/home: At Home")
            for label, key in numeric_metrics:
                val = home.get(key, "—")
                st.metric(label, str(val) if val != "—" else "—")
            st.metric("Top Artist", str(home.get("top_artist", "—")))

    with col_t:
        with st.container(border=True):
            st.subheader(":material/flight_takeoff: On Trip")
            for label, key in numeric_metrics:
                val = trip.get(key, "—")
                home_val = home.get(key)
                delta = None
                if isinstance(val, (int, float)) and isinstance(home_val, (int, float)):
                    delta = round(val - home_val, 1)
                st.metric(label, str(val) if val != "—" else "—", delta=delta)
            st.metric("Top Artist", str(trip.get("top_artist", "—")))

    col_timeline, col_discovery = st.columns(2)
    with col_timeline:
        _render_timeline_chart(df_labeled, trip_periods)
    with col_discovery:
        _render_discovery_chart(df_labeled)


def _render_chapter_card(
    chapter: dict[str, Any],
    index: int,
    total: int,
    df_labeled: pd.DataFrame,
    trip_periods: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    """Render a single chapter as a styled Streamlit card with a connector line.

    Trip chapters use an orange accent; residency chapters use indigo.
    Residency chapters that contain trip periods include an expandable
    Home vs. Trip breakdown.

    Args:
        chapter: Chapter dict from ``build_life_chapters()``.
        index: Zero-based position of this chapter in the list.
        total: Total number of chapters (used to suppress the trailing line).
        df_labeled: Full labeled listening history for the comparison section.
        trip_periods: All trip periods detected for the page.
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
    is_trip = chapter.get("kind") == "trip"
    accent = ACCENT_ORANGE if is_trip else ACCENT_INDIGO

    date_str = _format_date_range(start, end)
    duration = _duration_label(start, end)

    # ── Connector line above each card (except the first) ───────────────────
    if index > 0:
        st.markdown(
            f"""
            <div style="display:flex; justify-content:center; margin: 0; padding: 0;">
              <div style="width:2px; height:32px; background:{accent}; opacity:0.5;"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Chapter bullet ───────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
          <div style="width:14px; height:14px; border-radius:50%;
                      background:{accent}; flex-shrink:0; margin:auto;
                      box-shadow: 0 0 0 3px {CARD_BG}, 0 0 0 5px {accent}44;"></div>
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

        if top_artists:
            st.markdown("**Top Artists**")
            artist_cols = st.columns(min(len(top_artists), 5))
            for i, (col, artist) in enumerate(zip(artist_cols, top_artists)):
                rank_color = accent if i == 0 else TEXT_DIM
                col.markdown(
                    f"<div style='text-align:center;'>"
                    f"<span style='color:{rank_color}; font-weight:700; font-size:0.9rem;'>"
                    f"#{i + 1}</span><br>"
                    f"<span style='font-size:0.8rem; color:{TEXT_PRIMARY};'>{artist}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # On the Road section — residency chapters that contain trip periods only
        if not is_trip and trip_periods and not df_labeled.empty:
            chapter_trips = [(s, e) for s, e in trip_periods if s <= end and e >= start]
            if chapter_trips:
                _render_on_the_road(df_labeled, start, end, chapter_trips)


def render_life_in_chapters() -> None:
    """Render the Life in Chapters geographic autobiography timeline page.

    Reads listening history from ``st.session_state['df']`` and the
    assumptions file path from ``st.session_state['_loaded_config']``.
    Shows an empty state when no data has been loaded or no assumptions
    file is configured.  Trip chapters are rendered with an orange accent;
    residency chapters with indigo.  A page-level Home vs. Trip section
    appears below the timeline when trip periods are present.
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

    # Detect trip periods and label the full listening history
    swarm_df: pd.DataFrame | None = st.session_state.get("swarm_df")
    trip_periods = detect_trip_periods(
        assumptions,
        swarm_df=swarm_df if swarm_df is not None else pd.DataFrame(),
    )
    df_labeled = label_listening_context(df, trip_periods)

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
        _render_chapter_card(chapter, i, len(chapters), df_labeled, trip_periods)

    # Trailing connector end-cap
    st.markdown(
        f"""
        <div style="display:flex; justify-content:center; margin: 0; padding: 0;">
          <div style="width:2px; height:20px; background:{ACCENT_INDIGO}; opacity:0.3;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Home vs. Trip summary ─────────────────────────────────────────────────
    if trip_periods:
        _render_home_vs_trip_summary(df_labeled, trip_periods)
