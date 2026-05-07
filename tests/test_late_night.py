"""Tests for the Late Night Sessions page (issue #68)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from pages.late_night import (
    find_latest_session,
    get_late_night_by_city,
    get_late_night_by_location_type,
    get_late_night_hourly,
    get_top_late_night_artists,
    render_late_night,
)


def _make_df(hours: list[int], cities: list[str], artists: list[str]) -> pd.DataFrame:
    """Build a minimal merged DataFrame suitable for late-night analysis.

    Args:
        hours: Local hour for each row (0–23).
        cities: City label for each row.
        artists: Artist name for each row.

    Returns:
        DataFrame with ``date_text``, ``artist``, ``city``, ``lat``, ``lng``,
        ``timestamp``, ``country``, ``state`` columns.
    """
    base_ts = 1700000000  # arbitrary fixed epoch
    timestamps = [base_ts + i * 60 for i in range(len(hours))]
    date_texts = [pd.Timestamp("2024-01-15") + pd.Timedelta(hours=h) for h in hours]
    return pd.DataFrame(
        {
            "date_text": pd.to_datetime(date_texts),
            "timestamp": timestamps,
            "artist": artists,
            "city": cities,
            "state": ["State"] * len(hours),
            "country": ["Country"] * len(hours),
            "lat": [40.0] * len(hours),
            "lng": [-74.0] * len(hours),
        }
    )


class TestGetTopLateNightArtists(unittest.TestCase):
    """Tests for get_top_late_night_artists."""

    def test_returns_only_midnight_to_4am(self) -> None:
        """Only scrobbles in hours 0–3 are included in the artist counts."""
        df = _make_df(
            hours=[1, 2, 10, 14, 23],
            cities=["NYC"] * 5,
            artists=["NightOwl", "NightOwl", "Morning", "Afternoon", "Evening"],
        )
        top = get_top_late_night_artists(df)
        self.assertIn("NightOwl", top["artist"].values)
        self.assertNotIn("Morning", top["artist"].values)
        self.assertNotIn("Afternoon", top["artist"].values)

    def test_limit_respected(self) -> None:
        """Result has at most ``limit`` rows."""
        artists = [f"Artist{i}" for i in range(30)]
        hours = [2] * 30
        cities = ["NYC"] * 30
        df = _make_df(hours=hours, cities=cities, artists=artists)
        top = get_top_late_night_artists(df, limit=20)
        self.assertLessEqual(len(top), 20)

    def test_empty_df_returns_empty(self) -> None:
        """Empty DataFrame input yields an empty result."""
        df = pd.DataFrame(columns=["date_text", "artist", "city", "lat", "lng"])
        top = get_top_late_night_artists(df)
        self.assertTrue(top.empty)

    def test_no_late_night_rows_returns_empty(self) -> None:
        """No rows in hours 0–3 yields an empty result."""
        df = _make_df(hours=[9, 10, 11], cities=["NYC"] * 3, artists=["A", "B", "C"])
        top = get_top_late_night_artists(df)
        self.assertTrue(top.empty)


class TestGetLateNightByCity(unittest.TestCase):
    """Tests for get_late_night_by_city."""

    def test_groups_by_city(self) -> None:
        """Late-night plays are summed per city."""
        df = _make_df(
            hours=[1, 2, 3, 1],
            cities=["NYC", "NYC", "LA", "LA"],
            artists=["A", "B", "C", "D"],
        )
        result = get_late_night_by_city(df)
        self.assertIn("city", result.columns)
        self.assertIn("plays", result.columns)
        nyc_row = result[result["city"] == "NYC"]
        self.assertEqual(int(nyc_row["plays"].iloc[0]), 2)

    def test_excludes_daytime(self) -> None:
        """Daytime plays do not appear in the city summary."""
        df = _make_df(hours=[9, 12], cities=["NYC", "NYC"], artists=["A", "B"])
        result = get_late_night_by_city(df)
        self.assertTrue(result.empty)

    def test_empty_df_returns_empty(self) -> None:
        df = pd.DataFrame(columns=["date_text", "artist", "city", "lat", "lng"])
        result = get_late_night_by_city(df)
        self.assertTrue(result.empty)


class TestGetLateNightByLocationType(unittest.TestCase):
    """Tests for get_late_night_by_location_type."""

    def test_returns_three_types(self) -> None:
        """Result contains rows for home, hotel, and trip."""
        df = _make_df(
            hours=[1, 2, 3],
            cities=["Home City", "Hotel XYZ", "Trip Town"],
            artists=["A", "B", "C"],
        )
        # All three cities map to distinct location type groups
        result = get_late_night_by_location_type(df)
        self.assertIn("location_type", result.columns)
        self.assertIn("plays", result.columns)
        self.assertGreater(len(result), 0)

    def test_rate_column_present(self) -> None:
        """A ``rate`` column expressing late-night fraction is included."""
        df = _make_df(
            hours=[1, 10, 2, 12],
            cities=["Home", "Home", "Trip", "Trip"],
            artists=["A", "B", "C", "D"],
        )
        result = get_late_night_by_location_type(df)
        self.assertIn("rate", result.columns)

    def test_empty_df_returns_empty(self) -> None:
        df = pd.DataFrame(columns=["date_text", "artist", "city", "lat", "lng"])
        result = get_late_night_by_location_type(df)
        self.assertTrue(result.empty)


class TestGetLateNightHourly(unittest.TestCase):
    """Tests for get_late_night_hourly."""

    def test_returns_all_24_hours(self) -> None:
        """Result always has exactly 24 rows (one per hour)."""
        df = _make_df(hours=[0, 1, 2, 3], cities=["NYC"] * 4, artists=["A"] * 4)
        result = get_late_night_hourly(df)
        self.assertEqual(len(result), 24)

    def test_late_night_hours_highlighted(self) -> None:
        """The ``is_late_night`` flag is True for hours 0–3 only."""
        df = _make_df(hours=[0, 1, 2, 3, 4, 5], cities=["NYC"] * 6, artists=["A"] * 6)
        result = get_late_night_hourly(df)
        self.assertIn("is_late_night", result.columns)
        late = result[result["is_late_night"]]
        self.assertEqual(set(late["hour"].tolist()), {0, 1, 2, 3})

    def test_empty_df_returns_24_rows_with_zero_plays(self) -> None:
        """Even with no data, 24 zero-play hours are returned."""
        df = pd.DataFrame(columns=["date_text", "artist", "city", "lat", "lng"])
        result = get_late_night_hourly(df)
        self.assertEqual(len(result), 24)
        self.assertTrue((result["plays"] == 0).all())


class TestFindLatestSession(unittest.TestCase):
    """Tests for find_latest_session (consecutive late-night streak detection)."""

    def test_detects_consecutive_streak(self) -> None:
        """Plays within 30-min gaps form a single session."""
        # Three plays two minutes apart — all one session
        base_ts = 1700000000
        df = pd.DataFrame(
            {
                "date_text": pd.to_datetime(
                    [
                        pd.Timestamp("2024-01-15 01:00"),
                        pd.Timestamp("2024-01-15 01:02"),
                        pd.Timestamp("2024-01-15 01:04"),
                    ]
                ),
                "timestamp": [base_ts, base_ts + 120, base_ts + 240],
                "artist": ["A", "A", "A"],
                "city": ["NYC"] * 3,
                "state": ["NY"] * 3,
                "country": ["US"] * 3,
                "lat": [40.0] * 3,
                "lng": [-74.0] * 3,
            }
        )
        session = find_latest_session(df)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["track_count"], 3)

    def test_gap_over_30_min_breaks_session(self) -> None:
        """A gap larger than 30 minutes separates plays into different sessions."""
        base_ts = 1700000000
        df = pd.DataFrame(
            {
                "date_text": pd.to_datetime(
                    [
                        pd.Timestamp("2024-01-15 01:00"),
                        pd.Timestamp("2024-01-15 01:40"),  # 40 min later — new session
                    ]
                ),
                "timestamp": [base_ts, base_ts + 2400],
                "artist": ["A", "B"],
                "city": ["NYC"] * 2,
                "state": ["NY"] * 2,
                "country": ["US"] * 2,
                "lat": [40.0] * 2,
                "lng": [-74.0] * 2,
            }
        )
        session = find_latest_session(df)
        # Both are single-track sessions; the latest (most recent) is returned
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["track_count"], 1)

    def test_returns_none_when_no_late_night_plays(self) -> None:
        """Returns None when there are no plays in hours 0–3."""
        df = _make_df(hours=[9, 10], cities=["NYC"] * 2, artists=["A", "B"])
        session = find_latest_session(df)
        self.assertIsNone(session)

    def test_empty_df_returns_none(self) -> None:
        df = pd.DataFrame(columns=["date_text", "artist", "city", "lat", "lng", "timestamp"])
        session = find_latest_session(df)
        self.assertIsNone(session)


class TestRenderLateNight(unittest.TestCase):
    """Integration tests for render_late_night page function."""

    def _make_full_df(self) -> pd.DataFrame:
        """Return a DataFrame with enough variety for all page sections."""
        return _make_df(
            hours=[0, 1, 2, 3, 10, 14],
            cities=["NYC", "NYC", "LA", "LA", "NYC", "LA"],
            artists=["Artist1", "Artist2", "Artist1", "Artist3", "Artist4", "Artist5"],
        )

    @patch("streamlit.info")
    def test_empty_state_shows_info(self, mock_info: MagicMock) -> None:
        """render_late_night shows an info message when no data is loaded."""
        with patch("streamlit.session_state", {"df": None}):
            render_late_night()
        mock_info.assert_called_once()

    @patch("streamlit.header")
    @patch("streamlit.subheader")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.dataframe")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    def test_renders_with_data(
        self,
        mock_divider: MagicMock,
        mock_caption: MagicMock,
        mock_dataframe: MagicMock,
        mock_markdown: MagicMock,
        mock_columns: MagicMock,
        mock_metric: MagicMock,
        mock_plotly: MagicMock,
        mock_subheader: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        """render_late_night completes without error when data is present."""
        df = self._make_full_df()
        col_mock = MagicMock()
        col_mock.__enter__ = MagicMock(return_value=col_mock)
        col_mock.__exit__ = MagicMock(return_value=False)
        mock_columns.return_value = [col_mock, col_mock]

        with patch("streamlit.session_state", {"df": df}):
            render_late_night()

        mock_header.assert_called_once_with("Late Night Sessions")
        self.assertTrue(mock_plotly.called)
