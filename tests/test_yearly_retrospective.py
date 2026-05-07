"""Tests for pages/yearly_retrospective.py — Year in Review page."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from pages.yearly_retrospective import (
    _compute_new_artist_discoveries,
    _compute_year_stats,
    _filter_by_year,
    render_yearly_retrospective,
)


def _make_df() -> pd.DataFrame:
    """Return a minimal listening history spanning two calendar years."""
    rows = [
        # 2022 tracks
        ("Artist A", "Album A", "Track 1", "2022-03-15 10:00"),
        ("Artist A", "Album A", "Track 2", "2022-03-16 11:00"),
        ("Artist B", "Album B", "Track 3", "2022-06-01 08:00"),
        ("Artist B", "Album B", "Track 4", "2022-06-02 09:00"),
        ("Artist C", "Album C", "Track 5", "2022-09-10 14:00"),
        # 2023 tracks — Artist D is new in 2023
        ("Artist A", "Album A", "Track 1", "2023-01-05 10:00"),
        ("Artist B", "Album B", "Track 3", "2023-02-14 12:00"),
        ("Artist D", "Album D", "Track 6", "2023-04-20 16:00"),
        ("Artist D", "Album D", "Track 7", "2023-07-04 18:00"),
        ("Artist A", "Album A", "Track 2", "2023-11-30 09:00"),
    ]
    df = pd.DataFrame(rows, columns=["artist", "album", "track", "date_text"])
    df["date_text"] = pd.to_datetime(df["date_text"])
    df["timestamp"] = df["date_text"].astype("int64") // 10**9
    df["country"] = ["Iceland"] * 5 + ["Iceland", "UK", "Iceland", "UK", "Iceland"]
    df["city"] = ["Reykjavik"] * 5 + [
        "Reykjavik",
        "London",
        "Reykjavik",
        "London",
        "Reykjavik",
    ]
    df["lat"] = [64.13] * 5 + [64.13, 51.51, 64.13, 51.51, 64.13]
    df["lng"] = [-21.82] * 5 + [-21.82, -0.13, -21.82, -0.13, -21.82]
    return df


class TestFilterByYear(unittest.TestCase):
    """Tests for _filter_by_year."""

    def test_returns_correct_year_rows(self) -> None:
        df = _make_df()
        result = _filter_by_year(df, 2022)
        self.assertEqual(len(result), 5)
        self.assertTrue((result["date_text"].dt.year == 2022).all())

    def test_empty_when_year_absent(self) -> None:
        df = _make_df()
        result = _filter_by_year(df, 2000)
        self.assertTrue(result.empty)

    def test_returns_all_rows_for_year_2023(self) -> None:
        df = _make_df()
        result = _filter_by_year(df, 2023)
        self.assertEqual(len(result), 5)


class TestComputeNewArtistDiscoveries(unittest.TestCase):
    """Tests for _compute_new_artist_discoveries."""

    def test_artist_d_is_new_in_2023(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2023)
        new_artists = _compute_new_artist_discoveries(df, year_df, 2023)
        self.assertIn("Artist D", new_artists)

    def test_existing_artists_not_counted_as_new(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2023)
        new_artists = _compute_new_artist_discoveries(df, year_df, 2023)
        self.assertNotIn("Artist A", new_artists)
        self.assertNotIn("Artist B", new_artists)

    def test_all_artists_new_for_first_year(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2022)
        new_artists = _compute_new_artist_discoveries(df, year_df, 2022)
        # Every artist in 2022 is new (no prior data)
        self.assertEqual(len(new_artists), 3)

    def test_returns_empty_for_empty_year_df(self) -> None:
        df = _make_df()
        new_artists = _compute_new_artist_discoveries(df, pd.DataFrame(), 2025)
        self.assertEqual(len(new_artists), 0)


class TestComputeYearStats(unittest.TestCase):
    """Tests for _compute_year_stats."""

    def test_total_scrobbles(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2022)
        stats = _compute_year_stats(df, year_df, 2022)
        self.assertEqual(stats["total_scrobbles"], 5)

    def test_estimated_hours(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2022)
        stats = _compute_year_stats(df, year_df, 2022)
        # 5 tracks × 3.5 min / 60 ≈ 0.29 hours
        self.assertAlmostEqual(stats["estimated_hours"], 5 * 3.5 / 60, places=2)

    def test_unique_countries(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2023)
        stats = _compute_year_stats(df, year_df, 2023)
        self.assertEqual(stats["unique_countries"], 2)

    def test_new_discoveries_count(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2023)
        stats = _compute_year_stats(df, year_df, 2023)
        self.assertEqual(stats["new_artists"], 1)

    def test_top_artist(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2022)
        stats = _compute_year_stats(df, year_df, 2022)
        self.assertIn("top_artist", stats)
        self.assertIn(stats["top_artist"], ["Artist A", "Artist B"])

    def test_most_active_month_present(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2022)
        stats = _compute_year_stats(df, year_df, 2022)
        self.assertIn("most_active_month", stats)

    def test_longest_streak_present(self) -> None:
        df = _make_df()
        year_df = _filter_by_year(df, 2022)
        stats = _compute_year_stats(df, year_df, 2022)
        self.assertIn("longest_streak", stats)
        self.assertGreaterEqual(stats["longest_streak"], 1)

    def test_empty_year_returns_zero_stats(self) -> None:
        df = _make_df()
        stats = _compute_year_stats(df, pd.DataFrame(), 2025)
        self.assertEqual(stats["total_scrobbles"], 0)
        self.assertEqual(stats["new_artists"], 0)


class TestRenderYearlyRetrospective(unittest.TestCase):
    """Integration-style tests for render_yearly_retrospective (Streamlit mocked)."""

    def setUp(self) -> None:
        self.df = _make_df()

    @patch("streamlit.info")
    def test_empty_state_shown_when_no_data(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": None}):
            render_yearly_retrospective()
        mock_info.assert_called_once()

    @patch("streamlit.header")
    @patch("streamlit.selectbox")
    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    def test_renders_with_valid_data(
        self,
        mock_caption: MagicMock,
        mock_subheader: MagicMock,
        mock_plotly: MagicMock,
        mock_metric: MagicMock,
        mock_cols: MagicMock,
        mock_selectbox: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_selectbox.return_value = 2022
        mock_cols.return_value = [MagicMock()] * 4

        with patch("streamlit.session_state", {"df": self.df}):
            render_yearly_retrospective()

        mock_header.assert_called_once_with("Year in Review")
        self.assertTrue(mock_metric.called)

    @patch("streamlit.header")
    @patch("streamlit.selectbox")
    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    def test_year_selector_shown(
        self,
        mock_caption: MagicMock,
        mock_subheader: MagicMock,
        mock_plotly: MagicMock,
        mock_metric: MagicMock,
        mock_cols: MagicMock,
        mock_selectbox: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_selectbox.return_value = 2023
        mock_cols.return_value = [MagicMock()] * 4

        with patch("streamlit.session_state", {"df": self.df}):
            render_yearly_retrospective()

        # Selectbox should be called to pick the year
        mock_selectbox.assert_called()
        call_args = mock_selectbox.call_args_list[0]
        self.assertIn("Year", str(call_args))

    @patch("streamlit.header")
    @patch("streamlit.selectbox")
    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.subheader")
    @patch("streamlit.caption")
    def test_charts_rendered(
        self,
        mock_caption: MagicMock,
        mock_subheader: MagicMock,
        mock_plotly: MagicMock,
        mock_metric: MagicMock,
        mock_cols: MagicMock,
        mock_selectbox: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_selectbox.return_value = 2022
        mock_cols.return_value = [MagicMock()] * 4

        with patch("streamlit.session_state", {"df": self.df}):
            render_yearly_retrospective()

        # At least the monthly bar chart and top-5 charts should render
        self.assertGreater(mock_plotly.call_count, 0)


if __name__ == "__main__":
    unittest.main()
