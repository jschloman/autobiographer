"""Late Night Sessions page — listening after midnight by location (issue #68).

Night-sky aesthetic.  Surfaces:
- Top-20 late-night artists (midnight–4 AM local time)
- City dot map with glow effect
- Late-night play rate per location type (home / hotel / trip)
- Hourly clock highlighting midnight–4 AM slice vs. full day
- "Latest session" — most extreme consecutive late-night streak
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.theme import (
    ACCENT_CYAN,
    ACCENT_INDIGO,
    ACCENT_PURPLE,
    TEXT_DIM,
    apply_dark_theme,
)

# Local hours considered "late night" (0 inclusive, 4 exclusive).
_LATE_NIGHT_START = 0
_LATE_NIGHT_END = 4  # exclusive: hours 0, 1, 2, 3

# Maximum gap in minutes between consecutive plays within one session.
_SESSION_GAP_MINUTES = 30

# Colour constants for the night-sky aesthetic.
_GLOW_COLOUR = "rgba(99, 102, 241, 0.55)"  # indigo glow for dot map
_LATE_COLOUR = ACCENT_INDIGO  # bars for midnight–4 AM window
_DAY_COLOUR = "rgba(139, 148, 167, 0.4)"  # muted colour for rest of day


def _filter_late_night(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where the local hour falls in the midnight–4 AM window.

    Args:
        df: Listening history with a ``date_text`` column (local time).

    Returns:
        Filtered DataFrame; empty when no late-night rows exist.
    """
    if df.empty or "date_text" not in df.columns:
        return pd.DataFrame()
    mask = (df["date_text"].dt.hour >= _LATE_NIGHT_START) & (
        df["date_text"].dt.hour < _LATE_NIGHT_END
    )
    return df[mask]


def get_top_late_night_artists(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Return the top ``limit`` artists by late-night play count.

    Only scrobbles recorded between midnight and 4 AM (local time) are
    considered.

    Args:
        df: Full listening history DataFrame with ``date_text`` and ``artist``.
        limit: Maximum number of artists to return.

    Returns:
        DataFrame with columns ``artist`` and ``plays``, sorted descending.
    """
    late = _filter_late_night(df)
    if late.empty or "artist" not in late.columns:
        return pd.DataFrame(columns=["artist", "plays"])
    counts = late["artist"].value_counts().head(limit).reset_index()
    counts.columns = ["artist", "plays"]
    return counts


def get_late_night_by_city(df: pd.DataFrame) -> pd.DataFrame:
    """Return late-night play counts grouped by city with lat/lng.

    Args:
        df: Listening history with ``date_text``, ``city``, ``lat``, ``lng``.

    Returns:
        DataFrame with columns ``city``, ``lat``, ``lng``, ``plays`` sorted
        descending by play count.  Empty when no late-night plays exist.
    """
    late = _filter_late_night(df)
    if late.empty or "city" not in late.columns:
        return pd.DataFrame(columns=["city", "lat", "lng", "plays"])
    groups = ["city"]
    if "lat" in late.columns and "lng" in late.columns:
        groups = ["city", "lat", "lng"]
    result = late.groupby(groups).size().reset_index(name="plays")
    return result.sort_values("plays", ascending=False).reset_index(drop=True)


def get_late_night_by_location_type(df: pd.DataFrame) -> pd.DataFrame:
    """Compute late-night rate per inferred location type.

    Location type is inferred from the city name heuristic:
    - "hotel" / "inn" / "hostel" anywhere in the city string → "Hotel"
    - Otherwise: if the city appears in both late-night and daytime plays the
      ratio determines the label; all cities without a hotel keyword are
      grouped as either "Home" (city most frequently seen) or "Trip" (others).

    The result contains one row per inferred type with ``plays`` (total
    late-night plays) and ``rate`` (late-night plays / all plays for that
    type, 0–1).

    Args:
        df: Listening history with ``date_text`` and ``city``.

    Returns:
        DataFrame with columns ``location_type``, ``plays``, ``rate``.
        Empty when input is empty or lacks required columns.
    """
    if df.empty or "date_text" not in df.columns or "city" not in df.columns:
        return pd.DataFrame(columns=["location_type", "plays", "rate"])

    late = _filter_late_night(df)
    if late.empty:
        return pd.DataFrame(columns=["location_type", "plays", "rate"])

    # Infer type for each city.
    def _infer_type(city: str, home_city: str) -> str:
        city_lower = city.lower()
        if any(k in city_lower for k in ("hotel", "inn", "hostel", "motel")):
            return "Hotel"
        if city == home_city:
            return "Home"
        return "Trip"

    # The most-played city across all hours is treated as "home".
    home_city: str = str(df["city"].mode().iloc[0]) if not df.empty else ""

    late = late.copy()
    late["location_type"] = late["city"].astype(str).apply(lambda c: _infer_type(c, home_city))

    all_df = df.copy()
    all_df["location_type"] = all_df["city"].astype(str).apply(lambda c: _infer_type(c, home_city))

    late_counts = late.groupby("location_type").size().rename("plays")
    all_counts = all_df.groupby("location_type").size().rename("total")

    result = pd.concat([late_counts, all_counts], axis=1).fillna(0).reset_index()
    result.columns = ["location_type", "plays", "total"]
    result["rate"] = (result["plays"] / result["total"].replace(0, 1)).round(3)
    result["plays"] = result["plays"].astype(int)
    return result.sort_values("plays", ascending=False).reset_index(drop=True)


def get_late_night_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Return hourly play counts for all 24 hours with a late-night flag.

    Args:
        df: Listening history with ``date_text``.

    Returns:
        DataFrame with columns ``hour`` (0–23), ``plays`` (int), and
        ``is_late_night`` (bool) — True for hours 0–3.
    """
    all_hours = pd.DataFrame({"hour": range(24)})
    if df.empty or "date_text" not in df.columns:
        all_hours["plays"] = 0
        all_hours["is_late_night"] = all_hours["hour"] < _LATE_NIGHT_END
        return all_hours

    hourly = (
        df.assign(hour=df["date_text"].dt.hour).groupby("hour").size().reset_index(name="plays")
    )
    merged = all_hours.merge(hourly, on="hour", how="left").fillna(0)
    merged["plays"] = merged["plays"].astype(int)
    merged["is_late_night"] = merged["hour"] < _LATE_NIGHT_END
    return merged


def find_latest_session(df: pd.DataFrame) -> dict[str, Any] | None:
    """Find the most extreme consecutive late-night listening session.

    A "session" is defined as consecutive plays in the midnight–4 AM window
    with inter-play gaps of less than ``_SESSION_GAP_MINUTES`` minutes.
    The "latest" session is the one with the highest track count; ties are
    broken by the most recent start time.

    Args:
        df: Listening history with ``date_text``, ``timestamp``, and
            ``artist``.

    Returns:
        Dictionary with keys:
        - ``start``: session start ``pd.Timestamp``
        - ``end``: session end ``pd.Timestamp``
        - ``track_count``: number of plays in the session
        - ``artists``: list of unique artists

        Returns ``None`` when no late-night plays are present.
    """
    late = _filter_late_night(df)
    if late.empty:
        return None

    late = late.sort_values("date_text").reset_index(drop=True)

    # Compute gap to previous play (in minutes).
    gap_minutes = late["date_text"].diff().dt.total_seconds().fillna(0) / 60

    # Assign session IDs: new session whenever gap exceeds threshold.
    session_ids = (gap_minutes > _SESSION_GAP_MINUTES).cumsum()
    late = late.copy()
    late["session_id"] = session_ids

    # Aggregate sessions.
    sessions: list[dict[str, Any]] = []
    for sid, grp in late.groupby("session_id"):
        sessions.append(
            {
                "session_id": sid,
                "start": grp["date_text"].iloc[0],
                "end": grp["date_text"].iloc[-1],
                "track_count": len(grp),
                "artists": grp["artist"].dropna().unique().tolist()
                if "artist" in grp.columns
                else [],
            }
        )

    if not sessions:
        return None

    # Return the session with the most tracks (latest start for ties).
    best = sorted(sessions, key=lambda s: (s["track_count"], s["start"]), reverse=True)[0]
    return best


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_top_artists(df: pd.DataFrame) -> None:
    """Render a horizontal bar chart of top late-night artists.

    Args:
        df: Full listening history DataFrame.
    """
    top = get_top_late_night_artists(df, limit=20)
    if top.empty:
        st.caption("No late-night plays found in this dataset.")
        return

    ranked_labels = [f"#{r}  {n}" for r, n in enumerate(top["artist"], 1)]
    colors = [ACCENT_INDIGO] + [ACCENT_PURPLE] * (len(top) - 1)

    fig = go.Figure(
        go.Bar(
            x=top["plays"].tolist(),
            y=ranked_labels,
            orientation="h",
            marker_color=colors,
            text=[f"{p:,}" for p in top["plays"]],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title="Top 20 Late-Night Artists (Midnight – 4 AM)",
        yaxis={"categoryorder": "total ascending"},
        margin={"r": 80},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_city_dot_map(df: pd.DataFrame) -> None:
    """Render a scatter-geo dot map of late-night listening cities.

    Uses a glow-style opacity effect to evoke a night-sky aesthetic.

    Args:
        df: Full listening history DataFrame.
    """
    city_data = get_late_night_by_city(df)
    if city_data.empty or "lat" not in city_data.columns or "lng" not in city_data.columns:
        st.caption("No geographic data available for the city map.")
        return

    city_data = city_data.dropna(subset=["lat", "lng"])
    if city_data.empty:
        st.caption("No geographic data available for the city map.")
        return

    fig = px.scatter_geo(
        city_data,
        lat="lat",
        lon="lng",
        size="plays",
        hover_name="city",
        hover_data={"plays": True, "lat": False, "lng": False},
        title="Late-Night Listening Locations",
        size_max=40,
        color="plays",
        color_continuous_scale=[
            [0.0, "#1e1b4b"],
            [0.5, ACCENT_INDIGO],
            [1.0, ACCENT_CYAN],
        ],
    )
    fig.update_geos(
        bgcolor="rgba(0,0,0,0)",
        showland=True,
        landcolor="#0c1120",
        showocean=True,
        oceancolor="#090e1a",
        showcoastlines=True,
        coastlinecolor="#2d3a52",
        showframe=False,
    )
    fig.update_layout(
        geo={"showframe": False, "bgcolor": "rgba(0,0,0,0)"},
        coloraxis_showscale=False,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_location_type_chart(df: pd.DataFrame) -> None:
    """Render late-night play rate per location type (home / hotel / trip).

    Args:
        df: Full listening history DataFrame.
    """
    loc_data = get_late_night_by_location_type(df)
    if loc_data.empty:
        st.caption("No location-type data available.")
        return

    loc_data = loc_data.copy()
    loc_data["rate_pct"] = (loc_data["rate"] * 100).round(1)

    fig = px.bar(
        loc_data,
        x="location_type",
        y="rate_pct",
        color="location_type",
        text=loc_data["rate_pct"].astype(str) + "%",
        title="Late-Night Rate by Location Type",
        labels={"location_type": "Location Type", "rate_pct": "Late-Night %"},
        color_discrete_sequence=[ACCENT_INDIGO, ACCENT_PURPLE, ACCENT_CYAN],
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_hourly_clock(df: pd.DataFrame) -> None:
    """Render a 24-hour bar chart highlighting the midnight–4 AM window.

    Late-night hours are shown in indigo; all other hours are muted.

    Args:
        df: Full listening history DataFrame.
    """
    hourly = get_late_night_hourly(df)
    colors = [_LATE_COLOUR if h else _DAY_COLOUR for h in hourly["is_late_night"]]

    fig = go.Figure(
        go.Bar(
            x=hourly["hour"],
            y=hourly["plays"],
            marker_color=colors,
            hovertemplate="Hour %{x}:00 — %{y} plays<extra></extra>",
        )
    )
    fig.update_layout(
        title="Plays by Hour — Midnight–4 AM Highlighted",
        xaxis={"tickmode": "linear", "tick0": 0, "dtick": 2, "title": "Hour of Day"},
        yaxis={"title": "Plays"},
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_latest_session(df: pd.DataFrame) -> None:
    """Render the 'Latest Session' card showing the longest consecutive streak.

    Args:
        df: Full listening history DataFrame.
    """
    session = find_latest_session(df)
    if session is None:
        st.caption("No late-night sessions found.")
        return

    start_str = session["start"].strftime("%Y-%m-%d %H:%M")
    end_str = session["end"].strftime("%H:%M")
    duration_min = int((session["end"] - session["start"]).total_seconds() / 60)
    artists_str = ", ".join(str(a) for a in session["artists"][:5])
    if len(session["artists"]) > 5:
        artists_str += f" +{len(session['artists']) - 5} more"

    st.markdown(
        f"""
<div style="
    background: linear-gradient(135deg, #1e1b4b, #0c1120);
    border: 1px solid {ACCENT_INDIGO};
    border-radius: 12px;
    padding: 1.5rem 2rem;
    margin-bottom: 1rem;
">
    <h3 style="color: {ACCENT_CYAN}; margin-top: 0;">Latest Session</h3>
    <p style="color: #f0f4ff; font-size: 1.1rem; margin: 0.25rem 0;">
        <strong>{start_str} – {end_str}</strong>
        &nbsp;&middot;&nbsp;
        {session['track_count']} tracks
        &nbsp;&middot;&nbsp;
        {duration_min} min
    </p>
    <p style="color: {TEXT_DIM}; margin: 0.5rem 0 0 0; font-size: 0.9rem;">
        {artists_str}
    </p>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------


def render_late_night() -> None:
    """Render the Late Night Sessions page.

    Reads the active merged DataFrame from ``st.session_state['df']``.
    Shows an empty state when no data has been loaded.

    The page surfaces:
    - Top-20 late-night artists (midnight–4 AM)
    - City dot map with glow effect
    - Late-night rate per location type
    - Hourly clock with midnight–4 AM window highlighted
    - Latest session card (longest consecutive streak)
    """
    df = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    st.header("Late Night Sessions")
    subtitle = (
        f'<p style="color:{TEXT_DIM}; margin-top:-0.5rem;">'
        "Listening after midnight · Local time · Midnight – 4 AM window"
        "</p>"
    )
    st.markdown(subtitle, unsafe_allow_html=True)

    late = _filter_late_night(df)
    total_plays = len(df)
    late_plays = len(late)
    late_pct = late_plays / total_plays * 100 if total_plays else 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Late-Night Plays", f"{late_plays:,}")
    with col2:
        st.metric("% of All Plays", f"{late_pct:.1f}%")

    st.divider()

    _render_latest_session(df)

    st.divider()

    st.subheader("Top Artists")
    _render_top_artists(df)

    st.divider()

    col_map, col_type = st.columns(2)
    with col_map:
        st.subheader("Listening Locations")
        _render_city_dot_map(df)
    with col_type:
        st.subheader("By Location Type")
        _render_location_type_chart(df)

    st.divider()

    st.subheader("Hourly Breakdown")
    _render_hourly_clock(df)
