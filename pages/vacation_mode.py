"""Vacation Mode page — how listening behaviour changes on trips vs. at home."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis_utils import (
    compute_vacation_stats,
    detect_trip_periods,
    get_listening_intensity,
    label_listening_context,
)
from components.theme import (
    ACCENT_INDIGO,
    ACCENT_ORANGE,
    COLORWAY,
    apply_dark_theme,
    card_container,
)


def render_stat_cards(stats: dict) -> None:
    """Render side-by-side metric cards for Home vs. Trip contexts.

    Args:
        stats: Output of :func:`~analysis_utils.compute_vacation_stats` — a
            dict keyed by ``'home'`` and ``'trip'``, each containing a metric
            sub-dict.
    """
    home = stats.get("home", {})
    trip = stats.get("trip", {})

    if not home and not trip:
        st.info("No data to compare — load listening history and configure trip periods.")
        return

    metrics = [
        ("Avg Daily Scrobbles", "avg_daily_scrobbles"),
        ("Unique Artists / Day", "unique_artists_per_day"),
        ("Estimated Hours", "listening_hours"),
        ("Top Artist", "top_artist"),
    ]

    col_home, col_trip = st.columns(2)
    with col_home:
        with card_container():
            st.subheader("Home")
            for label, key in metrics:
                raw = home.get(key, "—")
                st.metric(label, str(raw) if raw != "—" else "—")
    with col_trip:
        with card_container():
            st.subheader("Trip")
            for label, key in metrics:
                raw = trip.get(key, "—")
                st.metric(label, str(raw) if raw != "—" else "—")


def render_timeline_chart(
    df: pd.DataFrame,
    trip_periods: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> None:
    """Render a daily scrobble bar chart with trip periods shaded.

    Args:
        df: Full listening history with ``date_text`` and ``context`` columns.
        trip_periods: List of ``(start, end)`` Timestamp pairs.
    """
    intensity = get_listening_intensity(df, "D")
    if intensity.empty:
        return

    # Colour bars by context
    intensity["date_ts"] = pd.to_datetime(intensity["date"])
    intensity["context"] = "home"
    for start, end in trip_periods:
        mask = (intensity["date_ts"] >= start) & (intensity["date_ts"] <= end)
        intensity.loc[mask, "context"] = "trip"

    color_map = {"home": ACCENT_INDIGO, "trip": ACCENT_ORANGE}

    fig = px.bar(
        intensity,
        x="date",
        y="Plays",
        color="context",
        color_discrete_map=color_map,
        title="Daily Scrobbles — Home vs. Trip",
        labels={"context": "Context", "date": ""},
    )
    # Add shaded vrects for each trip period
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


def render_genre_comparison(df: pd.DataFrame) -> None:
    """Render a horizontal bar chart comparing top artists between Home and Trip.

    Args:
        df: Listening history with ``artist`` and ``context`` columns.
    """
    if "artist" not in df.columns or "context" not in df.columns:
        return

    top_n = 10
    home_df = df[df["context"] == "home"]
    trip_df = df[df["context"] == "trip"]

    if home_df.empty or trip_df.empty:
        return

    home_counts = home_df["artist"].value_counts().head(top_n).rename("home")
    trip_counts = trip_df["artist"].value_counts().head(top_n).rename("trip")

    all_artists = list(dict.fromkeys(home_counts.index.tolist() + trip_counts.index.tolist()))
    compare = pd.DataFrame(index=all_artists)
    compare["home"] = home_counts.reindex(all_artists).fillna(0)
    compare["trip"] = trip_counts.reindex(all_artists).fillna(0)
    compare = compare.sort_values("home", ascending=False).head(top_n)

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Home",
            y=compare.index.tolist(),
            x=compare["home"].tolist(),
            orientation="h",
            marker_color=ACCENT_INDIGO,
        )
    )
    fig.add_trace(
        go.Bar(
            name="Trip",
            y=compare.index.tolist(),
            x=compare["trip"].tolist(),
            orientation="h",
            marker_color=ACCENT_ORANGE,
        )
    )
    fig.update_layout(
        barmode="group",
        title="Artist Plays — Home vs. Trip",
        yaxis={"categoryorder": "total ascending"},
        colorway=COLORWAY,
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_discovery_chart(df: pd.DataFrame) -> None:
    """Render a bar chart comparing daily new-artist discovery rate by context.

    A 'new' artist on a given day is one that has not appeared in the
    listening history before that date within the context group.

    Args:
        df: Listening history sorted by ``date_text`` with ``artist`` and
            ``context`` columns.
    """
    if "artist" not in df.columns or "context" not in df.columns or df.empty:
        return

    records = []
    for ctx, sub in df.groupby("context"):
        sub = sub.sort_values("date_text")
        seen: set[str] = set()
        day_groups = sub.groupby(sub["date_text"].dt.normalize())
        for day, day_df in day_groups:
            artists_today = set(day_df["artist"].dropna().tolist())
            new_artists = artists_today - seen
            seen |= artists_today
            records.append(
                {
                    "date": day,
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
    summary.columns = ["context", "Avg Discovery Rate"]
    summary["Context"] = summary["context"].str.capitalize()

    color_map = {"home": ACCENT_INDIGO, "trip": ACCENT_ORANGE}

    fig = px.bar(
        summary,
        x="Context",
        y="Avg Discovery Rate",
        color="context",
        color_discrete_map=color_map,
        title="New-Artist Discovery Rate by Context",
        labels={"context": "Context"},
    )
    fig.update_layout(showlegend=False)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_vacation_mode() -> None:
    """Render the Vacation Mode page.

    Reads ``st.session_state['df']`` (Last.fm data) and
    ``st.session_state['assumptions']`` (loaded assumptions).  Swarm data is
    read from ``st.session_state.get('swarm_df')`` when available.

    Shows an empty state when no listening data has been loaded.
    """
    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    assumptions: dict = st.session_state.get("assumptions", {})
    swarm_df: pd.DataFrame | None = st.session_state.get("swarm_df")

    st.header("Vacation Mode")
    st.caption(
        "How does your listening change when you travel? "
        "Trip periods are detected from your assumptions file and Swarm check-ins."
    )

    # --- Detect trip periods ---
    trip_periods = detect_trip_periods(
        assumptions,
        swarm_df=swarm_df if swarm_df is not None else pd.DataFrame(),
    )

    if not trip_periods:
        st.warning(
            "No trip periods detected. "
            "Add trips to your assumptions file or load Swarm check-in data."
        )
        # Still render basic stats with home-only data
        df_labeled = label_listening_context(df, [])
    else:
        df_labeled = label_listening_context(df, trip_periods)

    # --- Summary cards ---
    st.subheader("Summary")
    stats = compute_vacation_stats(df_labeled)
    render_stat_cards(stats)

    if not trip_periods:
        return

    # --- Timeline ---
    st.divider()
    st.subheader("Listening Timeline")
    render_timeline_chart(df_labeled, trip_periods)

    # --- Artist comparison ---
    st.divider()
    st.subheader("Artist Comparison")
    col1, col2 = st.columns(2)
    with col1:
        render_genre_comparison(df_labeled)
    with col2:
        render_discovery_chart(df_labeled)

    # --- Trip list ---
    st.divider()
    st.subheader("Detected Trip Periods")
    trip_rows = [
        {
            "Start": str(s.date()),
            "End": str(e.date()),
            "Days": (e - s).days + 1,
        }
        for s, e in trip_periods
    ]
    st.dataframe(pd.DataFrame(trip_rows), use_container_width=True, hide_index=True)

    trip_count = len(df_labeled[df_labeled["context"] == "trip"])
    home_count = len(df_labeled[df_labeled["context"] == "home"])
    total = trip_count + home_count
    if total:
        pct = round(trip_count / total * 100, 1)
        st.caption(
            f"{trip_count:,} scrobbles on trips ({pct}%) · "
            f"{home_count:,} at home across {len(trip_periods)} trip period(s)."
        )
