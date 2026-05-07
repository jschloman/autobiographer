"""Tests for pages.dining_soundtrack — music around restaurant check-ins."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from analysis_utils import load_swarm_data
from pages.dining_soundtrack import (
    FOOD_DRINK_CATEGORIES,
    _classify_venue_category,
    _get_listens_around_checkin,
    get_dining_soundtrack_data,
    render_dining_soundtrack,
)


class TestClassifyVenueCategory(unittest.TestCase):
    """Tests for _classify_venue_category()."""

    def test_restaurant_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Italian Restaurant"), "Restaurants")

    def test_bar_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Dive Bar"), "Bars & Nightlife")

    def test_nightclub_maps_to_bars(self) -> None:
        self.assertEqual(_classify_venue_category("Nightclub"), "Bars & Nightlife")

    def test_cafe_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Coffee Shop"), "Cafes")

    def test_fast_food_maps_correctly(self) -> None:
        self.assertEqual(_classify_venue_category("Fast Food Restaurant"), "Fast Food")

    def test_burger_joint_maps_to_fast_food(self) -> None:
        self.assertEqual(_classify_venue_category("Burger Joint"), "Fast Food")

    def test_bakery_maps_to_cafes(self) -> None:
        self.assertEqual(_classify_venue_category("Bakery"), "Cafes")

    def test_non_food_returns_none(self) -> None:
        self.assertIsNone(_classify_venue_category("Museum"))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_classify_venue_category(""))

    def test_case_insensitive(self) -> None:
        self.assertEqual(_classify_venue_category("ITALIAN RESTAURANT"), "Restaurants")

    def test_food_drink_categories_constant_is_nonempty(self) -> None:
        self.assertIn("Restaurants", FOOD_DRINK_CATEGORIES)
        self.assertIn("Bars & Nightlife", FOOD_DRINK_CATEGORIES)
        self.assertIn("Cafes", FOOD_DRINK_CATEGORIES)
        self.assertIn("Fast Food", FOOD_DRINK_CATEGORIES)


class TestGetListensAroundCheckin(unittest.TestCase):
    """Tests for _get_listens_around_checkin() — ±2 hour window logic."""

    def _make_lastfm_df(self) -> pd.DataFrame:
        """Return a small Last.fm DataFrame spanning several timestamps."""
        base = 1_700_000_000  # arbitrary Unix epoch
        return pd.DataFrame(
            {
                "artist": ["Artist A", "Artist B", "Artist C", "Artist D"],
                "track": ["Track 1", "Track 2", "Track 3", "Track 4"],
                "timestamp": [
                    base - 7300,  # >2 hours before checkin — outside window
                    base - 3600,  # 1 hour before — inside window
                    base + 1800,  # 30 min after — inside window
                    base + 7300,  # >2 hours after — outside window
                ],
                "date_text": pd.to_datetime(
                    [
                        base - 7300,
                        base - 3600,
                        base + 1800,
                        base + 7300,
                    ],
                    unit="s",
                ),
            }
        )

    def test_returns_only_listens_within_window(self) -> None:
        lastfm_df = self._make_lastfm_df()
        base = 1_700_000_000
        result = _get_listens_around_checkin(lastfm_df, base, window_hours=2)
        self.assertEqual(len(result), 2)
        self.assertIn("Artist B", result["artist"].values)
        self.assertIn("Artist C", result["artist"].values)

    def test_returns_empty_when_no_listens_in_window(self) -> None:
        lastfm_df = self._make_lastfm_df()
        result = _get_listens_around_checkin(lastfm_df, 0, window_hours=2)
        self.assertTrue(result.empty)

    def test_returns_empty_for_empty_lastfm(self) -> None:
        result = _get_listens_around_checkin(pd.DataFrame(), 1_700_000_000, window_hours=2)
        self.assertTrue(result.empty)


class TestGetDiningSoundtrackData(unittest.TestCase):
    """Tests for get_dining_soundtrack_data() — the main aggregation function."""

    def _make_swarm_df(self) -> pd.DataFrame:
        base = 1_700_000_000
        return pd.DataFrame(
            {
                "timestamp": [base, base + 86400, base + 172800],
                "venue": ["Pizzeria Roma", "The Dive", "McDonalds"],
                "venue_category": ["Italian Restaurant", "Dive Bar", "Fast Food Restaurant"],
                "city": ["London", "London", "London"],
                "country": ["UK", "UK", "UK"],
            }
        )

    def _make_lastfm_df(self) -> pd.DataFrame:
        base = 1_700_000_000
        return pd.DataFrame(
            {
                "artist": ["Beatles", "Beatles", "Rolling Stones", "Oasis"],
                "track": ["Hey Jude", "Let It Be", "Paint It Black", "Wonderwall"],
                "timestamp": [
                    base - 1800,  # 30 min before restaurant checkin
                    base + 1800,  # 30 min after restaurant checkin
                    base + 86400 - 1800,  # 30 min before bar checkin
                    base + 172800 + 1800,  # 30 min after fast food checkin
                ],
                "date_text": pd.to_datetime(
                    [
                        base - 1800,
                        base + 1800,
                        base + 86400 - 1800,
                        base + 172800 + 1800,
                    ],
                    unit="s",
                ),
            }
        )

    def test_returns_dict_with_expected_categories(self) -> None:
        swarm_df = self._make_swarm_df()
        lastfm_df = self._make_lastfm_df()
        result = get_dining_soundtrack_data(swarm_df, lastfm_df)
        self.assertIsInstance(result, dict)
        # At least the categories present in our test data should appear
        self.assertIn("Restaurants", result)
        self.assertIn("Bars & Nightlife", result)

    def test_restaurants_category_has_correct_structure(self) -> None:
        swarm_df = self._make_swarm_df()
        lastfm_df = self._make_lastfm_df()
        result = get_dining_soundtrack_data(swarm_df, lastfm_df)
        cat_data = result.get("Restaurants")
        self.assertIsNotNone(cat_data)
        assert cat_data is not None
        self.assertIn("top_artists", cat_data)
        self.assertIn("checkin_count", cat_data)
        self.assertIn("listen_count", cat_data)
        self.assertIn("peak_hour", cat_data)

    def test_top_artists_respects_limit(self) -> None:
        swarm_df = self._make_swarm_df()
        lastfm_df = self._make_lastfm_df()
        result = get_dining_soundtrack_data(swarm_df, lastfm_df, top_n=5)
        for cat_data in result.values():
            self.assertLessEqual(len(cat_data["top_artists"]), 5)

    def test_empty_swarm_returns_empty_dict(self) -> None:
        result = get_dining_soundtrack_data(pd.DataFrame(), self._make_lastfm_df())
        self.assertEqual(result, {})

    def test_empty_lastfm_returns_empty_dict(self) -> None:
        result = get_dining_soundtrack_data(self._make_swarm_df(), pd.DataFrame())
        self.assertEqual(result, {})

    def test_skips_non_food_venues(self) -> None:
        swarm_df = pd.DataFrame(
            {
                "timestamp": [1_700_000_000],
                "venue": ["Museum of Art"],
                "venue_category": ["Museum"],
                "city": ["London"],
                "country": ["UK"],
            }
        )
        lastfm_df = self._make_lastfm_df()
        result = get_dining_soundtrack_data(swarm_df, lastfm_df)
        self.assertEqual(result, {})

    def test_missing_required_columns_returns_empty(self) -> None:
        """Returns empty dict when swarm_df lacks required columns."""
        swarm_df = pd.DataFrame({"venue": ["Pizzeria Roma"]})  # no timestamp or venue_category
        lastfm_df = self._make_lastfm_df()
        result = get_dining_soundtrack_data(swarm_df, lastfm_df)
        self.assertEqual(result, {})

    def test_checkins_with_no_nearby_listens_excluded(self) -> None:
        """Category with check-ins but zero nearby listens is excluded from results."""
        base = 1_700_000_000
        swarm_df = pd.DataFrame(
            {
                "timestamp": [base],
                "venue": ["Pizzeria Roma"],
                "venue_category": ["Italian Restaurant"],
                "city": ["London"],
                "country": ["UK"],
            }
        )
        # Put all listens far outside the ±2 hour window
        lastfm_df = pd.DataFrame(
            {
                "artist": ["Beatles"],
                "track": ["Hey Jude"],
                "timestamp": [base + 86400],  # 24 hours away
                "date_text": pd.to_datetime([base + 86400], unit="s"),
            }
        )
        result = get_dining_soundtrack_data(swarm_df, lastfm_df)
        # Restaurants had a checkin but no nearby listens — should be absent
        self.assertNotIn("Restaurants", result)


class TestLoadSwarmDataVenueCategory(unittest.TestCase):
    """Test that load_swarm_data() correctly parses venue_category."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_venue_category_parsed_when_present(self) -> None:
        data = {
            "items": [
                {
                    "createdAt": 1_700_000_000,
                    "timeZoneOffset": 0,
                    "venue": {
                        "name": "Pizzeria Roma",
                        "categories": [{"name": "Italian Restaurant"}],
                        "location": {"city": "London", "country": "UK"},
                    },
                }
            ]
        }
        with open(os.path.join(self.test_dir, "checkins1.json"), "w") as f:
            json.dump(data, f)

        df = load_swarm_data(self.test_dir)
        self.assertIn("venue_category", df.columns)
        self.assertEqual(df.iloc[0]["venue_category"], "Italian Restaurant")

    def test_venue_category_empty_when_no_categories(self) -> None:
        data = {
            "items": [
                {
                    "createdAt": 1_700_000_001,
                    "timeZoneOffset": 0,
                    "venue": {
                        "name": "Unnamed Place",
                        "location": {"city": "London", "country": "UK"},
                    },
                }
            ]
        }
        with open(os.path.join(self.test_dir, "checkins_nocat.json"), "w") as f:
            json.dump(data, f)

        df = load_swarm_data(self.test_dir)
        self.assertIn("venue_category", df.columns)
        self.assertEqual(df.iloc[0]["venue_category"], "")

    def test_empty_dir_returns_venue_category_column(self) -> None:
        empty_dir = tempfile.mkdtemp()
        try:
            df = load_swarm_data(empty_dir)
            self.assertIn("venue_category", df.columns)
        finally:
            shutil.rmtree(empty_dir)


class TestRenderDiningSoundtrack(unittest.TestCase):
    """Integration-style tests for the render_dining_soundtrack() page function."""

    def _make_swarm_df(self) -> pd.DataFrame:
        base = 1_700_000_000
        return pd.DataFrame(
            {
                "timestamp": [base],
                "venue": ["Pizzeria Roma"],
                "venue_category": ["Italian Restaurant"],
                "city": ["London"],
                "country": ["UK"],
            }
        )

    def _make_lastfm_df(self) -> pd.DataFrame:
        base = 1_700_000_000
        return pd.DataFrame(
            {
                "artist": ["Beatles", "Beatles"],
                "track": ["Hey Jude", "Let It Be"],
                "timestamp": [base - 1800, base + 1800],
                "date_text": pd.to_datetime([base - 1800, base + 1800], unit="s"),
            }
        )

    @patch("streamlit.info")
    def test_shows_info_when_no_swarm(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": self._make_lastfm_df(), "swarm_df": None}):
            render_dining_soundtrack()
        mock_info.assert_called_once()

    @patch("streamlit.info")
    def test_shows_info_when_no_lastfm(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": None, "swarm_df": self._make_swarm_df()}):
            render_dining_soundtrack()
        mock_info.assert_called_once()

    @patch("streamlit.info")
    def test_shows_info_when_no_matches(self, mock_info: MagicMock) -> None:
        """Page shows an info message when no food/drink venues match."""
        swarm_df = pd.DataFrame(
            {
                "timestamp": [1_700_000_000],
                "venue": ["Art Museum"],
                "venue_category": ["Museum"],
                "city": ["London"],
                "country": ["UK"],
            }
        )
        lastfm_df = self._make_lastfm_df()
        with patch("streamlit.session_state", {"df": lastfm_df, "swarm_df": swarm_df}):
            render_dining_soundtrack()
        mock_info.assert_called_once()

    def _make_swarm_df(self) -> pd.DataFrame:
        """Multi-category swarm data for render tests."""
        base = 1_700_000_000
        return pd.DataFrame(
            {
                "timestamp": [base, base + 86400],
                "venue": ["Pizzeria Roma", "The Dive"],
                "venue_category": ["Italian Restaurant", "Dive Bar"],
                "city": ["London", "London"],
                "country": ["UK", "UK"],
            }
        )

    def _make_lastfm_df(self) -> pd.DataFrame:
        """Last.fm data with listens near both check-ins above."""
        base = 1_700_000_000
        return pd.DataFrame(
            {
                "artist": ["Beatles", "Rolling Stones"],
                "track": ["Hey Jude", "Paint It Black"],
                "timestamp": [base - 1800, base + 86400 - 1800],
                "date_text": pd.to_datetime([base - 1800, base + 86400 - 1800], unit="s"),
            }
        )

    @patch("streamlit.header")
    @patch("streamlit.subheader")
    @patch("streamlit.columns")
    @patch("streamlit.plotly_chart")
    @patch("streamlit.metric")
    @patch("streamlit.caption")
    @patch("streamlit.markdown")
    @patch("streamlit.divider")
    def test_renders_with_valid_data(
        self,
        mock_divider: MagicMock,
        mock_md: MagicMock,
        mock_caption: MagicMock,
        mock_metric: MagicMock,
        mock_plotly: MagicMock,
        mock_cols: MagicMock,
        mock_subheader: MagicMock,
        mock_header: MagicMock,
    ) -> None:
        swarm_df = self._make_swarm_df()
        lastfm_df = self._make_lastfm_df()
        # st.columns(len(FOOD_DRINK_CATEGORIES)) returns 4 cols;
        # subsequent st.columns([2, 1]) calls return 2-element lists.
        col_pair = [MagicMock(), MagicMock()]
        col_quad = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        # First call = 4-column summary row; next calls = [2,1] per category + comparison chart
        mock_cols.side_effect = [col_quad, col_pair, col_pair]

        with patch("streamlit.session_state", {"df": lastfm_df, "swarm_df": swarm_df}):
            render_dining_soundtrack()

        mock_header.assert_called_with("Dining Soundtrack")
        # Should render at least one plotly chart (per-category bar + comparison)
        self.assertTrue(mock_plotly.called)


if __name__ == "__main__":
    unittest.main()
