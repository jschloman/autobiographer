"""Unit tests for the Autobiographer dashboard pages."""

from __future__ import annotations

import os
import shutil
import unittest
from unittest.mock import ANY, MagicMock, patch

import pandas as pd

from pages.insights import render_insights_and_narrative
from pages.music import render_timeline_analysis
from pages.overview import render_top_charts
from pages.places import render_spatial_analysis
from visualize import main


class TestVisualize(unittest.TestCase):
    """Tests for page render functions and the dashboard entrypoint."""

    def setUp(self) -> None:
        self.test_dir = "data_test"
        os.makedirs(self.test_dir, exist_ok=True)
        self.test_csv = os.path.join(self.test_dir, "test_user_tracks.csv")

        self.df = pd.DataFrame(
            {
                "artist": ["Artist 1", "Artist 2", "Artist 1"],
                "album": ["Album 1", "Album 2", "Album 1"],
                "track": ["Track 1", "Track 2", "Track 3"],
                "timestamp": [1610000000, 1610000100, 1610000200],
                "date_text": ["2021-01-01 10:00", "2021-01-01 10:01", "2021-01-01 11:02"],
                "lat": [41.0, 42.0, 41.0],
                "lng": [-87.0, -88.0, -87.0],
                "city": ["Reykjavik", "Perth", "Reykjavik"],
                "state": ["IS", "WA", "IS"],
                "country": ["Iceland", "Australia", "Iceland"],
            }
        )
        self.df["date_text"] = pd.to_datetime(self.df["date_text"])
        self.df.to_csv(self.test_csv, index=False)

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch("streamlit.header")
    @patch("streamlit.selectbox")
    @patch("streamlit.date_input")
    @patch("streamlit.columns")
    @patch("streamlit.pydeck_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.slider")
    def test_render_spatial_analysis(
        self,
        mock_slider: MagicMock,
        mock_df: MagicMock,
        mock_deck: MagicMock,
        mock_cols: MagicMock,
        mock_date: MagicMock,
        mock_select: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_select.return_value = "All"
        mock_date.return_value = [
            self.df["date_text"].min().date(),
            self.df["date_text"].max().date(),
        ]
        mock_cols.side_effect = [
            [MagicMock(), MagicMock()],
            [MagicMock(), MagicMock(), MagicMock()],
            [MagicMock(), MagicMock()],
        ]
        mock_slider.return_value = 3.0

        mock_state = MagicMock()
        mock_state.__contains__.return_value = False

        with patch("streamlit.session_state", mock_state):
            render_spatial_analysis(self.df)

        mock_header.assert_called_with("Spatial Music Explorer")
        mock_deck.assert_called_once()
        mock_df.assert_called_once()

    @patch("streamlit.header")
    @patch("streamlit.radio")
    @patch("streamlit.slider")
    @patch("streamlit.columns")
    @patch("streamlit.plotly_chart")
    def test_render_top_charts(
        self,
        mock_plotly: MagicMock,
        mock_columns: MagicMock,
        mock_slider: MagicMock,
        mock_radio: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_radio.return_value = "artist"
        mock_slider.return_value = 10
        mock_columns.return_value = [MagicMock(), MagicMock()]

        render_top_charts(self.df)

        mock_header.assert_called_with("Top Charts")
        self.assertEqual(mock_plotly.call_count, 2)
        mock_plotly.assert_any_call(ANY, width="stretch")

    @patch("streamlit.header")
    @patch("streamlit.selectbox")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.subheader")
    def test_render_timeline_analysis(
        self,
        mock_subheader: MagicMock,
        mock_plotly: MagicMock,
        mock_selectbox: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_selectbox.return_value = "Daily"

        render_timeline_analysis(self.df)

        mock_header.assert_called_with("Activity Over Time")
        self.assertEqual(mock_plotly.call_count, 2)
        mock_plotly.assert_any_call(ANY, width="stretch")

    @patch("streamlit.header")
    @patch("streamlit.subheader")
    @patch("streamlit.selectbox")
    @patch("streamlit.columns")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.dataframe")
    @patch("streamlit.tabs")
    @patch("streamlit.metric")
    def test_render_insights_and_narrative(
        self,
        mock_metric: MagicMock,
        mock_tabs: MagicMock,
        mock_df: MagicMock,
        mock_plotly: MagicMock,
        mock_cols: MagicMock,
        mock_select: MagicMock,
        mock_subheader: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        mock_select.return_value = "All"
        mock_cols.side_effect = [
            [MagicMock()] * 4,
            [MagicMock()] * 2,
            [MagicMock()] * 2,
            [MagicMock()] * 2,
        ]
        mock_tabs.return_value = [MagicMock(), MagicMock(), MagicMock()]

        render_insights_and_narrative(self.df)

        mock_header.assert_called_with("Insights & Narrative")
        self.assertTrue(mock_select.called)

    @patch("streamlit.set_page_config")
    @patch("streamlit.navigation")
    def test_main_configures_page_and_runs_navigation(
        self,
        mock_nav: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        mock_pg = MagicMock()
        mock_nav.return_value = mock_pg

        with patch("visualize.render_sidebar"):
            main()

        mock_config.assert_called_once_with(page_title="Autobiographer", layout="wide")
        mock_nav.assert_called_once()
        mock_pg.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
