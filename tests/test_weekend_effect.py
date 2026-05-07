"""Tests for the Weekend Effect page — weekend vs. weekday listening by location."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from pages.weekend_effect import (
    _add_location_context,
    _add_weekend_columns,
    _compute_context_stats,
    _get_new_vs_familiar_ratio,
    render_weekend_effect,
)


def _make_df(home_city: str = "Reykjavik") -> pd.DataFrame:
    """Create a minimal merged DataFrame with all required columns."""
    dates = pd.to_datetime(
        [
            "2024-01-01 09:00",  # Monday
            "2024-01-02 14:00",  # Tuesday
            "2024-01-06 10:00",  # Saturday
            "2024-01-07 11:00",  # Sunday
            "2024-01-08 08:00",  # Monday — away city
            "2024-01-13 20:00",  # Saturday — away city
        ]
    )
    return pd.DataFrame(
        {
            "artist": ["Artist A", "Artist B", "Artist A", "Artist C", "Artist D", "Artist A"],
            "album": ["Album 1", "Album 2", "Album 1", "Album 3", "Album 4", "Album 1"],
            "track": ["T1", "T2", "T3", "T4", "T5", "T3"],
            "date_text": dates,
            "city": [home_city, home_city, home_city, home_city, "London", "London"],
            "country": ["Iceland", "Iceland", "Iceland", "Iceland", "UK", "UK"],
        }
    )


class TestAddWeekendColumns(unittest.TestCase):
    """Tests for _add_weekend_columns()."""

    def test_adds_day_of_week_and_is_weekend(self) -> None:
        df = _make_df()
        out = _add_weekend_columns(df)
        self.assertIn("day_of_week", out.columns)
        self.assertIn("is_weekend", out.columns)

    def test_monday_is_not_weekend(self) -> None:
        df = _make_df()
        out = _add_weekend_columns(df)
        # Row 0 is Monday 2024-01-01
        self.assertFalse(out.iloc[0]["is_weekend"])

    def test_saturday_is_weekend(self) -> None:
        df = _make_df()
        out = _add_weekend_columns(df)
        # Row 2 is Saturday 2024-01-06
        self.assertTrue(out.iloc[2]["is_weekend"])

    def test_sunday_is_weekend(self) -> None:
        df = _make_df()
        out = _add_weekend_columns(df)
        # Row 3 is Sunday 2024-01-07
        self.assertTrue(out.iloc[3]["is_weekend"])


class TestAddLocationContext(unittest.TestCase):
    """Tests for _add_location_context()."""

    def test_adds_is_home_column(self) -> None:
        df = _make_df("Reykjavik")
        out = _add_location_context(df, "Reykjavik")
        self.assertIn("is_home", out.columns)

    def test_home_city_rows_are_is_home_true(self) -> None:
        df = _make_df("Reykjavik")
        out = _add_location_context(df, "Reykjavik")
        home_rows = out[out["city"] == "Reykjavik"]
        self.assertTrue(home_rows["is_home"].all())

    def test_away_city_rows_are_is_home_false(self) -> None:
        df = _make_df("Reykjavik")
        out = _add_location_context(df, "Reykjavik")
        away_rows = out[out["city"] == "London"]
        self.assertFalse(away_rows["is_home"].any())

    def test_case_insensitive_matching(self) -> None:
        df = _make_df("reykjavik")
        out = _add_location_context(df, "Reykjavik")
        home_rows = out[out["city"].str.lower() == "reykjavik"]
        self.assertTrue(home_rows["is_home"].all())


class TestGetNewVsFamiliarRatio(unittest.TestCase):
    """Tests for _get_new_vs_familiar_ratio()."""

    def test_all_familiar_returns_zero(self) -> None:
        prior = {"Artist A", "Artist B"}
        current = {"Artist A", "Artist B"}
        ratio = _get_new_vs_familiar_ratio(current, prior)
        self.assertAlmostEqual(ratio, 0.0)

    def test_all_new_returns_one(self) -> None:
        prior: set[str] = set()
        current = {"Artist X", "Artist Y"}
        ratio = _get_new_vs_familiar_ratio(current, prior)
        self.assertAlmostEqual(ratio, 1.0)

    def test_half_new_returns_half(self) -> None:
        prior = {"Artist A"}
        current = {"Artist A", "Artist X"}
        ratio = _get_new_vs_familiar_ratio(current, prior)
        self.assertAlmostEqual(ratio, 0.5)

    def test_empty_current_returns_zero(self) -> None:
        prior = {"Artist A"}
        current: set[str] = set()
        ratio = _get_new_vs_familiar_ratio(current, prior)
        self.assertAlmostEqual(ratio, 0.0)


class TestComputeContextStats(unittest.TestCase):
    """Tests for _compute_context_stats()."""

    def _make_enriched_df(self) -> pd.DataFrame:
        df = _make_df("Reykjavik")
        df = _add_weekend_columns(df)
        df = _add_location_context(df, "Reykjavik")
        return df

    def test_returns_four_contexts(self) -> None:
        df = self._make_enriched_df()
        stats = _compute_context_stats(df)
        self.assertEqual(len(stats), 4)

    def test_context_keys_present(self) -> None:
        df = self._make_enriched_df()
        stats = _compute_context_stats(df)
        keys = {(s["is_weekend"], s["is_home"]) for s in stats}
        expected = {
            (False, True),
            (True, True),
            (False, False),
            (True, False),
        }
        self.assertEqual(keys, expected)

    def test_each_context_has_required_fields(self) -> None:
        df = self._make_enriched_df()
        stats = _compute_context_stats(df)
        required = {"is_weekend", "is_home", "label", "play_count", "top_artists", "peak_hour"}
        for stat in stats:
            self.assertTrue(required.issubset(stat.keys()), f"Missing keys in {stat}")

    def test_play_count_positive(self) -> None:
        df = self._make_enriched_df()
        stats = _compute_context_stats(df)
        for stat in stats:
            self.assertGreaterEqual(stat["play_count"], 0)

    def test_top_artists_limited_to_three(self) -> None:
        df = self._make_enriched_df()
        stats = _compute_context_stats(df)
        for stat in stats:
            self.assertLessEqual(len(stat["top_artists"]), 3)


class TestRenderWeekendEffect(unittest.TestCase):
    """Integration-level tests for render_weekend_effect()."""

    def _make_session_df(self) -> pd.DataFrame:
        df = _make_df("Reykjavik")
        return df

    @patch("streamlit.info")
    def test_empty_state_shows_info(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": None}):
            render_weekend_effect()
        mock_info.assert_called_once()

    @patch("streamlit.info")
    def test_no_city_column_shows_info(self, mock_info: MagicMock) -> None:
        df = pd.DataFrame(
            {
                "artist": ["A"],
                "date_text": pd.to_datetime(["2024-01-01"]),
            }
        )
        with patch("streamlit.session_state", {"df": df}):
            render_weekend_effect()
        mock_info.assert_called_once()

    @patch("streamlit.plotly_chart")
    @patch("streamlit.metric")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.header")
    @patch("streamlit.columns")
    @patch("streamlit.divider")
    @patch("streamlit.caption")
    @patch("streamlit.selectbox")
    def test_renders_with_data(
        self,
        mock_selectbox: MagicMock,
        mock_caption: MagicMock,
        mock_divider: MagicMock,
        mock_cols: MagicMock,
        mock_header: MagicMock,
        mock_subheader: MagicMock,
        mock_markdown: MagicMock,
        mock_metric: MagicMock,
        mock_plotly: MagicMock,
    ) -> None:
        df = self._make_session_df()
        mock_selectbox.return_value = "All"
        # Provide enough column mock lists for all st.columns() calls:
        # 1. row 1 of 2×2 grid, 2. row 2 of 2×2 grid, 3. heatmap side-by-side
        mock_cols.side_effect = [
            [MagicMock(), MagicMock()],  # 2×2 grid row 1
            [MagicMock(), MagicMock()],  # 2×2 grid row 2
            [MagicMock(), MagicMock()],  # heatmap (Home | Away)
        ]

        with patch(
            "streamlit.session_state",
            {"df": df, "assumptions": {"defaults": {"city": "Reykjavik"}}},
        ):
            render_weekend_effect()

        mock_header.assert_called_once()
        # At least one chart rendered
        self.assertTrue(mock_plotly.called or mock_metric.called)


if __name__ == "__main__":
    unittest.main()
