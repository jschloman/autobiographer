"""Weekend Effect page — weekend vs. weekday listening by location.

Splits the listening history into four contexts based on two binary dimensions:

* **is_weekend**: Saturday/Sunday (True) vs. Monday–Friday (False)
* **is_home**: city matches the user's home city from ``assumptions["defaults"]``

A 2×2 grid summarises each context with per-cell metrics (play count, top-3
artists, new-vs-familiar ratio, peak hour).  A day×hour heatmap and per-context
genre/artist comparison bars complete the view.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis_utils import get_day_hour_heatmap
from components.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_INDIGO,
    ACCENT_ORANGE,
    COLORWAY,
    SEQUENTIAL_SCALE,
    apply_dark_theme,
)

# Human-readable labels for each of the four contexts
_CONTEXT_LABELS: dict[tuple[bool, bool], str] = {
    (False, True): "Home Weekday",
    (True, True): "Home Weekend",
    (False, False): "Away Weekday",
    (True, False): "Away Weekend",
}

# Accent colours assigned to each context card for quick visual differentiation
_CONTEXT_COLORS: dict[tuple[bool, bool], str] = {
    (False, True): ACCENT_INDIGO,
    (True, True): ACCENT_CYAN,
    (False, False): ACCENT_ORANGE,
    (True, False): ACCENT_GREEN,
}

# Display order: row 0 = Home, row 1 = Away; col 0 = Weekday, col 1 = Weekend
_GRID_ORDER: list[tuple[bool, bool]] = [
    (False, True),  # Home Weekday  — row 0, col 0
    (True, True),  # Home Weekend  — row 0, col 1
    (False, False),  # Away Weekday  — row 1, col 0
    (True, False),  # Away Weekend  — row 1, col 1
]


def _add_weekend_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``day_of_week`` (str) and ``is_weekend`` (bool) columns from ``date_text``.

    Args:
        df: Listening history with a datetime ``date_text`` column.

    Returns:
        A copy of ``df`` with two additional columns.
    """
    out = df.copy()
    out["day_of_week"] = out["date_text"].dt.day_name()
    # weekday() returns 5=Saturday, 6=Sunday
    out["is_weekend"] = out["date_text"].dt.weekday >= 5
    return out


def _add_location_context(df: pd.DataFrame, home_city: str) -> pd.DataFrame:
    """Add an ``is_home`` (bool) column comparing the track's city to *home_city*.

    Comparison is case-insensitive so minor capitalisation differences are handled.

    Args:
        df: Listening history with a ``city`` column.
        home_city: The user's home city string (from ``assumptions["defaults"]["city"]``).
                   May include ", CC" country suffix — only the part before the first
                   comma is used for matching.

    Returns:
        A copy of ``df`` with the ``is_home`` column added.
    """
    out = df.copy()
    # Extract the bare city name (strip country code suffix if present)
    bare_home = home_city.split(",")[0].strip().lower()
    out["is_home"] = out["city"].str.split(",").str[0].str.strip().str.lower() == bare_home
    return out


def _get_new_vs_familiar_ratio(current_artists: set[str], prior_artists: set[str]) -> float:
    """Compute the fraction of *current_artists* not seen in *prior_artists*.

    Args:
        current_artists: Artist names in this context slice.
        prior_artists: Artist names seen in all other contexts / the full history.

    Returns:
        Float in ``[0.0, 1.0]``.  0.0 = all familiar; 1.0 = all new.
        Returns 0.0 when *current_artists* is empty.
    """
    if not current_artists:
        return 0.0
    new_count = len(current_artists - prior_artists)
    return new_count / len(current_artists)


def _compute_context_stats(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Compute per-context statistics for all four (is_weekend × is_home) cells.

    Each returned dict contains:

    * ``is_weekend`` / ``is_home`` — context boolean flags
    * ``label`` — human-readable context name
    * ``play_count`` — total rows in this context
    * ``avg_hourly_plays`` — average plays per unique hour slot
    * ``top_artists`` — up to 3 most-played artist names
    * ``new_vs_familiar`` — fraction of artists not seen in the full dataset
    * ``peak_hour`` — hour-of-day (int) with the most plays, or None

    Args:
        df: Enriched listening history with ``is_weekend``, ``is_home``, and
            ``date_text`` columns.

    Returns:
        List of four stat dicts, one per context (in ``_GRID_ORDER`` order).
    """
    all_artists = set(df["artist"].dropna().unique())
    stats: list[dict[str, Any]] = []

    for is_weekend, is_home in _GRID_ORDER:
        mask = (df["is_weekend"] == is_weekend) & (df["is_home"] == is_home)
        subset = df[mask]
        play_count = len(subset)

        # Average hourly plays: total plays / number of distinct hour-of-day slots present
        if not subset.empty:
            hours_present = subset["date_text"].dt.hour.nunique()
            avg_hourly = play_count / max(hours_present, 1)
            top_artists = subset["artist"].value_counts().head(3).index.tolist()
            current_set = set(subset["artist"].dropna().unique())
            prior_set = all_artists - current_set
            new_ratio = _get_new_vs_familiar_ratio(current_set, prior_set)
            hour_counts = subset.groupby(subset["date_text"].dt.hour).size()
            peak_hour = int(hour_counts.idxmax()) if not hour_counts.empty else None
        else:
            avg_hourly = 0.0
            top_artists = []
            new_ratio = 0.0
            peak_hour = None

        stats.append(
            {
                "is_weekend": is_weekend,
                "is_home": is_home,
                "label": _CONTEXT_LABELS[(is_weekend, is_home)],
                "color": _CONTEXT_COLORS[(is_weekend, is_home)],
                "play_count": play_count,
                "avg_hourly_plays": avg_hourly,
                "top_artists": top_artists,
                "new_vs_familiar": new_ratio,
                "peak_hour": peak_hour,
                "subset": subset,
            }
        )

    return stats


def _render_context_card(stat: dict[str, Any]) -> None:
    """Render one context card inside the current Streamlit column.

    Displays play count, average hourly plays, top-3 artists, new-vs-familiar
    ratio, and peak hour.

    Args:
        stat: A stat dict produced by ``_compute_context_stats()``.
    """
    color = stat["color"]
    label = stat["label"]
    play_count = stat["play_count"]

    st.markdown(
        f"<div style='border-left: 4px solid {color}; padding-left: 0.75rem;'>"
        f"<strong style='color:{color}'>{label}</strong></div>",
        unsafe_allow_html=True,
    )

    if play_count == 0:
        st.caption("No plays in this context")
        return

    st.metric("Plays", f"{play_count:,}")
    st.metric("Avg Hourly Plays", f"{stat['avg_hourly_plays']:.1f}")

    if stat["top_artists"]:
        artists_str = " · ".join(stat["top_artists"])
        st.caption(f"Top artists: {artists_str}")

    peak = stat["peak_hour"]
    peak_str = f"{peak:02d}:00" if peak is not None else "—"
    st.caption(f"Peak hour: {peak_str}")

    new_pct = stat["new_vs_familiar"] * 100
    st.caption(f"New artists: {new_pct:.0f}%")


def _render_heatmap(df: pd.DataFrame, location_label: str) -> None:
    """Render a day×hour heatmap for the given subset.

    Args:
        df: Listening history slice (already filtered by location context).
        location_label: Label for the chart title.
    """
    heatmap = get_day_hour_heatmap(df)
    if heatmap.empty:
        return
    fig = px.imshow(
        heatmap,
        color_continuous_scale=SEQUENTIAL_SCALE,
        title=f"Day × Hour Heatmap — {location_label}",
        labels={"x": "Hour of Day", "y": "Day", "color": "Plays"},
        aspect="auto",
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_genre_comparison(stats: list[dict[str, Any]]) -> None:
    """Render a horizontal bar chart comparing top-artist play counts across contexts.

    Shows up to 10 artists per context stacked as grouped bars.

    Args:
        stats: List of four context stat dicts from ``_compute_context_stats()``.
    """
    rows = []
    for stat in stats:
        subset = stat["subset"]
        if subset.empty:
            continue
        top = subset["artist"].value_counts().head(10)
        for artist, count in top.items():
            rows.append({"Context": stat["label"], "Artist": artist, "Plays": count})

    if not rows:
        return

    comp_df = pd.DataFrame(rows)
    fig = px.bar(
        comp_df,
        x="Plays",
        y="Artist",
        color="Context",
        orientation="h",
        title="Top Artists by Context",
        barmode="group",
        color_discrete_sequence=COLORWAY,
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_hourly_overlay(stats: list[dict[str, Any]]) -> None:
    """Render overlapping hourly play-count lines for all four contexts.

    Args:
        stats: List of four context stat dicts from ``_compute_context_stats()``.
    """
    rows = []
    for stat in stats:
        subset = stat["subset"]
        if subset.empty:
            continue
        hourly = subset.groupby(subset["date_text"].dt.hour).size().reset_index()
        hourly.columns = ["hour", "plays"]
        hourly["context"] = stat["label"]
        rows.append(hourly)

    if not rows:
        return

    combined = pd.concat(rows, ignore_index=True)
    # Fill missing hours so each line spans 0–23
    all_contexts = combined["context"].unique()
    full_grid = pd.MultiIndex.from_product(
        [range(24), all_contexts], names=["hour", "context"]
    ).to_frame(index=False)
    combined = full_grid.merge(combined, on=["hour", "context"], how="left").fillna(0)
    combined["plays"] = combined["plays"].astype(int)

    fig = px.line(
        combined,
        x="hour",
        y="plays",
        color="context",
        title="Hourly Listening Pattern by Context",
        markers=True,
        color_discrete_sequence=COLORWAY,
        labels={"hour": "Hour of Day", "plays": "Plays", "context": "Context"},
    )
    fig.update_xaxes(tickmode="linear", tick0=0, dtick=2)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_bubble_summary(stats: list[dict[str, Any]]) -> None:
    """Render a scatter bubble chart: x=context, y=avg hourly, size=play_count.

    Args:
        stats: List of four context stat dicts from ``_compute_context_stats()``.
    """
    rows = [
        {
            "Context": s["label"],
            "Avg Hourly Plays": s["avg_hourly_plays"],
            "Total Plays": s["play_count"],
            "New Artist %": round(s["new_vs_familiar"] * 100, 1),
        }
        for s in stats
        if s["play_count"] > 0
    ]
    if not rows:
        return
    bubble_df = pd.DataFrame(rows)
    fig = go.Figure()
    for i, row in bubble_df.iterrows():
        color = _CONTEXT_COLORS[_GRID_ORDER[int(i)]]
        fig.add_trace(
            go.Scatter(
                x=[row["Context"]],
                y=[row["Avg Hourly Plays"]],
                mode="markers+text",
                marker=dict(
                    size=max(row["Total Plays"] ** 0.45, 10),
                    color=color,
                    opacity=0.85,
                    line=dict(width=1, color="white"),
                ),
                text=[f"{row['Total Plays']:,}"],
                textposition="top center",
                name=row["Context"],
                hovertemplate=(
                    f"<b>{row['Context']}</b><br>"
                    f"Total plays: {row['Total Plays']:,}<br>"
                    f"Avg hourly: {row['Avg Hourly Plays']:.1f}<br>"
                    f"New artists: {row['New Artist %']}%<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        title="Context Summary (bubble size = total plays)",
        xaxis_title="Context",
        yaxis_title="Avg Hourly Plays",
        showlegend=False,
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_weekend_effect() -> None:
    """Render the Weekend Effect page.

    Reads ``st.session_state['df']`` for listening history and
    ``st.session_state.get('assumptions', {})`` for the home-city default.

    Shows an empty state when no data has been loaded or when the ``city``
    column is absent (requires Swarm data or assumption geocoding).
    """
    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    if "city" not in df.columns:
        st.info(
            "Location data is required for the Weekend Effect view. "
            "Load Swarm check-in data or add location assumptions so each track "
            "has a city assigned."
        )
        return

    assumptions: dict[str, Any] = st.session_state.get("assumptions") or {}
    home_city: str = assumptions.get("defaults", {}).get("city", "")

    st.header("The Long Weekend Effect")
    st.markdown(
        "How does your listening change across four life contexts: "
        "**Home Weekday**, **Home Weekend**, **Away Weekday**, and **Away Weekend**?"
    )

    # Enrich the DataFrame with weekend + home flags
    enriched = _add_weekend_columns(df)
    enriched = _add_location_context(enriched, home_city)

    # Location filter — lets users narrow to a specific country
    if "country" in enriched.columns:
        countries = ["All"] + sorted(enriched["country"].dropna().unique().tolist())
        selected_country = st.selectbox("Filter by country", countries)
        if selected_country != "All":
            enriched = enriched[enriched["country"] == selected_country]

    if enriched.empty:
        st.warning("No data matches the selected filters.")
        return

    stats = _compute_context_stats(enriched)

    # ── 2×2 context grid ─────────────────────────────────────────────────────
    st.subheader("Context Snapshot")
    row1_cols = st.columns(2)
    row2_cols = st.columns(2)
    grid_cols = [row1_cols[0], row1_cols[1], row2_cols[0], row2_cols[1]]

    for col, stat in zip(grid_cols, stats):
        with col:
            _render_context_card(stat)

    st.divider()

    # ── Bubble summary ───────────────────────────────────────────────────────
    _render_bubble_summary(stats)

    st.divider()

    # ── Hourly overlay ───────────────────────────────────────────────────────
    st.subheader("Hourly Listening Patterns")
    _render_hourly_overlay(stats)

    st.divider()

    # ── Day × Hour heatmaps ──────────────────────────────────────────────────
    st.subheader("Day × Hour Heatmaps")
    hm_col1, hm_col2 = st.columns(2)
    home_data = enriched[enriched["is_home"]]
    away_data = enriched[~enriched["is_home"]]
    with hm_col1:
        _render_heatmap(home_data, "Home")
    with hm_col2:
        _render_heatmap(away_data, "Away")

    st.divider()

    # ── Genre / artist comparison bars ──────────────────────────────────────
    st.subheader("Artist Comparison Across Contexts")
    _render_genre_comparison(stats)
