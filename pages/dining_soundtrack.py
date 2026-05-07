"""Dining Soundtrack page — music listened to around food and drink check-ins.

Matches Foursquare/Swarm check-ins at food and drink venues with Last.fm
listens in a ±2 hour window, then groups the results by venue category to
show top artists, average plays, and the most common listening hour.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from analysis_utils import get_top_entities
from components.theme import (
    ACCENT_INDIGO,
    AMBER,
    COLORWAY,
    TEAL,
    apply_dark_theme,
)

# ---------------------------------------------------------------------------
# Category taxonomy — maps partial Foursquare category name substrings to
# the four display buckets shown in the venue grid.
# ---------------------------------------------------------------------------

#: The four venue buckets displayed on the page.
FOOD_DRINK_CATEGORIES: list[str] = [
    "Restaurants",
    "Bars & Nightlife",
    "Cafes",
    "Fast Food",
]

# Ordered list of (substring, bucket) rules; first match wins.
_CATEGORY_RULES: list[tuple[str, str]] = [
    # Fast food — check before "restaurant" to avoid false positive
    ("fast food", "Fast Food"),
    ("burger", "Fast Food"),
    ("pizza", "Fast Food"),
    ("fried chicken", "Fast Food"),
    ("hot dog", "Fast Food"),
    ("sandwich", "Fast Food"),
    # Bars & Nightlife
    ("bar", "Bars & Nightlife"),
    ("nightclub", "Bars & Nightlife"),
    ("pub", "Bars & Nightlife"),
    ("brewery", "Bars & Nightlife"),
    ("wine", "Bars & Nightlife"),
    ("cocktail", "Bars & Nightlife"),
    ("lounge", "Bars & Nightlife"),
    ("club", "Bars & Nightlife"),
    # Cafes
    ("cafe", "Cafes"),
    ("café", "Cafes"),
    ("coffee", "Cafes"),
    ("tea room", "Cafes"),
    ("bakery", "Cafes"),
    ("dessert", "Cafes"),
    ("ice cream", "Cafes"),
    ("juice bar", "Cafes"),
    # General restaurants — broadest bucket, checked last
    ("restaurant", "Restaurants"),
    ("diner", "Restaurants"),
    ("food", "Restaurants"),
    ("sushi", "Restaurants"),
    ("ramen", "Restaurants"),
    ("noodle", "Restaurants"),
    ("steakhouse", "Restaurants"),
    ("bbq", "Restaurants"),
    ("seafood", "Restaurants"),
    ("bistro", "Restaurants"),
    ("brasserie", "Restaurants"),
    ("tapas", "Restaurants"),
    ("dim sum", "Restaurants"),
    ("buffet", "Restaurants"),
    ("grill", "Restaurants"),
    ("kitchen", "Restaurants"),
    ("eatery", "Restaurants"),
]

# Window size for listening matching (±hours)
_WINDOW_HOURS: int = 2
_WINDOW_SEC: int = _WINDOW_HOURS * 3600


def _classify_venue_category(raw_category: str) -> str | None:
    """Map a raw Foursquare category name to one of the four display buckets.

    The match is case-insensitive substring search; the first rule that matches
    wins.  Returns ``None`` for venue types that are not food or drink related.

    Args:
        raw_category: Raw category string from the Foursquare export (e.g.
            ``"Italian Restaurant"``).

    Returns:
        One of the four :data:`FOOD_DRINK_CATEGORIES` strings, or ``None``.
    """
    lower = raw_category.lower()
    for substring, bucket in _CATEGORY_RULES:
        if substring in lower:
            return bucket
    return None


def _get_listens_around_checkin(
    lastfm_df: pd.DataFrame,
    checkin_ts: int,
    window_hours: int = _WINDOW_HOURS,
) -> pd.DataFrame:
    """Return Last.fm listens within ±``window_hours`` of a check-in timestamp.

    Args:
        lastfm_df: Full listening history DataFrame with a ``timestamp`` column.
        checkin_ts: Unix timestamp of the Swarm check-in.
        window_hours: Symmetric window size in hours (default 2).

    Returns:
        Subset of ``lastfm_df`` whose ``timestamp`` falls within
        ``[checkin_ts - window_sec, checkin_ts + window_sec]``.
    """
    if lastfm_df.empty or "timestamp" not in lastfm_df.columns:
        return pd.DataFrame()
    window_sec = window_hours * 3600
    mask = (lastfm_df["timestamp"] >= checkin_ts - window_sec) & (
        lastfm_df["timestamp"] <= checkin_ts + window_sec
    )
    return lastfm_df[mask]


def get_dining_soundtrack_data(
    swarm_df: pd.DataFrame,
    lastfm_df: pd.DataFrame,
    top_n: int = 5,
    window_hours: int = _WINDOW_HOURS,
) -> dict[str, dict[str, Any]]:
    """Aggregate Last.fm listens around food/drink check-ins by venue category.

    For each Swarm check-in whose category maps to a food/drink bucket,
    collects all Last.fm listens within ``±window_hours``.  Groups by bucket
    and computes top artists, total listen count, check-in count, and peak
    listening hour.

    Args:
        swarm_df: Swarm DataFrame with ``timestamp`` and ``venue_category``
            columns (as returned by :func:`analysis_utils.load_swarm_data`).
        lastfm_df: Listening history DataFrame with ``timestamp``, ``artist``,
            and ``date_text`` columns.
        top_n: Maximum number of top artists to return per category (default 5).
        window_hours: Symmetric window around each check-in in hours (default 2).

    Returns:
        Dict keyed by venue category bucket.  Each value is a dict with:
        ``top_artists`` (DataFrame), ``checkin_count`` (int),
        ``listen_count`` (int), and ``peak_hour`` (int or None).
    """
    if swarm_df.empty or lastfm_df.empty:
        return {}

    required_swarm = {"timestamp", "venue_category"}
    required_lastfm = {"timestamp", "artist"}
    if not required_swarm.issubset(swarm_df.columns) or not required_lastfm.issubset(
        lastfm_df.columns
    ):
        return {}

    # Bucket all food/drink check-ins
    bucket_listens: dict[str, list[pd.DataFrame]] = {cat: [] for cat in FOOD_DRINK_CATEGORIES}
    bucket_checkin_count: dict[str, int] = {cat: 0 for cat in FOOD_DRINK_CATEGORIES}

    for _, row in swarm_df.iterrows():
        bucket = _classify_venue_category(str(row.get("venue_category", "")))
        if bucket is None:
            continue
        nearby = _get_listens_around_checkin(lastfm_df, int(row["timestamp"]), window_hours)
        if not nearby.empty:
            bucket_listens[bucket].append(nearby)
        bucket_checkin_count[bucket] += 1

    results: dict[str, dict[str, Any]] = {}
    for cat in FOOD_DRINK_CATEGORIES:
        if bucket_checkin_count[cat] == 0:
            continue  # no check-ins in this category
        frames = bucket_listens[cat]
        if not frames:
            continue  # check-ins exist but no nearby listens
        combined = pd.concat(frames, ignore_index=True).drop_duplicates()
        top_artists = get_top_entities(combined, "artist", limit=top_n)

        peak_hour: int | None = None
        if "date_text" in combined.columns and not combined["date_text"].isna().all():
            hour_counts = combined["date_text"].dt.hour.value_counts()
            peak_hour = int(hour_counts.idxmax()) if not hour_counts.empty else None

        results[cat] = {
            "top_artists": top_artists,
            "checkin_count": bucket_checkin_count[cat],
            "listen_count": len(combined),
            "peak_hour": peak_hour,
        }

    return results


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

_CATEGORY_COLORS: dict[str, str] = {
    "Restaurants": ACCENT_INDIGO,
    "Bars & Nightlife": AMBER,
    "Cafes": TEAL,
    "Fast Food": "#a855f7",  # purple accent
}


def render_dining_soundtrack() -> None:
    """Render the Dining Soundtrack page.

    Reads ``st.session_state['df']`` (Last.fm listens) and
    ``st.session_state['swarm_df']`` (Swarm check-ins).  Shows an empty state
    message when either dataset is missing or when no food/drink venues with
    nearby listens are found.
    """
    df: pd.DataFrame | None = st.session_state.get("df")
    swarm_df: pd.DataFrame | None = st.session_state.get("swarm_df")

    st.header("Dining Soundtrack")

    if df is None or df.empty or swarm_df is None or swarm_df.empty:
        st.info(
            "Both Last.fm and Foursquare/Swarm data are required. "
            "Configure both sources in the sidebar."
        )
        return

    with st.spinner("Matching listens to check-ins…"):
        category_data = get_dining_soundtrack_data(swarm_df, df)

    if not category_data:
        st.info(
            "No food or drink check-ins with nearby listens found. "
            "Make sure your Swarm export includes venue categories."
        )
        return

    st.markdown(
        f"Showing Last.fm listens within **±{_WINDOW_HOURS} hours** "
        "of Foursquare/Swarm food and drink check-ins."
    )

    # ── Summary metric row ─────────────────────────────────────────────────
    cols = st.columns(len(FOOD_DRINK_CATEGORIES))
    for col, cat in zip(cols, FOOD_DRINK_CATEGORIES):
        with col:
            if cat in category_data:
                data = category_data[cat]
                st.metric(
                    cat,
                    f"{data['listen_count']:,} listens",
                    delta=f"{data['checkin_count']} check-ins",
                )
            else:
                st.metric(cat, "—")

    st.divider()

    # ── Per-category grid ──────────────────────────────────────────────────
    for cat in FOOD_DRINK_CATEGORIES:
        if cat not in category_data:
            continue
        data = category_data[cat]
        top_artists: pd.DataFrame = data["top_artists"]
        color = _CATEGORY_COLORS.get(cat, ACCENT_INDIGO)

        st.subheader(cat)
        col_chart, col_stats = st.columns([2, 1])

        with col_chart:
            if not top_artists.empty:
                fig = px.bar(
                    top_artists,
                    x="Plays",
                    y="artist",
                    orientation="h",
                    title=f"Top Artists at {cat}",
                    color_discrete_sequence=[color],
                )
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                apply_dark_theme(fig)
                st.plotly_chart(fig, width="stretch")
            else:
                st.caption("No artist data available.")

        with col_stats:
            st.metric("Check-ins", data["checkin_count"])
            st.metric("Listens matched", data["listen_count"])
            if data["peak_hour"] is not None:
                st.metric("Peak hour", f"{data['peak_hour']:02d}:00")
            if not top_artists.empty:
                top_name = str(top_artists.iloc[0]["artist"])
                st.caption(f"Top artist: **{top_name}**")

        st.divider()

    # ── Cross-category comparison chart ───────────────────────────────────
    if len(category_data) > 1:
        st.subheader("Category Comparison")
        summary_rows = [
            {
                "Category": cat,
                "Listens": data["listen_count"],
                "Check-ins": data["checkin_count"],
            }
            for cat, data in category_data.items()
        ]
        summary_df = pd.DataFrame(summary_rows)
        fig_cmp = px.bar(
            summary_df,
            x="Category",
            y="Listens",
            color="Category",
            title="Total Listens per Venue Category",
            color_discrete_sequence=COLORWAY,
        )
        apply_dark_theme(fig_cmp)
        st.plotly_chart(fig_cmp, width="stretch")
