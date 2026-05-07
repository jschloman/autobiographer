"""Tests for pages/vacation_mode.py render functions."""

from __future__ import annotations

import unittest
from unittest.mock import ANY, MagicMock, patch

import pandas as pd

from pages.vacation_mode import (
    render_discovery_chart,
    render_genre_comparison,
    render_stat_cards,
    render_timeline_chart,
    render_vacation_mode,
)


def _make_labeled_df() -> pd.DataFrame:
    """Return a small labeled DataFrame with both home and trip rows."""
    df = pd.DataFrame(
        {
            "artist": ["A", "B", "C", "D", "A", "E"],
            "album": ["X", "X", "Y", "Y", "X", "Z"],
            "track": ["t1", "t2", "t3", "t4", "t1", "t5"],
            "timestamp": [
                1610000000,
                1610086400,
                1610172800,
                1610259200,
                1610345600,
                1610432000,
            ],
            "date_text": pd.to_datetime(
                [
                    "2021-01-07",
                    "2021-01-08",
                    "2021-01-09",
                    "2021-01-10",
                    "2021-01-11",
                    "2021-01-12",
                ]
            ),
            "context": ["home", "home", "trip", "trip", "home", "home"],
        }
    )
    return df


class TestRenderStatCards(unittest.TestCase):
    """Tests for render_stat_cards."""

    @patch("streamlit.metric")
    @patch("streamlit.subheader")
    @patch("streamlit.columns")
    @patch("streamlit.container")
    def test_renders_home_and_trip_sections(
        self,
        mock_container: MagicMock,
        mock_cols: MagicMock,
        mock_subheader: MagicMock,
        mock_metric: MagicMock,
    ) -> None:
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_container.return_value = ctx
        mock_cols.return_value = [ctx, ctx]

        stats = {
            "home": {
                "avg_daily_scrobbles": 10.0,
                "unique_artists_per_day": 3.0,
                "listening_hours": 2.5,
                "top_artist": "Artist A",
            },
            "trip": {
                "avg_daily_scrobbles": 5.0,
                "unique_artists_per_day": 2.0,
                "listening_hours": 1.0,
                "top_artist": "Artist B",
            },
        }
        render_stat_cards(stats)
        # At least Home and Trip subheaders
        calls = [str(c) for c in mock_subheader.call_args_list]
        self.assertTrue(any("Home" in c for c in calls))
        self.assertTrue(any("Trip" in c for c in calls))
        self.assertTrue(mock_metric.called)

    @patch("streamlit.info")
    def test_empty_stats_shows_info(self, mock_info: MagicMock) -> None:
        render_stat_cards({})
        mock_info.assert_called_once()


class TestRenderTimelineChart(unittest.TestCase):
    """Tests for render_timeline_chart."""

    @patch("streamlit.plotly_chart")
    def test_renders_chart_with_periods(self, mock_plotly: MagicMock) -> None:
        df = _make_labeled_df()
        trip_periods = [
            (pd.Timestamp("2021-01-09"), pd.Timestamp("2021-01-10")),
        ]
        render_timeline_chart(df, trip_periods)
        mock_plotly.assert_called_once_with(ANY, width="stretch")

    @patch("streamlit.plotly_chart")
    def test_empty_df_does_not_render(self, mock_plotly: MagicMock) -> None:
        render_timeline_chart(pd.DataFrame(), [])
        mock_plotly.assert_not_called()


class TestRenderGenreComparison(unittest.TestCase):
    """Tests for render_genre_comparison."""

    @patch("streamlit.plotly_chart")
    def test_renders_with_both_contexts(self, mock_plotly: MagicMock) -> None:
        df = _make_labeled_df()
        render_genre_comparison(df)
        mock_plotly.assert_called_once()

    @patch("streamlit.plotly_chart")
    def test_no_render_when_one_context_empty(self, mock_plotly: MagicMock) -> None:
        df = _make_labeled_df()
        df_home_only = df[df["context"] == "home"].copy()
        render_genre_comparison(df_home_only)
        mock_plotly.assert_not_called()


class TestRenderDiscoveryChart(unittest.TestCase):
    """Tests for render_discovery_chart."""

    @patch("streamlit.plotly_chart")
    def test_renders_with_valid_data(self, mock_plotly: MagicMock) -> None:
        df = _make_labeled_df()
        render_discovery_chart(df)
        mock_plotly.assert_called_once()

    @patch("streamlit.plotly_chart")
    def test_no_render_on_empty_df(self, mock_plotly: MagicMock) -> None:
        render_discovery_chart(pd.DataFrame())
        mock_plotly.assert_not_called()


class TestRenderVacationMode(unittest.TestCase):
    """Integration-style tests for render_vacation_mode."""

    def _base_df(self) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "artist": ["A", "B", "C", "D"],
                "album": ["X", "X", "Y", "Y"],
                "track": ["t1", "t2", "t3", "t4"],
                "timestamp": [1610000000, 1610086400, 1610172800, 1610259200],
                "date_text": pd.to_datetime(
                    ["2021-01-07", "2021-01-08", "2021-01-09", "2021-01-10"]
                ),
            }
        )
        return df

    @patch("streamlit.info")
    def test_empty_state_shown_when_no_df(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": None}):
            render_vacation_mode()
        mock_info.assert_called_once()

    @patch("streamlit.warning")
    @patch("streamlit.caption")
    @patch("streamlit.subheader")
    @patch("streamlit.header")
    @patch("streamlit.info")
    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.container")
    def test_renders_with_no_trips(
        self,
        mock_container: MagicMock,
        mock_metric: MagicMock,
        mock_cols: MagicMock,
        mock_info: MagicMock,
        mock_header: MagicMock,
        mock_subheader: MagicMock,
        mock_caption: MagicMock,
        mock_warning: MagicMock,
    ) -> None:
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_container.return_value = ctx
        mock_cols.return_value = [ctx, ctx]

        session = {
            "df": self._base_df(),
            "assumptions": {"trips": [], "defaults": {"city": "Reykjavik, IS"}},
            "swarm_df": None,
        }
        with patch("streamlit.session_state", session):
            render_vacation_mode()

        mock_header.assert_called_with("Vacation Mode")
        mock_warning.assert_called_once()

    @patch("streamlit.dataframe")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    @patch("streamlit.subheader")
    @patch("streamlit.header")
    @patch("streamlit.columns")
    @patch("streamlit.metric")
    @patch("streamlit.container")
    @patch("streamlit.plotly_chart")
    def test_renders_with_trip_periods(
        self,
        mock_plotly: MagicMock,
        mock_container: MagicMock,
        mock_metric: MagicMock,
        mock_cols: MagicMock,
        mock_header: MagicMock,
        mock_subheader: MagicMock,
        mock_divider: MagicMock,
        mock_caption: MagicMock,
        mock_df_widget: MagicMock,
    ) -> None:
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=ctx)
        ctx.__exit__ = MagicMock(return_value=False)
        mock_container.return_value = ctx
        mock_cols.return_value = [ctx, ctx]

        assumptions = {
            "trips": [{"start": "2021-01-09", "end": "2021-01-10", "city": "Paris"}],
            "defaults": {"city": "Reykjavik, IS"},
        }
        session = {
            "df": self._base_df(),
            "assumptions": assumptions,
            "swarm_df": None,
        }
        with patch("streamlit.session_state", session):
            render_vacation_mode()

        mock_header.assert_called_with("Vacation Mode")
        # Timeline + comparison + discovery charts should be rendered
        self.assertTrue(mock_plotly.called)
        mock_df_widget.assert_called_once()


if __name__ == "__main__":
    unittest.main()
