"""Tests for pages/listening_lifestyle.py — Listening Lifestyle page."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from analysis_utils import get_avg_plays_per_day, get_transit_days, split_transit_listens
from pages.listening_lifestyle import (
    _add_location_context,
    _add_weekend_columns,
    _build_holiday_windows,
    _classify_venue_category,
    _compute_holiday_stats,
    _compute_week_stats,
    _filter_holiday,
    _filter_late_night,
    _listens_around_checkin,
    _signature_song,
    _synthesize_persona,
    find_latest_session,
    get_dining_soundtrack_data,
    get_late_night_hourly,
    get_top_late_night_artists,
    render_listening_lifestyle,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_listens_df(
    hours: list[int] | None = None,
    cities: list[str] | None = None,
    artists: list[str] | None = None,
    days: list[str] | None = None,
) -> pd.DataFrame:
    """Build a minimal merged DataFrame for testing.

    The row count is determined by the longest provided list; shorter lists
    are repeated (cycled) to match.  If no lists are given, a 4-row default
    DataFrame is returned.

    Args:
        hours: Local hour for each row (0–23).
        cities: City label for each row.
        artists: Artist name for each row.
        days: ISO date string prefix (YYYY-MM-DD) for each row.

    Returns:
        DataFrame with ``date_text``, ``timestamp``, ``artist``, ``city``, ``track``.
    """
    # Determine row count from the longest explicit argument; fall back to 4.
    explicit_lens = [len(x) for x in [hours, cities, artists, days] if x is not None]
    n = max(explicit_lens) if explicit_lens else 4
    _hours = ((hours or [10]) * n)[:n]
    _cities = ((cities or ["Home City"]) * n)[:n]
    _artists = ((artists or ["Artist A"]) * n)[:n]
    _days = ((days or ["2024-01-01"]) * n)[:n]

    date_texts = [pd.Timestamp(f"{d} {h:02d}:00:00") for d, h in zip(_days, _hours)]
    timestamps = [int(dt.timestamp()) for dt in date_texts]
    return pd.DataFrame(
        {
            "date_text": pd.to_datetime(date_texts),
            "timestamp": timestamps,
            "artist": _artists,
            "city": _cities,
            "track": [f"Track {i}" for i in range(n)],
            "country": ["Country"] * n,
        }
    )


def _make_swarm_df(
    venues: list[str] | None = None,
    timestamps: list[int] | None = None,
) -> pd.DataFrame:
    """Build a minimal Swarm DataFrame for testing.

    Args:
        venues: Foursquare venue category strings.
        timestamps: Unix timestamps for each check-in.

    Returns:
        DataFrame with ``venue_category`` and ``timestamp`` columns.
    """
    if venues is None:
        venues = ["Airport", "Italian Restaurant"]
    if timestamps is None:
        timestamps = [1700000000 + i * 3600 for i in range(len(venues))]
    return pd.DataFrame({"venue_category": venues, "timestamp": timestamps})


# ---------------------------------------------------------------------------
# analysis_utils transit additions
# ---------------------------------------------------------------------------


class TestGetTransitDays(unittest.TestCase):
    """Tests for analysis_utils.get_transit_days."""

    def test_returns_dates_with_airport_checkin(self) -> None:
        swarm = pd.DataFrame(
            {
                "venue_category": ["Airport", "Coffee Shop"],
                "timestamp": [1700000000, 1700003600],
            }
        )
        days = get_transit_days(swarm)
        self.assertEqual(len(days), 1)

    def test_empty_swarm_returns_empty_set(self) -> None:
        self.assertEqual(get_transit_days(pd.DataFrame()), set())

    def test_no_transit_category_returns_empty(self) -> None:
        swarm = pd.DataFrame({"venue_category": ["Museum", "Park"], "timestamp": [1, 2]})
        self.assertEqual(get_transit_days(swarm), set())

    def test_case_insensitive_matching(self) -> None:
        swarm = pd.DataFrame({"venue_category": ["airport"], "timestamp": [1700000000]})
        days = get_transit_days(swarm)
        self.assertEqual(len(days), 1)


class TestSplitTransitListens(unittest.TestCase):
    """Tests for analysis_utils.split_transit_listens."""

    def test_partitions_into_two_sets(self) -> None:
        df = _make_listens_df(
            days=["2024-01-01", "2024-01-02"],
            hours=[10, 10],
        )
        transit_days = {"2024-01-01"}
        transit, non = split_transit_listens(df, transit_days)
        self.assertEqual(len(transit), 1)
        self.assertEqual(len(non), 1)

    def test_empty_transit_days_yields_all_non_transit(self) -> None:
        df = _make_listens_df()
        transit, non = split_transit_listens(df, set())
        self.assertEqual(len(transit), 0)
        self.assertEqual(len(non), len(df))

    def test_empty_df_returns_two_empty_dfs(self) -> None:
        transit, non = split_transit_listens(pd.DataFrame(), {"2024-01-01"})
        self.assertTrue(transit.empty)
        self.assertTrue(non.empty)


class TestGetAvgPlaysPerDay(unittest.TestCase):
    """Tests for analysis_utils.get_avg_plays_per_day."""

    def test_returns_correct_average(self) -> None:
        df = _make_listens_df(days=["2024-01-01", "2024-01-01", "2024-01-02"], hours=[10, 11, 10])
        avg = get_avg_plays_per_day(df)
        self.assertAlmostEqual(avg, 1.5, places=1)

    def test_empty_df_returns_zero(self) -> None:
        self.assertEqual(get_avg_plays_per_day(pd.DataFrame()), 0.0)


# ---------------------------------------------------------------------------
# Week / weekend helpers
# ---------------------------------------------------------------------------


class TestAddWeekendColumns(unittest.TestCase):
    """Tests for _add_weekend_columns."""

    def test_adds_required_columns(self) -> None:
        df = _make_listens_df(days=["2024-01-01"])  # Monday
        out = _add_weekend_columns(df)
        self.assertIn("day_of_week", out.columns)
        self.assertIn("is_weekend", out.columns)

    def test_monday_is_not_weekend(self) -> None:
        df = _make_listens_df(days=["2024-01-01"])
        out = _add_weekend_columns(df)
        self.assertFalse(out.iloc[0]["is_weekend"])

    def test_saturday_is_weekend(self) -> None:
        df = _make_listens_df(days=["2024-01-06"])  # Saturday
        out = _add_weekend_columns(df)
        self.assertTrue(out.iloc[0]["is_weekend"])


class TestAddLocationContext(unittest.TestCase):
    """Tests for _add_location_context."""

    def test_home_city_rows_are_is_home_true(self) -> None:
        df = _make_listens_df(cities=["Reykjavik"])
        out = _add_location_context(df, "Reykjavik")
        self.assertTrue(out.iloc[0]["is_home"])

    def test_away_city_rows_are_is_home_false(self) -> None:
        df = _make_listens_df(cities=["London"])
        out = _add_location_context(df, "Reykjavik")
        self.assertFalse(out.iloc[0]["is_home"])

    def test_case_insensitive(self) -> None:
        df = _make_listens_df(cities=["REYKJAVIK"])
        out = _add_location_context(df, "reykjavik")
        self.assertTrue(out.iloc[0]["is_home"])


class TestComputeWeekStats(unittest.TestCase):
    """Tests for _compute_week_stats."""

    def test_returns_four_contexts(self) -> None:
        df = _make_listens_df(
            days=["2024-01-01", "2024-01-06"],  # Monday, Saturday
            cities=["Home City", "Home City"],
            hours=[10, 10],
        )
        stats = _compute_week_stats(df, "Home City")
        self.assertEqual(len(stats), 4)

    def test_empty_city_returns_four_zero_contexts(self) -> None:
        df = _make_listens_df()
        stats = _compute_week_stats(df, "Nonexistent City")
        self.assertEqual(len(stats), 4)
        # All contexts should have 0 home plays
        for s in stats:
            if s["is_home"]:
                self.assertEqual(s["play_count"], 0)


# ---------------------------------------------------------------------------
# Dining helpers
# ---------------------------------------------------------------------------


class TestClassifyVenueCategory(unittest.TestCase):
    """Tests for _classify_venue_category."""

    def test_restaurant_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Italian Restaurant"), "Restaurants")

    def test_bar_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Dive Bar"), "Bars & Nightlife")

    def test_cafe_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Coffee Shop"), "Cafes")

    def test_fast_food_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Burger Joint"), "Fast Food")

    def test_unknown_category_returns_none(self) -> None:
        self.assertIsNone(_classify_venue_category("Museum"))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_classify_venue_category(""))

    def test_case_insensitive(self) -> None:
        self.assertEqual(_classify_venue_category("ITALIAN RESTAURANT"), "Restaurants")


class TestListensAroundCheckin(unittest.TestCase):
    """Tests for _listens_around_checkin."""

    def test_returns_listens_within_window(self) -> None:
        base_ts = 1700000000
        df = pd.DataFrame(
            {
                "timestamp": [base_ts - 3600, base_ts, base_ts + 3600],
                "artist": ["A", "B", "C"],
            }
        )
        result = _listens_around_checkin(df, base_ts, window_hours=2)
        self.assertEqual(len(result), 3)

    def test_excludes_listens_outside_window(self) -> None:
        base_ts = 1700000000
        df = pd.DataFrame({"timestamp": [base_ts - 10000, base_ts + 10000], "artist": ["X", "Y"]})
        result = _listens_around_checkin(df, base_ts, window_hours=1)
        self.assertTrue(result.empty)

    def test_empty_df_returns_empty(self) -> None:
        result = _listens_around_checkin(pd.DataFrame(), 1700000000)
        self.assertTrue(result.empty)


class TestGetDiningSoundtrackData(unittest.TestCase):
    """Tests for get_dining_soundtrack_data."""

    def test_returns_dict_with_bucket_keys(self) -> None:
        base_ts = 1700000000
        swarm = pd.DataFrame({"venue_category": ["Italian Restaurant"], "timestamp": [base_ts]})
        listens = pd.DataFrame(
            {
                "timestamp": [base_ts - 1800, base_ts, base_ts + 1800],
                "artist": ["Artist A", "Artist A", "Artist B"],
                "date_text": pd.to_datetime(
                    ["2023-11-14 10:00", "2023-11-14 11:00", "2023-11-14 12:00"]
                ),
            }
        )
        result = get_dining_soundtrack_data(swarm, listens)
        self.assertIn("Restaurants", result)

    def test_empty_inputs_return_empty_dict(self) -> None:
        self.assertEqual(get_dining_soundtrack_data(pd.DataFrame(), pd.DataFrame()), {})


# ---------------------------------------------------------------------------
# Late night helpers
# ---------------------------------------------------------------------------


class TestFilterLateNight(unittest.TestCase):
    """Tests for _filter_late_night."""

    def test_keeps_midnight_to_4am(self) -> None:
        df = _make_listens_df(hours=[0, 1, 2, 3, 4, 12])
        result = _filter_late_night(df)
        self.assertEqual(len(result), 4)  # hours 0–3 only

    def test_empty_df_returns_empty(self) -> None:
        result = _filter_late_night(pd.DataFrame())
        self.assertTrue(result.empty)


class TestGetTopLateNightArtists(unittest.TestCase):
    """Tests for get_top_late_night_artists."""

    def test_returns_correct_artists(self) -> None:
        df = _make_listens_df(
            hours=[1, 2, 14],
            artists=["Night Artist", "Night Artist", "Day Artist"],
        )
        result = get_top_late_night_artists(df, limit=5)
        self.assertFalse(result.empty)
        self.assertEqual(result.iloc[0]["artist"], "Night Artist")

    def test_no_late_night_plays_returns_empty(self) -> None:
        df = _make_listens_df(hours=[10, 12, 14])
        result = get_top_late_night_artists(df)
        self.assertTrue(result.empty)


class TestGetLateNightHourly(unittest.TestCase):
    """Tests for get_late_night_hourly."""

    def test_returns_24_rows(self) -> None:
        df = _make_listens_df(hours=[1, 14])
        result = get_late_night_hourly(df)
        self.assertEqual(len(result), 24)

    def test_late_night_flag_set_correctly(self) -> None:
        df = _make_listens_df(hours=[0, 12])
        result = get_late_night_hourly(df)
        self.assertTrue(result.loc[result["hour"] == 0, "is_late_night"].all())
        self.assertFalse(result.loc[result["hour"] == 12, "is_late_night"].all())

    def test_empty_df_returns_24_rows_with_zero_plays(self) -> None:
        result = get_late_night_hourly(pd.DataFrame())
        self.assertEqual(len(result), 24)
        self.assertEqual(result["plays"].sum(), 0)


class TestFindLatestSession(unittest.TestCase):
    """Tests for find_latest_session."""

    def test_finds_session_in_late_night_data(self) -> None:
        df = _make_listens_df(hours=[1, 1, 1, 12], artists=["A", "B", "C", "D"])
        # Give each row a slightly different timestamp to form a session
        df = df.copy()
        df["timestamp"] = [1700000000 + i * 60 for i in range(len(df))]
        session = find_latest_session(df)
        self.assertIsNotNone(session)
        self.assertIn("track_count", session)

    def test_no_late_night_returns_none(self) -> None:
        df = _make_listens_df(hours=[10, 12, 14])
        self.assertIsNone(find_latest_session(df))


# ---------------------------------------------------------------------------
# Holiday helpers
# ---------------------------------------------------------------------------

_XMAS_DEF: dict = {"name": "Christmas", "month": 12, "day_range": [24, 26]}
_HALLOWEEN_DEF: dict = {"name": "Halloween", "month": 10, "day_range": [31, 31]}


def _make_holiday_df() -> pd.DataFrame:
    rows = [
        {"artist": "Mariah Carey", "track": "All I Want", "date_text": "2021-12-25 10:00"},
        {"artist": "Mariah Carey", "track": "All I Want", "date_text": "2022-12-25 09:00"},
        {"artist": "Wham!", "track": "Last Christmas", "date_text": "2021-12-25 12:00"},
        {"artist": "MJ", "track": "Thriller", "date_text": "2021-10-31 20:00"},
        {"artist": "Other", "track": "Summer Song", "date_text": "2021-06-15 14:00"},
    ]
    df = pd.DataFrame(rows)
    df["date_text"] = pd.to_datetime(df["date_text"])
    return df


class TestBuildHolidayWindows(unittest.TestCase):
    """Tests for _build_holiday_windows."""

    def test_returns_window_per_year(self) -> None:
        df = _make_holiday_df()
        windows = _build_holiday_windows(df, _XMAS_DEF)
        years = [w["year"] for w in windows]
        self.assertIn(2021, years)
        self.assertIn(2022, years)

    def test_window_bounds_match_day_range(self) -> None:
        df = _make_holiday_df()
        windows = _build_holiday_windows(df, _XMAS_DEF)
        for w in windows:
            self.assertEqual(w["start"].day, 24)
            self.assertEqual(w["end"].day, 26)

    def test_empty_df_returns_empty_list(self) -> None:
        self.assertEqual(_build_holiday_windows(pd.DataFrame(), _XMAS_DEF), [])


class TestFilterHoliday(unittest.TestCase):
    """Tests for _filter_holiday."""

    def test_keeps_rows_inside_window(self) -> None:
        df = _make_holiday_df()
        windows = _build_holiday_windows(df, _XMAS_DEF)
        w = next(w for w in windows if w["year"] == 2021)
        filtered = _filter_holiday(df, w)
        self.assertEqual(len(filtered), 2)  # 2021 Mariah + 2021 Wham! (2022 row excluded)


class TestSignatureSong(unittest.TestCase):
    """Tests for _signature_song."""

    def test_returns_most_played_track(self) -> None:
        df = _make_holiday_df()
        windows = _build_holiday_windows(df, _XMAS_DEF)
        song = _signature_song(df, windows)
        self.assertIsNotNone(song)
        self.assertIn("Mariah Carey", song)  # most played over 2 Christmases

    def test_empty_windows_returns_none(self) -> None:
        self.assertIsNone(_signature_song(_make_holiday_df(), []))


class TestComputeHolidayStats(unittest.TestCase):
    """Tests for _compute_holiday_stats."""

    def test_returns_holiday_with_plays(self) -> None:
        df = _make_holiday_df()
        stats = _compute_holiday_stats(df, [_XMAS_DEF, _HALLOWEEN_DEF])
        self.assertTrue(len(stats) >= 1)
        names = [h["name"] for h in stats]
        self.assertIn("Christmas", names)

    def test_sorted_by_total_plays_descending(self) -> None:
        df = _make_holiday_df()
        stats = _compute_holiday_stats(df, [_XMAS_DEF, _HALLOWEEN_DEF])
        plays = [h["total_plays"] for h in stats]
        self.assertEqual(plays, sorted(plays, reverse=True))


# ---------------------------------------------------------------------------
# Persona synthesis
# ---------------------------------------------------------------------------


class TestSynthesizePersona(unittest.TestCase):
    """Tests for _synthesize_persona."""

    def test_night_owl_badge_when_high_late_rate(self) -> None:
        signals = {
            "late_rate": 0.15,
            "weekend_boost": 0,
            "away_share": 0,
            "transit_days": 0,
            "dining_plays": 0,
            "holiday_count": 0,
        }
        badges = _synthesize_persona(signals)
        labels = [b["label"] for b in badges]
        self.assertIn("Night Owl", labels)

    def test_fallback_badge_when_no_signals(self) -> None:
        signals = {
            "late_rate": 0,
            "weekend_boost": 0,
            "away_share": 0,
            "transit_days": 0,
            "dining_plays": 0,
            "holiday_count": 0,
        }
        badges = _synthesize_persona(signals)
        self.assertEqual(len(badges), 1)
        self.assertEqual(badges[0]["label"], "Music Lover")


# ---------------------------------------------------------------------------
# Smoke test for the render function
# ---------------------------------------------------------------------------


class TestRenderListeningLifestyle(unittest.TestCase):
    """Smoke tests for render_listening_lifestyle."""

    @patch("pages.listening_lifestyle.st")
    def test_shows_info_when_no_data(self, mock_st: MagicMock) -> None:
        mock_st.session_state.get.side_effect = lambda k, d=None: {
            "df": None,
            "swarm_df": None,
            "_loaded_config": None,
        }.get(k, d)
        render_listening_lifestyle()
        mock_st.info.assert_called()

    @patch("pages.listening_lifestyle._compute_lifestyle_data")
    @patch("pages.listening_lifestyle.load_assumptions", return_value={})
    @patch("pages.listening_lifestyle.st")
    def test_renders_without_error_with_minimal_data(
        self,
        mock_st: MagicMock,
        _mock_assumptions: MagicMock,
        mock_compute: MagicMock,
    ) -> None:
        df = _make_listens_df(
            hours=[1, 10, 14, 22],
            cities=["Home", "Home", "Away", "Home"],
            artists=["A", "B", "C", "A"],
            days=["2024-01-01", "2024-01-01", "2024-01-06", "2024-01-08"],
        )
        # Pre-built data so the render skips recomputation
        fake_data: dict = {
            "week": [],
            "transit": {
                "days": 0,
                "transit_df": pd.DataFrame(),
                "transit_avg": 0.0,
                "non_transit_avg": 0.0,
                "delta_pct": 0.0,
                "top_artists": pd.DataFrame(columns=["artist", "Plays"]),
            },
            "dining": {},
            "late_night": {
                "late_rate": 0.05,
                "top_artists": pd.DataFrame(columns=["artist", "plays"]),
                "hourly": pd.DataFrame(),
                "latest_session": None,
            },
            "holiday": [],
            "persona_signals": {
                "late_rate": 0.05,
                "weekend_boost": 0.0,
                "away_share": 0.0,
                "transit_days": 0,
                "dining_plays": 0,
                "holiday_count": 0,
            },
        }
        state: dict = {
            "df": df,
            "swarm_df": pd.DataFrame(),
            "_loaded_config": None,
            "_ll_cache_key": None,
            "_ll_data": fake_data,
        }
        mock_st.session_state.get.side_effect = lambda k, d=None: state.get(k, d)
        mock_st.session_state.__setitem__ = lambda self_, k, v: state.__setitem__(k, v)
        mock_st.session_state.__getitem__ = lambda self_, k: state[k]
        mock_compute.return_value = fake_data

        spinner_ctx = MagicMock()
        spinner_ctx.__enter__ = MagicMock(return_value=None)
        spinner_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.spinner.return_value = spinner_ctx
        mock_st.columns.return_value = [MagicMock() for _ in range(4)]

        render_listening_lifestyle()
        mock_st.header.assert_called_once_with("Listening Lifestyle")


if __name__ == "__main__":
    unittest.main()
