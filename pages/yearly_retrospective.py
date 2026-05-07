"""Year in Review page — Spotify-Wrapped-style yearly listening retrospective."""

from __future__ import annotations

import calendar
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis_utils import get_listening_streaks, get_top_entities
from components.theme import (
    ACCENT_INDIGO,
    AMBER,
    LIFTED_BG,
    TEAL,
    apply_dark_theme,
    card_container,
)


def _filter_by_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Return rows where ``date_text`` falls within the given calendar year.

    Args:
        df: Full listening history DataFrame with a ``date_text`` column.
        year: Four-digit calendar year to filter to.

    Returns:
        Filtered DataFrame (may be empty if no data exists for that year).
    """
    return df[df["date_text"].dt.year == year].copy()


def _compute_new_artist_discoveries(
    full_df: pd.DataFrame,
    year_df: pd.DataFrame,
    year: int,
) -> list[str]:
    """Return the list of artists whose first-ever play falls within *year*.

    An artist is "new" if ``min(timestamp)`` across the entire dataset
    belongs to a row in the given year's slice.

    Args:
        full_df: Complete listening history DataFrame.
        year_df: Rows already filtered to *year*.
        year: The calendar year being reviewed.

    Returns:
        List of artist names first encountered in *year*.
    """
    if year_df.empty or "artist" not in full_df.columns:
        return []

    first_seen = full_df.groupby("artist")["date_text"].min()
    new_artists: list[str] = first_seen[first_seen.dt.year == year].index.tolist()
    return new_artists


def _compute_year_stats(
    full_df: pd.DataFrame,
    year_df: pd.DataFrame,
    year: int,
) -> dict[str, Any]:
    """Compute the full hero-stat dictionary for the given year.

    Args:
        full_df: Complete listening history DataFrame.
        year_df: Rows already filtered to *year*.
        year: The calendar year being reviewed.

    Returns:
        Dictionary with keys: ``total_scrobbles``, ``estimated_hours``,
        ``new_artists``, ``unique_countries``, ``top_artist``,
        ``top_track``, ``top_album``, ``longest_streak``,
        ``most_active_month``, ``most_active_month_plays``.
    """
    if year_df.empty:
        return {
            "total_scrobbles": 0,
            "estimated_hours": 0.0,
            "new_artists": 0,
            "unique_countries": 0,
            "top_artist": "—",
            "top_track": "—",
            "top_album": "—",
            "longest_streak": 0,
            "most_active_month": "—",
            "most_active_month_plays": 0,
        }

    total = len(year_df)
    estimated_hours = total * 3.5 / 60  # ~3.5 min average track length

    new_artists_list = _compute_new_artist_discoveries(full_df, year_df, year)
    new_artists_count = len(new_artists_list)

    unique_countries = int(year_df["country"].nunique()) if "country" in year_df.columns else 0

    top_artist_df = get_top_entities(year_df, "artist", limit=1)
    top_artist = str(top_artist_df.iloc[0]["artist"]) if not top_artist_df.empty else "—"

    top_track_df = get_top_entities(year_df, "track", limit=1)
    top_track = str(top_track_df.iloc[0]["track"]) if not top_track_df.empty else "—"

    top_album_df = get_top_entities(year_df, "album", limit=1)
    top_album = str(top_album_df.iloc[0]["album"]) if not top_album_df.empty else "—"

    streak_info = get_listening_streaks(year_df)
    longest_streak = int(streak_info.get("longest_streak", 0))

    # Most active month
    monthly = (
        year_df.assign(month=year_df["date_text"].dt.month)
        .groupby("month")
        .size()
        .reset_index(name="plays")
    )
    if not monthly.empty:
        peak_row = monthly.loc[monthly["plays"].idxmax()]
        peak_month_num = int(peak_row["month"])
        most_active_month = calendar.month_name[peak_month_num]
        most_active_month_plays = int(peak_row["plays"])
    else:
        most_active_month = "—"
        most_active_month_plays = 0

    return {
        "total_scrobbles": total,
        "estimated_hours": estimated_hours,
        "new_artists": new_artists_count,
        "unique_countries": unique_countries,
        "top_artist": top_artist,
        "top_track": top_track,
        "top_album": top_album,
        "longest_streak": longest_streak,
        "most_active_month": most_active_month,
        "most_active_month_plays": most_active_month_plays,
    }


def _render_hero_stats(stats: dict[str, Any]) -> None:
    """Render the top-line hero stat grid (8 metrics in two rows of 4).

    Args:
        stats: Dictionary produced by ``_compute_year_stats``.
    """
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Scrobbles", f"{stats['total_scrobbles']:,}")
    with c2:
        st.metric("Listening Time", f"{stats['estimated_hours']:.0f} h")
    with c3:
        st.metric("New Artists", f"{stats['new_artists']:,}")
    with c4:
        st.metric("Countries", f"{stats['unique_countries']:,}")

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("Top Artist", stats["top_artist"])
    with c6:
        st.metric("Top Track", stats["top_track"])
    with c7:
        st.metric("Longest Streak", f"{stats['longest_streak']} days")
    with c8:
        busiest_delta = (
            f"{stats['most_active_month_plays']:,} plays"
            if stats["most_active_month"] != "—"
            else None
        )
        st.metric("Busiest Month", stats["most_active_month"], delta=busiest_delta)


def _render_monthly_bar(year_df: pd.DataFrame, year: int) -> None:
    """Render a bar chart of monthly scrobble counts for the selected year.

    Args:
        year_df: Listening history filtered to the selected year.
        year: Four-digit calendar year (used for the chart title).
    """
    if year_df.empty:
        return

    monthly = (
        year_df.assign(month=year_df["date_text"].dt.month)
        .groupby("month")
        .size()
        .reset_index(name="Plays")
    )
    # Ensure all 12 months appear even when data is sparse
    all_months = pd.DataFrame({"month": range(1, 13)})
    monthly = all_months.merge(monthly, on="month", how="left").fillna(0)
    monthly["Plays"] = monthly["Plays"].astype(int)
    monthly["Month"] = monthly["month"].apply(lambda m: calendar.month_abbr[int(m)])

    peak_month = int(monthly.loc[monthly["Plays"].idxmax(), "month"])
    colors = [ACCENT_INDIGO if m == peak_month else LIFTED_BG for m in monthly["month"]]

    fig = go.Figure(go.Bar(x=monthly["Month"], y=monthly["Plays"], marker_color=colors))
    fig.update_layout(title=f"Monthly Listening — {year}", xaxis_title="", yaxis_title="Scrobbles")
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_top5_bars(year_df: pd.DataFrame) -> None:
    """Render three side-by-side top-5 bar charts: artists, albums, tracks.

    Args:
        year_df: Listening history filtered to the selected year.
    """
    if year_df.empty:
        return

    st.subheader("Top 5")
    entities = [("artist", "Artists"), ("album", "Albums"), ("track", "Tracks")]
    cols = st.columns(3)

    for col, (entity, label) in zip(cols, entities):
        with col:
            top = get_top_entities(year_df, entity, limit=5)
            if top.empty:
                st.caption(f"No {label.lower()} data")
                continue
            ranked = [f"#{r}  {n}" for r, n in enumerate(top[entity], 1)]
            plays = top["Plays"].tolist()
            bar_colors = [AMBER] + [LIFTED_BG] * (len(top) - 1)
            fig = go.Figure(
                go.Bar(
                    x=plays,
                    y=ranked,
                    orientation="h",
                    marker_color=bar_colors,
                    text=[f"{p:,}" for p in plays],
                    textposition="outside",
                    cliponaxis=False,
                )
            )
            fig.update_layout(
                title=f"Top {label}",
                yaxis={"categoryorder": "total ascending"},
                margin={"r": 60, "l": 10, "t": 40, "b": 10},
                height=280,
            )
            apply_dark_theme(fig)
            st.plotly_chart(fig, width="stretch")


def _render_country_map(year_df: pd.DataFrame) -> None:
    """Render a choropleth world map coloured by scrobbles per country.

    Skips rendering when no geographic data is present.

    Args:
        year_df: Listening history filtered to the selected year.
    """
    if year_df.empty or "country" not in year_df.columns:
        return

    country_counts = year_df.groupby("country").size().reset_index(name="Scrobbles")
    if country_counts.empty:
        return

    fig = px.choropleth(
        country_counts,
        locations="country",
        locationmode="country names",
        color="Scrobbles",
        title="Listening by Country",
        color_continuous_scale=[
            [0.0, "#1e1b4b"],
            [0.5, ACCENT_INDIGO],
            [1.0, TEAL],
        ],
    )
    fig.update_layout(
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            showframe=False,
            showcoastlines=True,
            coastlinecolor="#2d3a52",
            landcolor="#141c2f",
            oceancolor="#090e1a",
            showocean=True,
            lakecolor="#090e1a",
            projection_type="natural earth",
        ),
        coloraxis_colorbar=dict(title="Scrobbles"),
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        height=380,
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_new_discoveries(full_df: pd.DataFrame, year_df: pd.DataFrame, year: int) -> None:
    """Render a compact bar chart of newly discovered artists for the year.

    Shows up to 10 artists whose first-ever play falls within *year*, ranked
    by how many times they were played that year.

    Args:
        full_df: Complete listening history DataFrame.
        year_df: Listening history filtered to the selected year.
        year: The calendar year being reviewed.
    """
    new_artists = _compute_new_artist_discoveries(full_df, year_df, year)
    if not new_artists:
        st.caption("No new artist discoveries found for this year.")
        return

    new_df = year_df[year_df["artist"].isin(new_artists)]
    counts = new_df["artist"].value_counts().head(10).reset_index()
    counts.columns = ["artist", "Plays"]

    ranked = [f"#{r}  {n}" for r, n in enumerate(counts["artist"], 1)]
    colors = [TEAL] + [LIFTED_BG] * (len(counts) - 1)

    fig = go.Figure(
        go.Bar(
            x=counts["Plays"].tolist(),
            y=ranked,
            orientation="h",
            marker_color=colors,
            text=[f"{p:,}" for p in counts["Plays"].tolist()],
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title=f"New Artist Discoveries — {year}",
        yaxis={"categoryorder": "total ascending"},
        margin={"r": 60},
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_yearly_retrospective() -> None:
    """Render the Year in Review page.

    Presents a "Spotify Wrapped" style summary for the selected calendar
    year: hero stats, top-5 charts, monthly bar chart, new discoveries,
    and a choropleth world map.

    Reads the active DataFrame from ``st.session_state['df']``.
    Shows an empty state when no data has been loaded.
    """
    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    st.header("Year in Review")

    # ── Year selector ─────────────────────────────────────────────────────────
    available_years = sorted(df["date_text"].dt.year.unique().tolist(), reverse=True)
    selected_year: int = st.selectbox(
        "Year",
        options=available_years,
        index=0,
        key="retro_year",
    )

    year_df = _filter_by_year(df, selected_year)

    if year_df.empty:
        st.warning(f"No plays found for {selected_year}.")
        return

    # ── Hero stats ────────────────────────────────────────────────────────────
    st.divider()
    stats = _compute_year_stats(df, year_df, selected_year)
    with card_container():
        _render_hero_stats(stats)

    # ── Top-5 bar charts ──────────────────────────────────────────────────────
    st.divider()
    with card_container():
        _render_top5_bars(year_df)

    # ── Monthly bar chart ─────────────────────────────────────────────────────
    st.divider()
    _render_monthly_bar(year_df, selected_year)

    # ── New discoveries ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("New Discoveries")
    _render_new_discoveries(df, year_df, selected_year)

    # ── World map ─────────────────────────────────────────────────────────────
    if "country" in year_df.columns and not year_df["country"].isna().all():
        st.divider()
        _render_country_map(year_df)
