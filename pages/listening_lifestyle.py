"""Listening Lifestyle page — a multi-faceted portrait of how you listen to music.

Synthesises five listening contexts into a single narrative page:

- **Your Week**          Home vs. away, weekday vs. weekend patterns
- **On the Move**        Music during transit (airports, train stations)
- **Around the Table**   Dining soundtrack (restaurants, bars, cafes)
- **After Dark**         Late-night listening, midnight–4 AM
- **Year's Traditions**  Holiday listening patterns

A Persona Banner at the top derives lifestyle trait badges from the data.
Each section is a collapsed expander: key metrics visible immediately, full
chart revealed on expansion.

All analysis runs once and is cached in ``st.session_state`` keyed by
``(id(df), id(swarm_df), hash(assumptions))``.  UI interactions (expanding
sections, scrolling) never re-trigger computation.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis_utils import (
    get_avg_plays_per_day,
    get_top_entities,
    get_transit_days,
    load_assumptions,
    split_transit_listens,
)
from components.theme import (
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_INDIGO,
    ACCENT_ORANGE,
    ACCENT_PINK,
    ACCENT_PURPLE,
    ACCENT_YELLOW,
    COLORWAY,
    TEXT_DIM,
    apply_dark_theme,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LATE_NIGHT_START = 0
_LATE_NIGHT_END = 4  # hours 0, 1, 2, 3 (exclusive upper bound)
_SESSION_GAP_MINUTES = 30
_DINING_WINDOW_HOURS = 2

_FOOD_DRINK_CATEGORIES: list[str] = [
    "Restaurants",
    "Bars & Nightlife",
    "Cafes",
    "Fast Food",
]

_CATEGORY_RULES: list[tuple[str, str]] = [
    ("fast food", "Fast Food"),
    ("burger", "Fast Food"),
    ("pizza", "Fast Food"),
    ("fried chicken", "Fast Food"),
    ("hot dog", "Fast Food"),
    ("sandwich", "Fast Food"),
    ("bar", "Bars & Nightlife"),
    ("nightclub", "Bars & Nightlife"),
    ("pub", "Bars & Nightlife"),
    ("brewery", "Bars & Nightlife"),
    ("wine", "Bars & Nightlife"),
    ("cocktail", "Bars & Nightlife"),
    ("lounge", "Bars & Nightlife"),
    ("club", "Bars & Nightlife"),
    ("cafe", "Cafes"),
    ("café", "Cafes"),
    ("coffee", "Cafes"),
    ("tea room", "Cafes"),
    ("bakery", "Cafes"),
    ("dessert", "Cafes"),
    ("ice cream", "Cafes"),
    ("juice bar", "Cafes"),
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

# Weekend context display order and styling
_CONTEXT_LABELS: dict[tuple[bool, bool], str] = {
    (False, True): "Home Weekday",
    (True, True): "Home Weekend",
    (False, False): "Away Weekday",
    (True, False): "Away Weekend",
}
_CONTEXT_COLORS: dict[tuple[bool, bool], str] = {
    (False, True): ACCENT_INDIGO,
    (True, True): ACCENT_CYAN,
    (False, False): ACCENT_ORANGE,
    (True, False): ACCENT_GREEN,
}
_GRID_ORDER: list[tuple[bool, bool]] = [
    (False, True),
    (True, True),
    (False, False),
    (True, False),
]

# Persona badge definitions: (label, accent_color, description)
_PERSONA_BADGES: list[tuple[str, str, str]] = [
    ("Night Owl", ACCENT_INDIGO, "late_rate"),
    ("Weekend Listener", ACCENT_CYAN, "weekend_boost"),
    ("Globe Trotter", ACCENT_ORANGE, "away_share"),
    ("Transit Listener", ACCENT_GREEN, "transit_days"),
    ("Dining Devotee", ACCENT_PINK, "dining_plays"),
    ("Holiday Traditionalist", ACCENT_YELLOW, "holiday_count"),
]


# ---------------------------------------------------------------------------
# Week / weekend helpers
# ---------------------------------------------------------------------------


def _add_weekend_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``day_of_week`` and ``is_weekend`` columns from ``date_text``.

    Args:
        df: Listening history with a datetime ``date_text`` column.

    Returns:
        Copy of ``df`` with two additional columns.
    """
    out = df.copy()
    out["day_of_week"] = out["date_text"].dt.day_name()
    out["is_weekend"] = out["date_text"].dt.weekday >= 5
    return out


def _add_location_context(df: pd.DataFrame, home_city: str) -> pd.DataFrame:
    """Add ``is_home`` column — True when the city matches *home_city*.

    Args:
        df: Listening history with a ``city`` column.
        home_city: Home city from assumptions (may include ", CC" suffix).

    Returns:
        Copy of ``df`` with ``is_home`` column added.
    """
    out = df.copy()
    bare_home = home_city.split(",")[0].strip().lower()
    out["is_home"] = out["city"].str.split(",").str[0].str.strip().str.lower() == bare_home
    return out


def _compute_week_stats(df: pd.DataFrame, home_city: str) -> list[dict[str, Any]]:
    """Compute per-context statistics for the four (is_weekend × is_home) cells.

    Args:
        df: Enriched listening history with ``date_text``, ``artist``, ``city``.
        home_city: The user's home city string.

    Returns:
        List of four stat dicts in ``_GRID_ORDER`` order.
    """
    enriched = _add_weekend_columns(_add_location_context(df, home_city))
    stats: list[dict[str, Any]] = []

    for is_weekend, is_home in _GRID_ORDER:
        mask = (enriched["is_weekend"] == is_weekend) & (enriched["is_home"] == is_home)
        subset = enriched[mask]
        play_count = len(subset)

        if not subset.empty:
            top_artists = subset["artist"].value_counts().head(3).index.tolist()
            hour_counts = subset.groupby(subset["date_text"].dt.hour).size()
            peak_hour = int(hour_counts.idxmax()) if not hour_counts.empty else None
        else:
            top_artists, peak_hour = [], None

        stats.append(
            {
                "is_weekend": is_weekend,
                "is_home": is_home,
                "label": _CONTEXT_LABELS[(is_weekend, is_home)],
                "color": _CONTEXT_COLORS[(is_weekend, is_home)],
                "play_count": play_count,
                "top_artists": top_artists,
                "peak_hour": peak_hour,
                "subset": subset,
            }
        )

    return stats


# ---------------------------------------------------------------------------
# Dining helpers
# ---------------------------------------------------------------------------


def _classify_venue_category(raw_category: str) -> str | None:
    """Map a raw Foursquare category to one of the four display buckets.

    Args:
        raw_category: Raw category string from a Foursquare export.

    Returns:
        One of the four :data:`_FOOD_DRINK_CATEGORIES` strings, or ``None``.
    """
    lower = raw_category.lower()
    for substring, bucket in _CATEGORY_RULES:
        if substring in lower:
            return bucket
    return None


def _listens_around_checkin(
    lastfm_df: pd.DataFrame,
    checkin_ts: int,
    window_hours: int = _DINING_WINDOW_HOURS,
) -> pd.DataFrame:
    """Return Last.fm listens within ±``window_hours`` of *checkin_ts*.

    Args:
        lastfm_df: Listening history with a ``timestamp`` column.
        checkin_ts: Unix timestamp of the Swarm check-in.
        window_hours: Symmetric window size in hours.

    Returns:
        Subset of ``lastfm_df`` within the window; may be empty.
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
) -> dict[str, dict[str, Any]]:
    """Aggregate Last.fm listens around food/drink check-ins by venue bucket.

    Args:
        swarm_df: Swarm DataFrame with ``timestamp`` and ``venue_category``.
        lastfm_df: Listening history with ``timestamp``, ``artist``, ``date_text``.
        top_n: Maximum top artists to return per bucket.

    Returns:
        Dict keyed by venue category bucket.  Each value has:
        ``top_artists`` (DataFrame), ``checkin_count`` (int),
        ``listen_count`` (int), ``peak_hour`` (int | None).
    """
    if swarm_df.empty or lastfm_df.empty:
        return {}
    required = {"timestamp", "venue_category"}
    if not required.issubset(swarm_df.columns) or "timestamp" not in lastfm_df.columns:
        return {}

    bucket_listens: dict[str, list[pd.DataFrame]] = {c: [] for c in _FOOD_DRINK_CATEGORIES}
    bucket_checkins: dict[str, int] = {c: 0 for c in _FOOD_DRINK_CATEGORIES}

    for _, row in swarm_df.iterrows():
        bucket = _classify_venue_category(str(row.get("venue_category", "")))
        if bucket is None:
            continue
        nearby = _listens_around_checkin(lastfm_df, int(row["timestamp"]))
        if not nearby.empty:
            bucket_listens[bucket].append(nearby)
        bucket_checkins[bucket] += 1

    results: dict[str, dict[str, Any]] = {}
    for cat in _FOOD_DRINK_CATEGORIES:
        if bucket_checkins[cat] == 0:
            continue
        frames = bucket_listens[cat]
        if not frames:
            continue
        combined = pd.concat(frames, ignore_index=True).drop_duplicates()
        top_artists = get_top_entities(combined, "artist", limit=top_n)
        peak_hour: int | None = None
        if "date_text" in combined.columns and not combined["date_text"].isna().all():
            hour_counts = combined["date_text"].dt.hour.value_counts()
            if not hour_counts.empty:
                peak_hour = int(hour_counts.idxmax())
        results[cat] = {
            "top_artists": top_artists,
            "checkin_count": bucket_checkins[cat],
            "listen_count": len(combined),
            "peak_hour": peak_hour,
        }
    return results


# ---------------------------------------------------------------------------
# Late night helpers
# ---------------------------------------------------------------------------


def _filter_late_night(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where the local hour falls in the midnight–4 AM window.

    Args:
        df: Listening history with a ``date_text`` datetime column.

    Returns:
        Filtered DataFrame; empty when no late-night rows exist.
    """
    if df.empty or "date_text" not in df.columns:
        return pd.DataFrame()
    mask = (df["date_text"].dt.hour >= _LATE_NIGHT_START) & (
        df["date_text"].dt.hour < _LATE_NIGHT_END
    )
    return df[mask].copy()


def get_top_late_night_artists(df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    """Return the top ``limit`` artists by late-night play count.

    Args:
        df: Full listening history with ``date_text`` and ``artist``.
        limit: Maximum number of artists to return.

    Returns:
        DataFrame with columns ``artist`` and ``plays``.
    """
    late = _filter_late_night(df)
    if late.empty or "artist" not in late.columns:
        return pd.DataFrame(columns=["artist", "plays"])
    counts = late["artist"].value_counts().head(limit).reset_index()
    counts.columns = pd.Index(["artist", "plays"])
    return counts


def get_late_night_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Return hourly play counts for all 24 hours with a late-night flag.

    Args:
        df: Listening history with ``date_text``.

    Returns:
        DataFrame with columns ``hour`` (0–23), ``plays`` (int),
        ``is_late_night`` (bool).
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
    merged["is_late_night"] = (merged["hour"] >= _LATE_NIGHT_START) & (
        merged["hour"] < _LATE_NIGHT_END
    )
    return merged


def find_latest_session(df: pd.DataFrame) -> dict[str, Any] | None:
    """Find the most extreme consecutive late-night listening session.

    A session is consecutive plays within the midnight–4 AM window with
    inter-play gaps under :data:`_SESSION_GAP_MINUTES`.  The longest session
    wins; ties broken by most recent start time.

    Args:
        df: Listening history with ``date_text``, ``timestamp``, ``artist``.

    Returns:
        Dict with ``start``, ``end``, ``track_count``, ``artists``;
        or ``None`` when no late-night plays exist.
    """
    late = _filter_late_night(df)
    if late.empty or "timestamp" not in late.columns:
        return None

    late = late.sort_values("timestamp").reset_index(drop=True)
    gap_sec = _SESSION_GAP_MINUTES * 60

    sessions: list[dict[str, Any]] = []
    session_start = 0

    for i in range(1, len(late)):
        gap = late.loc[i, "timestamp"] - late.loc[i - 1, "timestamp"]
        if gap > gap_sec:
            sessions.append(
                {
                    "start": late.loc[session_start, "date_text"],
                    "end": late.loc[i - 1, "date_text"],
                    "track_count": i - session_start,
                    "artists": late.loc[session_start : i - 1, "artist"].dropna().unique().tolist(),
                }
            )
            session_start = i

    sessions.append(
        {
            "start": late.loc[session_start, "date_text"],
            "end": late.loc[len(late) - 1, "date_text"],
            "track_count": len(late) - session_start,
            "artists": late.loc[session_start:, "artist"].dropna().unique().tolist(),
        }
    )

    return max(sessions, key=lambda s: (s["track_count"], s["start"]))


# ---------------------------------------------------------------------------
# Holiday helpers
# ---------------------------------------------------------------------------


def _build_holiday_windows(df: pd.DataFrame, holiday: dict[str, Any]) -> list[dict[str, Any]]:
    """Build per-year date windows for a recurring holiday.

    Args:
        df: Listening history with a ``date_text`` column.
        holiday: Holiday definition dict with ``month`` and ``day_range`` keys.

    Returns:
        List of dicts with ``year``, ``start``, ``end`` per calendar year in ``df``.
    """
    if df.empty or "date_text" not in df.columns:
        return []
    month: int = holiday.get("month", 1)
    day_range: list[int] = holiday.get("day_range", [1, 1])
    day_start, day_end = day_range[0], day_range[1]
    windows: list[dict[str, Any]] = []
    for year in sorted(df["date_text"].dt.year.unique()):
        try:
            start = pd.Timestamp(year=int(year), month=month, day=day_start)
            end = pd.Timestamp(
                year=int(year), month=month, day=day_end, hour=23, minute=59, second=59
            )
        except ValueError:
            continue
        windows.append({"year": int(year), "start": start, "end": end})
    return windows


def _filter_holiday(df: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    """Return rows within a holiday window.

    Args:
        df: Listening history with a ``date_text`` column.
        window: Dict with ``start`` and ``end`` Timestamp keys.

    Returns:
        Filtered sub-DataFrame (may be empty).
    """
    mask = (df["date_text"] >= window["start"]) & (df["date_text"] <= window["end"])
    return df[mask]


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
    combined = combined.copy()
    combined["_song_key"] = combined["artist"] + " — " + combined["track"]
    top = combined["_song_key"].value_counts()
    return str(top.index[0]) if not top.empty else None


def _compute_holiday_stats(
    df: pd.DataFrame, holidays: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Compute per-holiday statistics across all years.

    Args:
        df: Full listening history.
        holidays: List of holiday dicts from assumptions (``name``, ``month``,
            ``day_range``).

    Returns:
        List of dicts; one per holiday that has at least one year of data.
        Each dict has: ``name``, ``windows``, ``total_plays``, ``years_with_data``,
        ``top_artist``, ``signature_song``, ``yoy_plays`` (DataFrame).
    """
    results = []
    for holiday in holidays:
        windows = _build_holiday_windows(df, holiday)
        if not windows:
            continue
        yoy_rows = []
        for w in windows:
            subset = _filter_holiday(df, w)
            yoy_rows.append({"year": w["year"], "plays": len(subset)})
        yoy = pd.DataFrame(yoy_rows)
        years_with_data = int((yoy["plays"] > 0).sum())
        if years_with_data == 0:
            continue
        all_subsets = [_filter_holiday(df, w) for w in windows]
        combined = pd.concat(all_subsets, ignore_index=True)
        top_artist = (
            combined["artist"].value_counts().index[0]
            if not combined.empty and "artist" in combined.columns
            else None
        )
        results.append(
            {
                "name": holiday.get("name", "Holiday"),
                "windows": windows,
                "total_plays": int(yoy["plays"].sum()),
                "years_with_data": years_with_data,
                "top_artist": top_artist,
                "signature_song": _signature_song(df, windows),
                "yoy_plays": yoy,
            }
        )
    return sorted(results, key=lambda h: h["total_plays"], reverse=True)


# ---------------------------------------------------------------------------
# Data computation — cached in session state
# ---------------------------------------------------------------------------


def _compute_lifestyle_data(
    df: pd.DataFrame,
    swarm_df: pd.DataFrame,
    assumptions: dict[str, Any],
) -> dict[str, Any]:
    """Run all five lifestyle analyses and return a combined data dict.

    Args:
        df: Full listening history.
        swarm_df: Swarm check-in DataFrame (may be empty).
        assumptions: Parsed assumptions dict.

    Returns:
        Dict with keys ``week``, ``transit``, ``dining``, ``late_night``,
        ``holiday`` and their computed values.
    """
    home_city: str = assumptions.get("defaults", {}).get("city", "")

    # Week / weekend context
    week_stats = _compute_week_stats(df, home_city) if home_city else []

    # Transit
    transit_days: set[str] = get_transit_days(swarm_df)
    transit_df, non_transit_df = split_transit_listens(df, transit_days)
    transit_avg = get_avg_plays_per_day(transit_df)
    non_transit_avg = get_avg_plays_per_day(non_transit_df)
    transit_top = (
        get_top_entities(transit_df, "artist", limit=10) if not transit_df.empty else pd.DataFrame()
    )
    transit_delta_pct = (
        ((transit_avg - non_transit_avg) / non_transit_avg * 100) if non_transit_avg > 0 else 0.0
    )

    # Dining
    dining = get_dining_soundtrack_data(swarm_df, df)

    # Late night
    late_df = _filter_late_night(df)
    late_rate = len(late_df) / len(df) if len(df) > 0 else 0.0
    top_late_night = get_top_late_night_artists(df, limit=10)
    late_hourly = get_late_night_hourly(df)
    latest_session = find_latest_session(df)

    # Holiday
    holidays_def = assumptions.get("holidays", [])
    holiday_stats = _compute_holiday_stats(df, holidays_def)

    # Persona signal values (used by badge synthesis)
    home_weekend_plays = next(
        (s["play_count"] for s in week_stats if s["is_weekend"] and s["is_home"]), 0
    )
    home_weekday_plays = next(
        (s["play_count"] for s in week_stats if not s["is_weekend"] and s["is_home"]), 0
    )
    away_plays = sum(s["play_count"] for s in week_stats if not s["is_home"])
    total_week_plays = sum(s["play_count"] for s in week_stats)
    away_share = away_plays / total_week_plays if total_week_plays > 0 else 0.0
    weekend_boost = (
        (home_weekend_plays - home_weekday_plays) / home_weekday_plays
        if home_weekday_plays > 0
        else 0.0
    )
    total_dining_plays = sum(v["listen_count"] for v in dining.values())

    return {
        "week": week_stats,
        "transit": {
            "days": len(transit_days),
            "transit_df": transit_df,
            "transit_avg": transit_avg,
            "non_transit_avg": non_transit_avg,
            "delta_pct": transit_delta_pct,
            "top_artists": transit_top,
        },
        "dining": dining,
        "late_night": {
            "late_rate": late_rate,
            "top_artists": top_late_night,
            "hourly": late_hourly,
            "latest_session": latest_session,
        },
        "holiday": holiday_stats,
        "persona_signals": {
            "late_rate": late_rate,
            "weekend_boost": weekend_boost,
            "away_share": away_share,
            "transit_days": len(transit_days),
            "dining_plays": total_dining_plays,
            "holiday_count": len(holiday_stats),
        },
    }


def _synthesize_persona(signals: dict[str, Any]) -> list[dict[str, str]]:
    """Derive lifestyle badge labels from the persona signal values.

    Args:
        signals: Dict of metric values from ``_compute_lifestyle_data``.

    Returns:
        List of dicts with ``label`` and ``color`` keys, at most 4 badges.
    """
    badges = []
    if signals.get("late_rate", 0) >= 0.10:
        badges.append({"label": "Night Owl", "color": ACCENT_INDIGO})
    if signals.get("weekend_boost", 0) >= 0.20:
        badges.append({"label": "Weekend Listener", "color": ACCENT_CYAN})
    if signals.get("away_share", 0) >= 0.20:
        badges.append({"label": "Globe Trotter", "color": ACCENT_ORANGE})
    if signals.get("transit_days", 0) >= 5:
        badges.append({"label": "Transit Listener", "color": ACCENT_GREEN})
    if signals.get("dining_plays", 0) >= 30:
        badges.append({"label": "Dining Devotee", "color": ACCENT_PINK})
    if signals.get("holiday_count", 0) >= 2:
        badges.append({"label": "Holiday Traditionalist", "color": ACCENT_YELLOW})
    return badges if badges else [{"label": "Music Lover", "color": ACCENT_CYAN}]


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_persona_banner(data: dict[str, Any]) -> None:
    """Render the top-of-page persona banner with badges and key stats.

    Args:
        data: The full lifestyle data dict from ``_compute_lifestyle_data``.
    """
    badges = _synthesize_persona(data["persona_signals"])

    badge_html = " ".join(
        f"<span style='background:{b['color']}22; color:{b['color']}; "
        f"border:1px solid {b['color']}55; border-radius:999px; "
        f"padding:2px 12px; font-size:0.85rem; font-weight:600; "
        f"margin-right:6px;'>{b['label']}</span>"
        for b in badges
    )
    st.markdown(
        f"<div style='margin-bottom:0.5rem;'>{badge_html}</div>",
        unsafe_allow_html=True,
    )

    signals = data["persona_signals"]
    cols = st.columns(4)
    with cols[0]:
        late_pct = signals["late_rate"] * 100
        st.metric("Late-Night Plays", f"{late_pct:.1f}%")
    with cols[1]:
        st.metric("Transit Days", f"{signals['transit_days']:,}")
    with cols[2]:
        st.metric("Dining Listens", f"{signals['dining_plays']:,}")
    with cols[3]:
        st.metric("Holidays Tracked", f"{signals['holiday_count']:,}")
    st.divider()


def _render_your_week(week_stats: list[dict[str, Any]]) -> None:
    """Render the Your Week section.

    Args:
        week_stats: Output of ``_compute_week_stats``.
    """
    if not week_stats:
        st.info(
            "No home city configured in your assumptions file. "
            "Add ``defaults.city`` to enable weekly context analysis."
        )
        return

    total = sum(s["play_count"] for s in week_stats)
    home_wknd = next((s for s in week_stats if s["is_weekend"] and s["is_home"]), None)
    home_wkdy = next((s for s in week_stats if not s["is_weekend"] and s["is_home"]), None)

    # Summary metrics (always visible)
    cols = st.columns(4)
    for i, stat in enumerate(week_stats):
        with cols[i]:
            pct = stat["play_count"] / total * 100 if total > 0 else 0
            st.markdown(
                f"<span style='color:{stat['color']}; font-weight:700;'>{stat['label']}</span>",
                unsafe_allow_html=True,
            )
            st.metric("Plays", f"{stat['play_count']:,}", delta=f"{pct:.0f}% of total")
            if stat["top_artists"]:
                st.caption(" · ".join(stat["top_artists"][:2]))

    with st.expander("Full breakdown", expanded=False):
        if home_wknd and home_wkdy and home_wkdy["play_count"] > 0:
            boost = (
                (home_wknd["play_count"] - home_wkdy["play_count"]) / home_wkdy["play_count"] * 100
            )
            st.caption(
                f"Weekend listening is **{abs(boost):.0f}%** "
                f"{'higher' if boost >= 0 else 'lower'} than weekdays at home."
            )

        # Day-of-week bar chart using all contexts
        all_subsets = [s["subset"] for s in week_stats if not s["subset"].empty]
        if all_subsets:
            combined = pd.concat(all_subsets, ignore_index=True)
            day_order = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            day_counts = (
                combined.assign(day=combined["date_text"].dt.day_name())
                .groupby("day")
                .size()
                .reindex(day_order, fill_value=0)
                .reset_index(name="plays")
            )
            day_counts.columns = pd.Index(["day", "plays"])
            fig = px.bar(
                day_counts,
                x="day",
                y="plays",
                color_discrete_sequence=[ACCENT_INDIGO],
                labels={"day": "Day", "plays": "Plays"},
            )
            fig = apply_dark_theme(fig)
            fig.update_layout(height=260, showlegend=False)
            st.plotly_chart(fig, width="stretch", key="lifestyle_week_bar")

        # Top artists per context
        ctx_cols = st.columns(4)
        for i, stat in enumerate(week_stats):
            with ctx_cols[i]:
                st.markdown(
                    f"<span style='color:{stat['color']}; font-size:0.8rem; font-weight:600;'>"
                    f"{stat['label']}</span>",
                    unsafe_allow_html=True,
                )
                if stat["peak_hour"] is not None:
                    st.caption(f"Peak hour: {stat['peak_hour']:02d}:00")
                for artist in stat["top_artists"]:
                    st.markdown(
                        f"<span style='font-size:0.85rem; color:{TEXT_DIM};'>· {artist}</span>",
                        unsafe_allow_html=True,
                    )


def _render_on_the_move(transit_data: dict[str, Any]) -> None:
    """Render the On the Move section.

    Args:
        transit_data: Transit facet dict from ``_compute_lifestyle_data``.
    """
    days = transit_data["days"]
    delta_pct = transit_data["delta_pct"]
    top_artists = transit_data["top_artists"]

    if days == 0:
        st.info(
            "No transit check-ins detected. "
            "Connect Swarm data with airport or train station check-ins to see this section."
        )
        return

    top_artist = str(top_artists.iloc[0]["artist"]) if not top_artists.empty else "—"

    cols = st.columns(3)
    with cols[0]:
        st.metric("Transit Days", f"{days:,}")
    with cols[1]:
        delta_label = f"{abs(delta_pct):.0f}% {'more' if delta_pct >= 0 else 'fewer'} plays/day"
        st.metric("vs. Normal Days", delta_label)
    with cols[2]:
        st.metric("Top Transit Artist", top_artist)

    with st.expander("Top artists on transit days", expanded=False):
        if top_artists.empty:
            st.caption("No artist data for transit days.")
        else:
            fig = px.bar(
                top_artists.head(10),
                x="Plays",
                y="artist",
                orientation="h",
                color_discrete_sequence=[ACCENT_GREEN],
                labels={"artist": "", "Plays": "Plays"},
            )
            fig = apply_dark_theme(fig)
            fig.update_layout(height=320, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, width="stretch", key="lifestyle_transit_bar")
            st.caption(
                f"Average **{transit_data['transit_avg']:.1f}** plays/day on transit days "
                f"vs **{transit_data['non_transit_avg']:.1f}** on other days."
            )


def _render_around_the_table(dining: dict[str, dict[str, Any]]) -> None:
    """Render the Around the Table section.

    Args:
        dining: Dining facet dict from ``get_dining_soundtrack_data``.
    """
    if not dining:
        st.info(
            "No dining data available. "
            "Connect Swarm data with restaurant or bar check-ins to see this section."
        )
        return

    total_plays = sum(v["listen_count"] for v in dining.values())
    best_bucket = max(dining, key=lambda k: dining[k]["listen_count"])
    best_artist_df = dining[best_bucket]["top_artists"]
    best_artist = str(best_artist_df.iloc[0]["artist"]) if not best_artist_df.empty else "—"

    cols = st.columns(3)
    with cols[0]:
        st.metric("Dining Listens", f"{total_plays:,}")
    with cols[1]:
        st.metric("Most Musical Venue", best_bucket)
    with cols[2]:
        st.metric("Top Dining Artist", best_artist)

    bucket_colors = {
        "Restaurants": ACCENT_INDIGO,
        "Bars & Nightlife": ACCENT_PURPLE,
        "Cafes": ACCENT_CYAN,
        "Fast Food": ACCENT_ORANGE,
    }

    with st.expander("Breakdown by venue type", expanded=False):
        bucket_cols = st.columns(len(dining))
        for i, (cat, stats) in enumerate(dining.items()):
            color = bucket_colors.get(cat, ACCENT_INDIGO)
            with bucket_cols[i]:
                st.markdown(
                    f"<span style='color:{color}; font-weight:700; font-size:0.9rem;'>{cat}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"{stats['checkin_count']} check-ins · {stats['listen_count']} listens")
                if stats["peak_hour"] is not None:
                    st.caption(f"Peak: {stats['peak_hour']:02d}:00")
                for _, row in stats["top_artists"].head(5).iterrows():
                    st.markdown(
                        f"<span style='font-size:0.85rem; color:{TEXT_DIM};'>"
                        f"· {row['artist']}</span>",
                        unsafe_allow_html=True,
                    )


def _render_after_dark(late_data: dict[str, Any]) -> None:
    """Render the After Dark section.

    Args:
        late_data: Late-night facet dict from ``_compute_lifestyle_data``.
    """
    late_rate = late_data["late_rate"]
    top_artists = late_data["top_artists"]
    hourly = late_data["hourly"]
    session = late_data["latest_session"]

    top_artist = str(top_artists.iloc[0]["artist"]) if not top_artists.empty else "—"

    cols = st.columns(3)
    with cols[0]:
        st.metric(
            "Late-Night Rate",
            f"{late_rate * 100:.1f}%",
            help="% of plays between midnight and 4 AM",
        )
    with cols[1]:
        st.metric("Top Night Artist", top_artist)
    with cols[2]:
        if session:
            st.metric(
                "Longest Late Session",
                f"{session['track_count']} tracks",
                delta=str(session["start"].date()),
            )
        else:
            st.metric("Longest Late Session", "—")

    with st.expander("Hourly listening clock & top artists", expanded=False):
        if not hourly.empty:
            hourly_copy = hourly.copy()
            hourly_copy["color"] = hourly_copy["is_late_night"].map(
                {True: ACCENT_INDIGO, False: "rgba(139,148,167,0.35)"}
            )
            fig = go.Figure(
                go.Bar(
                    x=hourly_copy["hour"],
                    y=hourly_copy["plays"],
                    marker_color=hourly_copy["color"].tolist(),
                    hovertemplate="%{x:02d}:00 — %{y} plays<extra></extra>",
                )
            )
            fig = apply_dark_theme(fig)
            fig.update_layout(
                height=280,
                xaxis={"tickmode": "linear", "dtick": 3, "tickformat": "%02d:00"},
                showlegend=False,
            )
            st.plotly_chart(fig, width="stretch", key="lifestyle_late_hourly")

        if not top_artists.empty:
            st.markdown(
                "<span style='color:" + TEXT_DIM + "; font-size:0.85rem;'>"
                "Top artists (midnight–4 AM)</span>",
                unsafe_allow_html=True,
            )
            artist_cols = st.columns(min(len(top_artists), 5))
            for i, (col, (_, row)) in enumerate(zip(artist_cols, top_artists.head(5).iterrows())):
                color = ACCENT_INDIGO if i == 0 else TEXT_DIM
                col.markdown(
                    f"<div style='text-align:center;'>"
                    f"<span style='color:{color}; font-weight:700; font-size:0.85rem;'>"
                    f"#{i + 1}</span>"
                    f"<br><span style='font-size:0.8rem;'>{row['artist']}</span></div>",
                    unsafe_allow_html=True,
                )


def _render_years_traditions(holiday_stats: list[dict[str, Any]]) -> None:
    """Render the Year's Traditions section.

    Args:
        holiday_stats: Holiday facet list from ``_compute_holiday_stats``.
    """
    if not holiday_stats:
        st.info(
            "No holiday data available. "
            "Add ``holidays`` entries to your assumptions file to see this section."
        )
        return

    top_holiday = holiday_stats[0]
    total_plays = sum(h["total_plays"] for h in holiday_stats)

    cols = st.columns(3)
    with cols[0]:
        st.metric("Holidays Tracked", f"{len(holiday_stats):,}")
    with cols[1]:
        st.metric("Most Listened", top_holiday["name"])
    with cols[2]:
        sig = top_holiday.get("signature_song") or "—"
        st.metric("Signature Song", sig[:40] + ("…" if len(sig) > 40 else ""))

    with st.expander("Year-over-year plays per holiday", expanded=False):
        st.caption(f"Total holiday listens across {total_plays:,} plays.")
        # YoY line chart for top 4 holidays
        top_holidays = holiday_stats[:4]
        if top_holidays:
            frames = []
            for h in top_holidays:
                yoy = h["yoy_plays"].copy()
                yoy["holiday"] = h["name"]
                frames.append(yoy)
            combined_yoy = pd.concat(frames, ignore_index=True)
            fig = px.line(
                combined_yoy,
                x="year",
                y="plays",
                color="holiday",
                markers=True,
                color_discrete_sequence=COLORWAY,
                labels={"year": "Year", "plays": "Plays", "holiday": "Holiday"},
            )
            fig = apply_dark_theme(fig)
            fig.update_layout(height=300)
            st.plotly_chart(fig, width="stretch", key="lifestyle_holiday_yoy")

        # Signature songs per holiday
        sig_rows = [
            {
                "Holiday": h["name"],
                "Signature Song": h.get("signature_song") or "—",
                "Top Artist": h.get("top_artist") or "—",
            }
            for h in holiday_stats
        ]
        st.dataframe(
            pd.DataFrame(sig_rows),
            hide_index=True,
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_listening_lifestyle() -> None:
    """Render the Listening Lifestyle multi-facet insights page.

    Reads listening history from ``st.session_state['df']``, Swarm check-ins
    from ``st.session_state['swarm_df']``, and the assumptions file path from
    ``st.session_state['_loaded_config']``.  Shows an empty state when no
    listening data has been loaded.

    All analysis is cached in session state keyed by ``(id(df), id(swarm_df),
    hash(assumptions))``.  UI interactions (expanding sections) never re-trigger
    the computation.
    """
    st.header("Listening Lifestyle")
    st.caption(
        "A portrait of how music fits into the different moments of your life — "
        "your week, your commute, your meals, your nights, your year."
    )

    df: pd.DataFrame | None = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    _swarm = st.session_state.get("swarm_df")
    swarm_df: pd.DataFrame = _swarm if isinstance(_swarm, pd.DataFrame) else pd.DataFrame()
    loaded_config = st.session_state.get("_loaded_config")
    assumptions_path: str | None = loaded_config[2] if loaded_config else None
    assumptions = load_assumptions(assumptions_path)

    _ll_key = (
        id(df),
        id(swarm_df),
        hash(json.dumps(assumptions, sort_keys=True, default=str)),
    )
    if st.session_state.get("_ll_cache_key") != _ll_key:
        with st.spinner("Analysing your listening lifestyle…"):
            _data = _compute_lifestyle_data(df, swarm_df, assumptions)
        st.session_state["_ll_data"] = _data
        st.session_state["_ll_cache_key"] = _ll_key

    data: dict[str, Any] = st.session_state["_ll_data"]

    _render_persona_banner(data)

    st.subheader(":material/calendar_view_week: Your Week")
    _render_your_week(data["week"])

    st.subheader(":material/train: On the Move")
    _render_on_the_move(data["transit"])

    st.subheader(":material/restaurant: Around the Table")
    _render_around_the_table(data["dining"])

    st.subheader(":material/nights_stay: After Dark")
    _render_after_dark(data["late_night"])

    st.subheader(":material/celebration: Year's Traditions")
    _render_years_traditions(data["holiday"])
