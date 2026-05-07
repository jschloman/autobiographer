"""Unit tests for the Music Atlas page (issue #66)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from pages.music_atlas import (
    _build_city_stats,
    render_music_atlas,
)


def _make_df() -> pd.DataFrame:
    """Return a minimal listening-history DataFrame with geo columns."""
    df = pd.DataFrame(
        {
            "artist": ["Artist A", "Artist B", "Artist A", "Artist C", "Artist A"],
            "album": ["Album 1", "Album 2", "Album 1", "Album 3", "Album 1"],
            "track": ["Track 1", "Track 2", "Track 3", "Track 4", "Track 5"],
            "timestamp": [
                1610000000,
                1610000100,
                1610000200,
                1610003600,
                1610007200,
            ],
            "date_text": pd.to_datetime(
                [
                    "2021-01-07 10:00",
                    "2021-01-07 10:01",
                    "2021-01-07 11:02",
                    "2021-01-07 12:00",
                    "2021-01-07 13:00",
                ]
            ),
            "lat": [64.13, 51.51, 64.13, 48.85, 64.13],
            "lng": [-21.82, -0.13, -21.82, 2.35, -21.82],
            "city": ["Reykjavik", "London", "Reykjavik", "Paris", "Reykjavik"],
            "country": ["Iceland", "UK", "Iceland", "France", "Iceland"],
        }
    )
    return df


class TestBuildCityStats(unittest.TestCase):
    """Tests for the _build_city_stats pure function."""

    def test_returns_dataframe(self) -> None:
        df = _make_df()
        result = _build_city_stats(df)
        self.assertIsInstance(result, pd.DataFrame)

    def test_row_per_city(self) -> None:
        df = _make_df()
        result = _build_city_stats(df)
        # Three distinct cities: Reykjavik, London, Paris
        self.assertEqual(len(result), 3)

    def test_required_columns_present(self) -> None:
        df = _make_df()
        result = _build_city_stats(df)
        for col in (
            "city",
            "country",
            "plays",
            "unique_artists",
            "top_artist",
            "top_track",
            "most_active_hour",
            "first_play",
            "last_play",
        ):
            self.assertIn(col, result.columns, f"Missing column: {col}")

    def test_play_counts_correct(self) -> None:
        df = _make_df()
        result = _build_city_stats(df).set_index("city")
        self.assertEqual(result.loc["Reykjavik", "plays"], 3)
        self.assertEqual(result.loc["London", "plays"], 1)
        self.assertEqual(result.loc["Paris", "plays"], 1)

    def test_unique_artists_correct(self) -> None:
        df = _make_df()
        result = _build_city_stats(df).set_index("city")
        self.assertEqual(result.loc["Reykjavik", "unique_artists"], 1)

    def test_top_artist_correct(self) -> None:
        df = _make_df()
        result = _build_city_stats(df).set_index("city")
        self.assertEqual(result.loc["Reykjavik", "top_artist"], "Artist A")

    def test_top_track_correct(self) -> None:
        df = _make_df()
        result = _build_city_stats(df).set_index("city")
        # Reykjavik: Track 1, Track 3, Track 5 — each once; any of them is valid
        self.assertIn(result.loc["Reykjavik", "top_track"], {"Track 1", "Track 3", "Track 5"})

    def test_most_active_hour_is_int(self) -> None:
        df = _make_df()
        result = _build_city_stats(df).set_index("city")
        hour = result.loc["Reykjavik", "most_active_hour"]
        self.assertIsInstance(int(hour), int)
        self.assertGreaterEqual(int(hour), 0)
        self.assertLessEqual(int(hour), 23)

    def test_empty_dataframe_returns_empty(self) -> None:
        result = _build_city_stats(pd.DataFrame())
        self.assertTrue(result.empty)

    def test_missing_geo_columns_returns_empty(self) -> None:
        df = pd.DataFrame(
            {"artist": ["A"], "track": ["T"], "date_text": pd.to_datetime(["2021-01-01"])}
        )
        result = _build_city_stats(df)
        self.assertTrue(result.empty)

    def test_lat_lng_preserved(self) -> None:
        df = _make_df()
        result = _build_city_stats(df).set_index("city")
        self.assertAlmostEqual(float(result.loc["Reykjavik", "lat"]), 64.13, places=1)


class TestRenderMusicAtlas(unittest.TestCase):
    """Integration tests for render_music_atlas UI entry point."""

    def _make_col_mock(self) -> MagicMock:
        """Return a column context-manager mock."""
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        return col

    @patch("streamlit.info")
    def test_empty_state_shows_info(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": None}):
            render_music_atlas()
        mock_info.assert_called_once()

    @patch("streamlit.info")
    def test_no_geo_data_shows_warning(self, mock_info: MagicMock) -> None:
        df = pd.DataFrame(
            {
                "artist": ["A"],
                "track": ["T"],
                "date_text": pd.to_datetime(["2021-01-01"]),
                "timestamp": [1609459200],
                "lat": [float("nan")],
                "lng": [float("nan")],
                "city": ["Unknown"],
                "country": ["Unknown"],
            }
        )
        with patch("streamlit.session_state", {"df": df}):
            render_music_atlas()
        mock_info.assert_called_once()

    @patch("streamlit.plotly_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.subheader")
    @patch("streamlit.header")
    @patch("streamlit.columns")
    def test_renders_with_valid_data(
        self,
        mock_cols: MagicMock,
        mock_header: MagicMock,
        mock_subheader: MagicMock,
        mock_df: MagicMock,
        mock_plotly: MagicMock,
    ) -> None:
        df = _make_df()
        col_mock = self._make_col_mock()
        mock_cols.side_effect = lambda n, **kw: [col_mock] * (n if isinstance(n, int) else len(n))

        with patch("streamlit.session_state", {"df": df}):
            render_music_atlas()

        mock_header.assert_called_once_with("Music Listening Atlas")
        mock_plotly.assert_called()
        mock_df.assert_called()

    @patch("streamlit.plotly_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.subheader")
    @patch("streamlit.header")
    @patch("streamlit.columns")
    @patch("streamlit.selectbox")
    def test_city_detail_card_rendered_on_selection(
        self,
        mock_select: MagicMock,
        mock_cols: MagicMock,
        mock_header: MagicMock,
        mock_subheader: MagicMock,
        mock_df: MagicMock,
        mock_plotly: MagicMock,
    ) -> None:
        df = _make_df()
        col_mock = self._make_col_mock()
        mock_cols.side_effect = lambda n, **kw: [col_mock] * (n if isinstance(n, int) else len(n))
        # Simulate user selecting "Reykjavik" from the city dropdown
        mock_select.return_value = "Reykjavik"

        with patch("streamlit.session_state", {"df": df}):
            render_music_atlas()

        # The detail card triggers a second plotly chart call for top artists
        self.assertGreaterEqual(mock_plotly.call_count, 2)


if __name__ == "__main__":
    unittest.main()
