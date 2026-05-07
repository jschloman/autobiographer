"""Tests for the In Transit page and supporting analysis utilities (Issue #61)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from analysis_utils import (
    TRANSIT_CATEGORY_KEYWORDS,
    get_avg_plays_per_day,
    get_longest_transit_session,
    get_new_artist_discovery_rate,
    get_transit_days,
    get_transit_listening_hours,
    load_swarm_data,
    split_transit_listens,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listens(dates: list[str], artists: list[str] | None = None) -> pd.DataFrame:
    """Build a minimal listening history DataFrame."""
    n = len(dates)
    if artists is None:
        artists = [f"Artist {i}" for i in range(n)]
    return pd.DataFrame(
        {
            "artist": artists,
            "track": [f"Track {i}" for i in range(n)],
            "album": [f"Album {i}" for i in range(n)],
            "timestamp": list(range(1_700_000_000, 1_700_000_000 + n)),
            "date_text": pd.to_datetime(dates),
        }
    )


def _make_swarm_dir_with_categories(tmp_dir: str, items: list[dict]) -> str:
    """Write a checkins1.json with the given items into tmp_dir and return tmp_dir."""
    payload = {"items": items}
    with open(os.path.join(tmp_dir, "checkins1.json"), "w") as f:
        json.dump(payload, f)
    return tmp_dir


# ---------------------------------------------------------------------------
# load_swarm_data — venue_category parsing
# ---------------------------------------------------------------------------


class TestLoadSwarmDataCategory(unittest.TestCase):
    """venue_category is captured from venue.categories[0].name."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def test_category_extracted_when_present(self) -> None:
        items = [
            {
                "createdAt": 1_700_000_000,
                "timeZoneOffset": 0,
                "venue": {
                    "name": "JFK Airport",
                    "categories": [{"name": "Airport"}],
                    "location": {"city": "New York", "country": "United States"},
                },
            }
        ]
        _make_swarm_dir_with_categories(self.tmp, items)
        df = load_swarm_data(self.tmp)
        self.assertIn("venue_category", df.columns)
        self.assertEqual(df.iloc[0]["venue_category"], "Airport")

    def test_category_empty_when_missing(self) -> None:
        items = [
            {
                "createdAt": 1_700_000_000,
                "timeZoneOffset": 0,
                "venue": {
                    "name": "Coffee Shop",
                    "location": {"city": "London", "country": "United Kingdom"},
                },
            }
        ]
        _make_swarm_dir_with_categories(self.tmp, items)
        df = load_swarm_data(self.tmp)
        self.assertEqual(df.iloc[0]["venue_category"], "")

    def test_first_category_only_used(self) -> None:
        items = [
            {
                "createdAt": 1_700_000_001,
                "timeZoneOffset": 0,
                "venue": {
                    "name": "Hub",
                    "categories": [{"name": "Transit"}, {"name": "Bus Station"}],
                    "location": {"city": "Chicago", "country": "United States"},
                },
            }
        ]
        _make_swarm_dir_with_categories(self.tmp, items)
        df = load_swarm_data(self.tmp)
        self.assertEqual(df.iloc[0]["venue_category"], "Transit")

    def test_empty_dir_returns_venue_category_column(self) -> None:
        df = load_swarm_data(self.tmp)  # no files
        self.assertIn("venue_category", df.columns)
        self.assertTrue(df.empty)


# ---------------------------------------------------------------------------
# get_transit_days
# ---------------------------------------------------------------------------


class TestGetTransitDays(unittest.TestCase):
    """get_transit_days returns date strings for transit check-in days."""

    def _swarm(self, cats: list[str], timestamps: list[int]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "venue_category": cats,
                "venue": ["v"] * len(cats),
            }
        )

    def test_returns_dates_for_airport_checkins(self) -> None:
        ts = int(pd.Timestamp("2023-06-12").timestamp())
        df = self._swarm(["Airport"], [ts])
        days = get_transit_days(df)
        self.assertIn("2023-06-12", days)

    def test_returns_dates_for_train_station(self) -> None:
        ts = int(pd.Timestamp("2023-06-15").timestamp())
        df = self._swarm(["Train Station"], [ts])
        days = get_transit_days(df)
        self.assertIn("2023-06-15", days)

    def test_ignores_non_transit_categories(self) -> None:
        ts = int(pd.Timestamp("2023-06-20").timestamp())
        df = self._swarm(["Coffee Shop"], [ts])
        days = get_transit_days(df)
        self.assertEqual(len(days), 0)

    def test_empty_swarm_returns_empty_set(self) -> None:
        days = get_transit_days(pd.DataFrame())
        self.assertEqual(days, set())

    def test_missing_venue_category_column(self) -> None:
        df = pd.DataFrame({"timestamp": [1_700_000_000], "venue": ["Place"]})
        days = get_transit_days(df)
        self.assertEqual(days, set())

    def test_case_insensitive_matching(self) -> None:
        ts = int(pd.Timestamp("2023-07-01").timestamp())
        df = self._swarm(["airport"], [ts])  # lowercase
        days = get_transit_days(df)
        self.assertIn("2023-07-01", days)

    def test_multiple_transit_days(self) -> None:
        ts1 = int(pd.Timestamp("2023-08-01").timestamp())
        ts2 = int(pd.Timestamp("2023-08-05").timestamp())
        df = self._swarm(["Airport", "Metro Station"], [ts1, ts2])
        days = get_transit_days(df)
        self.assertEqual(len(days), 2)

    def test_transit_category_keywords_list_non_empty(self) -> None:
        self.assertGreater(len(TRANSIT_CATEGORY_KEYWORDS), 0)
        self.assertIn("Airport", TRANSIT_CATEGORY_KEYWORDS)


# ---------------------------------------------------------------------------
# split_transit_listens
# ---------------------------------------------------------------------------


class TestSplitTransitListens(unittest.TestCase):
    """split_transit_listens correctly partitions a listening DataFrame."""

    def test_partitions_correctly(self) -> None:
        transit_days = {"2023-06-12", "2023-06-15"}
        df = _make_listens(
            ["2023-06-12", "2023-06-14", "2023-06-15", "2023-06-20"],
            ["Artist A", "Artist B", "Artist C", "Artist D"],
        )
        t_df, h_df = split_transit_listens(df, transit_days)
        self.assertEqual(len(t_df), 2)
        self.assertEqual(len(h_df), 2)
        self.assertSetEqual(set(t_df["artist"]), {"Artist A", "Artist C"})

    def test_all_home_when_no_overlap(self) -> None:
        df = _make_listens(["2023-01-01", "2023-01-02"])
        t_df, h_df = split_transit_listens(df, {"2024-01-01"})
        self.assertEqual(len(t_df), 0)
        self.assertEqual(len(h_df), 2)

    def test_empty_listens_returns_empty_both(self) -> None:
        t_df, h_df = split_transit_listens(pd.DataFrame(), {"2023-06-12"})
        self.assertTrue(t_df.empty)
        self.assertTrue(h_df.empty)


# ---------------------------------------------------------------------------
# get_avg_plays_per_day
# ---------------------------------------------------------------------------


class TestGetAvgPlaysPerDay(unittest.TestCase):
    def test_basic_average(self) -> None:
        df = _make_listens(["2023-01-01", "2023-01-01", "2023-01-02"])
        avg = get_avg_plays_per_day(df)
        self.assertAlmostEqual(avg, 1.5)

    def test_empty_returns_zero(self) -> None:
        self.assertEqual(get_avg_plays_per_day(pd.DataFrame()), 0.0)

    def test_single_day(self) -> None:
        df = _make_listens(["2023-05-01"] * 10)
        avg = get_avg_plays_per_day(df)
        self.assertAlmostEqual(avg, 10.0)


# ---------------------------------------------------------------------------
# get_new_artist_discovery_rate
# ---------------------------------------------------------------------------


class TestGetNewArtistDiscoveryRate(unittest.TestCase):
    def test_discovery_on_transit_day(self) -> None:
        # Transit subset: Artist A first heard on 2023-06-12
        # Full dataset: Artist A first appeared on 2023-06-12 (transit day)
        full = _make_listens(
            ["2023-06-11", "2023-06-12", "2023-06-13"],
            ["Artist B", "Artist A", "Artist B"],
        )
        transit = _make_listens(["2023-06-12"], ["Artist A"])
        count, rate = get_new_artist_discovery_rate(transit, full)
        self.assertEqual(count, 1)
        self.assertAlmostEqual(rate, 1.0)

    def test_no_discoveries(self) -> None:
        # Artist A first heard before the transit window
        full = _make_listens(
            ["2023-06-01", "2023-06-12"],
            ["Artist A", "Artist A"],
        )
        transit = _make_listens(["2023-06-12"], ["Artist A"])
        count, rate = get_new_artist_discovery_rate(transit, full)
        self.assertEqual(count, 0)
        self.assertAlmostEqual(rate, 0.0)

    def test_empty_inputs(self) -> None:
        count, rate = get_new_artist_discovery_rate(pd.DataFrame(), pd.DataFrame())
        self.assertEqual(count, 0)
        self.assertAlmostEqual(rate, 0.0)


# ---------------------------------------------------------------------------
# get_longest_transit_session
# ---------------------------------------------------------------------------


class TestGetLongestTransitSession(unittest.TestCase):
    def test_single_session(self) -> None:
        # 5 tracks 3 minutes apart → one session of 5
        base = 1_700_000_000
        df = pd.DataFrame({"timestamp": [base + i * 180 for i in range(5)]})
        self.assertEqual(get_longest_transit_session(df, gap_minutes=60), 5)

    def test_two_sessions_returns_longer(self) -> None:
        base = 1_700_000_000
        session1 = [base + i * 180 for i in range(3)]  # 3 tracks
        session2 = [base + 7200 + i * 180 for i in range(6)]  # 2h gap, 6 tracks
        df = pd.DataFrame({"timestamp": session1 + session2})
        self.assertEqual(get_longest_transit_session(df, gap_minutes=60), 6)

    def test_empty_returns_zero(self) -> None:
        self.assertEqual(get_longest_transit_session(pd.DataFrame()), 0)

    def test_single_track(self) -> None:
        df = pd.DataFrame({"timestamp": [1_700_000_000]})
        self.assertEqual(get_longest_transit_session(df, gap_minutes=60), 1)


# ---------------------------------------------------------------------------
# get_transit_listening_hours
# ---------------------------------------------------------------------------


class TestGetTransitListeningHours(unittest.TestCase):
    def test_returns_hourly_counts(self) -> None:
        df = _make_listens(["2023-06-12 10:00", "2023-06-12 10:30", "2023-06-12 14:00"])
        hourly = get_transit_listening_hours(df)
        self.assertIn("hour", hourly.columns)
        self.assertIn("Plays", hourly.columns)
        hour_10 = hourly[hourly["hour"] == 10]["Plays"].values
        self.assertEqual(hour_10[0], 2)

    def test_empty_df_returns_empty(self) -> None:
        hourly = get_transit_listening_hours(pd.DataFrame())
        self.assertTrue(hourly.empty)


# ---------------------------------------------------------------------------
# render_in_transit (UI smoke tests)
# ---------------------------------------------------------------------------


class TestRenderInTransit(unittest.TestCase):
    """Smoke tests for the Streamlit page render function."""

    def _transit_swarm(self) -> pd.DataFrame:
        """Return a minimal swarm DataFrame with one Airport check-in."""
        ts = int(pd.Timestamp("2023-06-12").timestamp())
        return pd.DataFrame(
            {
                "timestamp": [ts],
                "venue": ["JFK Airport"],
                "venue_category": ["Airport"],
                "city": ["New York"],
                "state": ["NY"],
                "country": ["United States"],
                "lat": [40.6413],
                "lng": [-73.7781],
                "offset": [0],
            }
        )

    def _listens(self) -> pd.DataFrame:
        return _make_listens(
            ["2023-06-12", "2023-06-13", "2023-06-12"],
            ["Artist A", "Artist B", "Artist C"],
        )

    @patch("streamlit.header")
    @patch("streamlit.caption")
    @patch("streamlit.info")
    def test_renders_info_when_no_listens(
        self, mock_info: MagicMock, _cap: MagicMock, _hdr: MagicMock
    ) -> None:
        with patch("streamlit.session_state", {"df": None, "swarm_df": None}):
            from pages.in_transit import render_in_transit

            render_in_transit()
        mock_info.assert_called_once()

    @patch("streamlit.header")
    @patch("streamlit.caption")
    @patch("streamlit.info")
    def test_renders_info_when_no_swarm(
        self, mock_info: MagicMock, _cap: MagicMock, _hdr: MagicMock
    ) -> None:
        listens = self._listens()
        with patch("streamlit.session_state", {"df": listens, "swarm_df": None}):
            from pages.in_transit import render_in_transit

            render_in_transit()
        mock_info.assert_called_once()

    @patch("streamlit.header")
    @patch("streamlit.caption")
    @patch("streamlit.warning")
    def test_renders_warning_when_no_transit_checkins(
        self, mock_warning: MagicMock, _cap: MagicMock, _hdr: MagicMock
    ) -> None:
        listens = self._listens()
        swarm = pd.DataFrame(
            {
                "timestamp": [1_700_000_000],
                "venue": ["Coffee Shop"],
                "venue_category": ["Cafe"],
                "city": ["London"],
                "state": ["England"],
                "country": ["United Kingdom"],
                "lat": [51.5],
                "lng": [-0.1],
                "offset": [0],
            }
        )
        with patch("streamlit.session_state", {"df": listens, "swarm_df": swarm}):
            from pages.in_transit import render_in_transit

            render_in_transit()
        mock_warning.assert_called_once()

    @patch("streamlit.plotly_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.markdown")
    @patch("streamlit.metric")
    @patch("streamlit.subheader")
    @patch("streamlit.expander")
    @patch("streamlit.columns")
    @patch("streamlit.header")
    @patch("streamlit.caption")
    def test_renders_full_page(
        self,
        _cap: MagicMock,
        _hdr: MagicMock,
        mock_columns: MagicMock,
        mock_expander: MagicMock,
        _sub: MagicMock,
        _metric: MagicMock,
        _md: MagicMock,
        _df: MagicMock,
        _pc: MagicMock,
    ) -> None:
        # Arrange column mocks — st.columns() is called with 4, 2, 2, and 2 args.
        def _make_col() -> MagicMock:
            c = MagicMock()
            c.__enter__ = MagicMock(return_value=c)
            c.__exit__ = MagicMock(return_value=False)
            return c

        def _columns_side_effect(n: int) -> list[MagicMock]:
            return [_make_col() for _ in range(n)]

        mock_columns.side_effect = _columns_side_effect

        exp_ctx = MagicMock()
        exp_ctx.__enter__ = MagicMock(return_value=exp_ctx)
        exp_ctx.__exit__ = MagicMock(return_value=False)
        mock_expander.return_value = exp_ctx

        listens = self._listens()
        swarm = self._transit_swarm()

        with patch("streamlit.session_state", {"df": listens, "swarm_df": swarm}):
            from pages.in_transit import render_in_transit

            render_in_transit()

        # The page must have called st.plotly_chart at least once
        self.assertGreater(_pc.call_count, 0)


if __name__ == "__main__":
    unittest.main()
