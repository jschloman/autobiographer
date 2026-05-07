"""Holiday Soundtrack page — recurring annual listening patterns (issue #65).

For each holiday defined in the user's assumptions file, this page shows:
- Year-over-year total play counts (line chart)
- Artist consistency heatmap (years × top artists, coloured by play count)
- Jaccard-similarity scores between consecutive years' top-10 artist sets
- Signature song (most-played track across all years of that holiday)
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.theme import (
    ACCENT_INDIGO,
    SEQUENTIAL_SCALE,
    TEAL,
    apply_dark_theme,
)

# ---------------------------------------------------------------------------
# Pure computation helpers (tested independently)
# ---------------------------------------------------------------------------


def _build_holiday_windows(df: pd.DataFrame, holiday: dict[str, Any]) -> list[dict[str, Any]]:
    """Build per-year date windows for a recurring holiday.

    Args:
        df: Full listening-history DataFrame with a ``date_text`` column.
        holiday: Holiday definition dict with ``month`` and ``day_range`` keys.

    Returns:
        List of dicts, one per calendar year that appears in ``df``, each
        containing ``year``, ``start`` (Timestamp), and ``end`` (Timestamp).
    """
    if df.empty or "date_text" not in df.columns:
        return []

    month: int = holiday.get("month", 1)
    day_range: list[int] = holiday.get("day_range", [1, 1])
    day_start, day_end = day_range[0], day_range[1]

    years = sorted(df["date_text"].dt.year.unique())
    windows: list[dict[str, Any]] = []
    for year in years:
        try:
            start = pd.Timestamp(year=year, month=month, day=day_start)
            end = pd.Timestamp(year=year, month=month, day=day_end, hour=23, minute=59, second=59)
        except ValueError:
            # Invalid date (e.g. day 31 in a month with fewer days) — skip silently.
            continue
        windows.append({"year": int(year), "start": start, "end": end})
    return windows


def _filter_holiday(df: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    """Return rows whose ``date_text`` falls within a holiday window.

    Args:
        df: Listening history with a ``date_text`` column.
        window: Dict with ``start`` and ``end`` Timestamp keys.

    Returns:
        Filtered sub-DataFrame (may be empty).
    """
    mask = (df["date_text"] >= window["start"]) & (df["date_text"] <= window["end"])
    return df[mask]


def _year_over_year_plays(df: pd.DataFrame, windows: list[dict[str, Any]]) -> pd.DataFrame:
    """Compute total play counts per year for a list of holiday windows.

    Args:
        df: Full listening history.
        windows: Output of :func:`_build_holiday_windows`.

    Returns:
        DataFrame with columns ``year`` (int) and ``plays`` (int).
    """
    rows = []
    for w in windows:
        subset = _filter_holiday(df, w)
        rows.append({"year": w["year"], "plays": len(subset)})
    return pd.DataFrame(rows)


def _top_artists_for_year(df: pd.DataFrame, window: dict[str, Any], n: int = 10) -> set[str]:
    """Return the top-N artist names by play count within a holiday window.

    Args:
        df: Full listening history.
        window: A single year's holiday window dict.
        n: How many top artists to include.

    Returns:
        Set of artist name strings (may be smaller than ``n`` if data is sparse).
    """
    subset = _filter_holiday(df, window)
    if subset.empty or "artist" not in subset.columns:
        return set()
    return set(subset["artist"].value_counts().head(n).index.tolist())


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets.

    Args:
        set_a: First set of strings.
        set_b: Second set of strings.

    Returns:
        Float in [0, 1].  Returns 0.0 when both sets are empty.
    """
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _signature_song(df: pd.DataFrame, windows: list[dict[str, Any]]) -> str | None:
    """Find the most-played track across all holiday windows.

    Args:
        df: Full listening history.
        windows: All per-year windows for a holiday.

    Returns:
        ``"Artist — Track"`` string, or ``None`` when no data exists.
    """
    if not windows or df.empty:
        return None

    subsets = [_filter_holiday(df, w) for w in windows]
    combined = pd.concat(subsets, ignore_index=True)
    if combined.empty or "track" not in combined.columns or "artist" not in combined.columns:
        return None

    combined["_song_key"] = combined["artist"] + " — " + combined["track"]
    top = combined["_song_key"].value_counts()
    if top.empty:
        return None
    return str(top.index[0])


# ---------------------------------------------------------------------------
# Chart renderers
# ---------------------------------------------------------------------------


def _render_yoy_chart(yoy: pd.DataFrame, holiday_name: str) -> None:
    """Render the year-over-year total plays line chart.

    Args:
        yoy: DataFrame with ``year`` and ``plays`` columns.
        holiday_name: Display name of the holiday (used in the chart title).
    """
    if yoy.empty or yoy["plays"].sum() == 0:
        st.caption("No plays found for this holiday.")
        return

    fig = px.line(
        yoy,
        x="year",
        y="plays",
        markers=True,
        title=f"{holiday_name} — Total Plays by Year",
        labels={"year": "Year", "plays": "Plays"},
    )
    fig.update_traces(line_color=TEAL, marker_color=ACCENT_INDIGO, marker_size=8)
    fig.update_xaxes(dtick=1, tickformat="d")
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_artist_heatmap(
    df: pd.DataFrame, windows: list[dict[str, Any]], holiday_name: str, top_n: int = 10
) -> None:
    """Render a years × top-artists heatmap coloured by play count.

    Args:
        df: Full listening history.
        windows: Per-year holiday windows.
        holiday_name: Display name of the holiday (used in the chart title).
        top_n: Number of top artists to track across all years.
    """
    if not windows:
        return

    # Collect all holiday plays to find the globally top-N artists.
    combined = pd.concat([_filter_holiday(df, w) for w in windows], ignore_index=True)
    if combined.empty or "artist" not in combined.columns:
        st.caption("Not enough data to build artist heatmap.")
        return

    global_top = combined["artist"].value_counts().head(top_n).index.tolist()
    if not global_top:
        return

    # Build a year × artist pivot.
    records = []
    for w in windows:
        subset = _filter_holiday(df, w)
        if subset.empty:
            continue
        counts = subset[subset["artist"].isin(global_top)]["artist"].value_counts()
        for artist in global_top:
            records.append(
                {"year": w["year"], "artist": artist, "plays": int(counts.get(artist, 0))}
            )

    pivot_df = pd.DataFrame(records)
    if pivot_df.empty:
        return

    pivot = pivot_df.pivot(index="artist", columns="year", values="plays").fillna(0)

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values.tolist(),
            x=[str(c) for c in pivot.columns],
            y=pivot.index.tolist(),
            colorscale=SEQUENTIAL_SCALE,
            hoverongaps=False,
            hovertemplate="Year: %{x}<br>Artist: %{y}<br>Plays: %{z}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{holiday_name} — Artist Consistency (plays per year)",
        xaxis_title="Year",
        yaxis_title="Artist",
        yaxis={"autorange": "reversed"},
    )
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def _render_jaccard_chart(
    df: pd.DataFrame, windows: list[dict[str, Any]], holiday_name: str
) -> None:
    """Render a bar chart of year-over-year Jaccard similarities for the top-10 artists.

    Args:
        df: Full listening history.
        windows: Per-year holiday windows (must have at least 2 to show anything).
        holiday_name: Display name of the holiday.
    """
    if len(windows) < 2:
        return

    top_sets = {w["year"]: _top_artists_for_year(df, w, n=10) for w in windows}
    years_sorted = sorted(top_sets.keys())

    records = []
    for i in range(1, len(years_sorted)):
        y_prev = years_sorted[i - 1]
        y_curr = years_sorted[i]
        sim = _jaccard_similarity(top_sets[y_prev], top_sets[y_curr])
        records.append({"pair": f"{y_prev}→{y_curr}", "jaccard": round(sim, 3)})

    if not records:
        return

    sim_df = pd.DataFrame(records)
    fig = px.bar(
        sim_df,
        x="pair",
        y="jaccard",
        title=f"{holiday_name} — Artist Consistency (Jaccard Similarity, top-10)",
        labels={"pair": "Year Pair", "jaccard": "Jaccard Similarity"},
        range_y=[0, 1],
    )
    fig.update_traces(marker_color=ACCENT_INDIGO)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Page entry-point
# ---------------------------------------------------------------------------


def render_holiday_soundtrack() -> None:
    """Render the Holiday Soundtrack page.

    Reads ``st.session_state['df']`` and ``st.session_state['assumptions']``.
    Shows an empty-state info message when data or holidays are missing.
    """
    df: pd.DataFrame | None = st.session_state.get("df")
    assumptions: dict[str, Any] = st.session_state.get("assumptions") or {}
    holidays: list[dict[str, Any]] = assumptions.get("holidays", [])

    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    if not holidays:
        st.info(
            "No holidays are defined in your assumptions file. "
            "Add entries to the ``holidays`` array in your assumptions JSON to use this page."
        )
        return

    st.header("Holiday Soundtrack")

    holiday_names = [h.get("name", f"Holiday {i}") for i, h in enumerate(holidays)]
    selected_name = st.selectbox("Select Holiday", holiday_names)
    holiday_def = next((h for h in holidays if h.get("name") == selected_name), holidays[0])

    windows = _build_holiday_windows(df, holiday_def)
    yoy = _year_over_year_plays(df, windows)

    # ── Summary metrics ──────────────────────────────────────────────────────
    total_plays = int(yoy["plays"].sum()) if not yoy.empty else 0
    active_years = int((yoy["plays"] > 0).sum()) if not yoy.empty else 0
    sig_song = _signature_song(df, windows)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Holiday Plays", f"{total_plays:,}")
    with c2:
        st.metric("Years with Data", str(active_years))
    with c3:
        st.metric("Signature Song", sig_song or "—")

    st.divider()

    # ── Year-over-year line chart ─────────────────────────────────────────────
    st.subheader("Year-over-Year Plays")
    _render_yoy_chart(yoy, selected_name)

    st.divider()

    # ── Artist consistency heatmap ────────────────────────────────────────────
    st.subheader("Artist Consistency")
    _render_artist_heatmap(df, windows, selected_name, top_n=10)

    # ── Jaccard similarity chart ──────────────────────────────────────────────
    _render_jaccard_chart(df, windows, selected_name)
