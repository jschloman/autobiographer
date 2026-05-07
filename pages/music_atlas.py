"""Music Listening Atlas page — most-played cities deep dive (issue #66).

Shows a world map with circles sized by plays per city, a sortable data table,
and a city detail card with top-10 artists when a city is selected.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from pandas import DataFrame

from analysis_utils import get_top_entities
from components.theme import (
    ACCENT_CYAN,
    ACCENT_INDIGO,
    ACCENT_ORANGE,
    BORDER,
    TEXT_DIM,
    TEXT_PRIMARY,
    apply_dark_theme,
)

# Columns required for geographic grouping.
_GEO_COLS = {"lat", "lng", "city", "country"}

# Assumed average track duration in minutes (used for estimated listening time).
_AVG_TRACK_MINUTES: float = 3.5


def _build_city_stats(df: DataFrame) -> DataFrame:
    """Aggregate per-city listening statistics from the merged DataFrame.

    Groups rows by ``city`` + ``country`` and computes play counts, unique
    artist count, top artist/track, most active hour, date range, lat/lng
    centroid, and estimated listening time.

    Args:
        df: Merged listening-history DataFrame.  Must contain ``city``,
            ``country``, ``lat``, ``lng``, ``artist``, ``track``,
            ``date_text``, and ``album`` columns.

    Returns:
        DataFrame with one row per (city, country) pair and computed stat
        columns.  Returns an empty DataFrame when input is empty or missing
        required columns.
    """
    if df.empty:
        return pd.DataFrame()

    required = {"city", "country", "lat", "lng", "artist", "track", "date_text"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    # Drop rows where geographic data is completely absent.
    geo_df = df.dropna(subset=["lat", "lng", "city"])
    if geo_df.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for (city, country), group in geo_df.groupby(["city", "country"], sort=False):
        plays = len(group)
        unique_artists = group["artist"].nunique()

        top_artist_series = group["artist"].value_counts()
        top_artist = str(top_artist_series.index[0]) if not top_artist_series.empty else ""

        top_track_series = group["track"].value_counts()
        top_track = str(top_track_series.index[0]) if not top_track_series.empty else ""

        top_album = ""
        if "album" in group.columns:
            top_album_series = group["album"].value_counts()
            top_album = str(top_album_series.index[0]) if not top_album_series.empty else ""

        most_active_hour = int(group["date_text"].dt.hour.value_counts().index[0])

        first_play = group["date_text"].min()
        last_play = group["date_text"].max()

        # Centroid lat/lng for the city (mean of all matching rows).
        lat = float(group["lat"].mean())
        lng = float(group["lng"].mean())

        checkin_count = 0
        if "swarm_checkins" in group.columns:
            checkin_count = int(group["swarm_checkins"].sum())

        rows.append(
            {
                "city": city,
                "country": country,
                "plays": plays,
                "unique_artists": unique_artists,
                "top_artist": top_artist,
                "top_track": top_track,
                "top_album": top_album,
                "most_active_hour": most_active_hour,
                "est_listening_hrs": round(plays * _AVG_TRACK_MINUTES / 60, 1),
                "first_play": first_play,
                "last_play": last_play,
                "checkin_count": checkin_count,
                "lat": lat,
                "lng": lng,
            }
        )

    result = pd.DataFrame(rows).sort_values("plays", ascending=False).reset_index(drop=True)
    return result


def _render_world_map(city_stats: DataFrame) -> None:
    """Render a Plotly scatter-geo world map with circles sized by play count.

    Args:
        city_stats: Output of ``_build_city_stats``, one row per city.
    """
    fig = px.scatter_geo(
        city_stats,
        lat="lat",
        lon="lng",
        size="plays",
        color="plays",
        hover_name="city",
        hover_data={
            "country": True,
            "plays": True,
            "unique_artists": True,
            "top_artist": True,
            "lat": False,
            "lng": False,
        },
        color_continuous_scale=[
            [0.0, ACCENT_INDIGO],
            [0.5, ACCENT_CYAN],
            [1.0, ACCENT_ORANGE],
        ],
        size_max=50,
        projection="natural earth",
        title="Plays by City",
        labels={"plays": "Plays", "unique_artists": "Unique Artists"},
    )
    fig.update_layout(
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            landcolor="#1e293b",
            oceancolor="#0c1120",
            showocean=True,
            showland=True,
            showcountries=True,
            countrycolor=BORDER,
            showframe=False,
        ),
        coloraxis_colorbar=dict(
            title=dict(text="Plays", font=dict(color=TEXT_PRIMARY)),
            tickfont=dict(color=TEXT_DIM),
        ),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, use_container_width=True)


def _render_city_detail(city: str, city_stats: DataFrame, full_df: DataFrame) -> None:
    """Render a detail card for a selected city with top-10 artists.

    Args:
        city: Name of the selected city.
        city_stats: Full city-stats table from ``_build_city_stats``.
        full_df: Raw listening history DataFrame.
    """
    row = city_stats[city_stats["city"] == city]
    if row.empty:
        return

    r = row.iloc[0]
    st.subheader(f"{city}, {r['country']}")

    # ── Key metrics ────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Plays", f"{r['plays']:,}")
    col2.metric("Est. Listening", f"{r['est_listening_hrs']} hrs")
    col3.metric("Unique Artists", f"{r['unique_artists']:,}")
    col4.metric("Most Active Hour", f"{int(r['most_active_hour']):02d}:00")

    col5, col6, col7 = st.columns(3)
    col5.metric("Top Artist", str(r["top_artist"]))
    col6.metric("Top Track", str(r["top_track"]))
    col7.metric("Top Album", str(r["top_album"]) if r["top_album"] else "—")

    # Date range
    first = r["first_play"]
    last = r["last_play"]
    if hasattr(first, "strftime"):
        st.caption(f"Date range: {first.strftime('%Y-%m-%d')} — {last.strftime('%Y-%m-%d')}")

    # ── Top-10 Artists bar chart ───────────────────────────────────────────────
    city_df = full_df[full_df["city"] == city]
    top10 = get_top_entities(city_df, entity="artist", limit=10)
    if not top10.empty:
        fig = px.bar(
            top10,
            x="Plays",
            y="artist",
            orientation="h",
            title=f"Top 10 Artists in {city}",
            labels={"artist": "Artist"},
            color="Plays",
            color_continuous_scale=[
                [0.0, ACCENT_INDIGO],
                [1.0, ACCENT_CYAN],
            ],
        )
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
            coloraxis_showscale=False,
        )
        apply_dark_theme(fig)
        st.plotly_chart(fig, use_container_width=True)


def render_music_atlas() -> None:
    """Render the Music Listening Atlas page.

    Reads the active DataFrame from ``st.session_state['df']``.  Shows an
    empty state when no data is loaded, and a geographic-data warning when the
    DataFrame has no lat/lng information.
    """
    df: DataFrame | None = st.session_state.get("df")

    st.header("Music Listening Atlas")

    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    # Require geographic data (lat/lng populated from Swarm or assumptions).
    if "lat" not in df.columns or df["lat"].isna().all():
        st.info(
            "No geographic data found. "
            "Link a Foursquare/Swarm export in the sidebar to enable the Music Atlas."
        )
        return

    city_stats = _build_city_stats(df)
    if city_stats.empty:
        st.info("No per-city data could be computed from the current dataset.")
        return

    # ── World map ──────────────────────────────────────────────────────────────
    st.subheader("World Map")
    _render_world_map(city_stats)

    # ── Sortable data table ────────────────────────────────────────────────────
    st.subheader("City Breakdown")

    display_cols = [
        "city",
        "country",
        "plays",
        "est_listening_hrs",
        "unique_artists",
        "top_artist",
        "top_track",
    ]
    available_cols = [c for c in display_cols if c in city_stats.columns]
    col_config: dict[str, object] = {
        "city": st.column_config.TextColumn("City"),
        "country": st.column_config.TextColumn("Country"),
        "plays": st.column_config.NumberColumn("Plays", format="%d"),
        "est_listening_hrs": st.column_config.NumberColumn("Est. Hours", format="%.1f"),
        "unique_artists": st.column_config.NumberColumn("Unique Artists", format="%d"),
        "top_artist": st.column_config.TextColumn("Top Artist"),
        "top_track": st.column_config.TextColumn("Top Track"),
    }
    st.dataframe(
        city_stats[available_cols],
        use_container_width=True,
        hide_index=True,
        column_config=col_config,
    )

    # ── City detail card ───────────────────────────────────────────────────────
    st.subheader("City Detail")
    city_names = city_stats["city"].tolist()
    selected_city: str | None = st.selectbox(
        "Select a city to explore",
        options=city_names,
        index=0,
        key="atlas_selected_city",
    )
    if selected_city:
        with st.container(border=True):
            _render_city_detail(selected_city, city_stats, df)
