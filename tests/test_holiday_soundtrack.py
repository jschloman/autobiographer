"""Unit tests for the Holiday Soundtrack page (issue #65)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from pages.holiday_soundtrack import (
    _build_holiday_windows,
    _filter_holiday,
    _jaccard_similarity,
    _signature_song,
    _top_artists_for_year,
    _year_over_year_plays,
    render_holiday_soundtrack,
)


def _make_df() -> pd.DataFrame:
    """Return a minimal listening-history DataFrame spanning two Christmases."""
    rows = [
        # Christmas 2021
        {
            "artist": "Mariah Carey",
            "track": "All I Want for Christmas Is You",
            "date_text": "2021-12-25 10:00:00",
        },
        {
            "artist": "Mariah Carey",
            "track": "All I Want for Christmas Is You",
            "date_text": "2021-12-25 11:00:00",
        },
        {"artist": "Wham!", "track": "Last Christmas", "date_text": "2021-12-25 12:00:00"},
        # Christmas 2022
        {
            "artist": "Mariah Carey",
            "track": "All I Want for Christmas Is You",
            "date_text": "2022-12-25 09:00:00",
        },
        {
            "artist": "Brenda Lee",
            "track": "Rockin Around the Christmas Tree",
            "date_text": "2022-12-25 10:00:00",
        },
        # Halloween 2021
        {"artist": "Michael Jackson", "track": "Thriller", "date_text": "2021-10-31 20:00:00"},
        # Off-holiday track
        {"artist": "Other Artist", "track": "Summer Song", "date_text": "2021-06-15 14:00:00"},
    ]
    df = pd.DataFrame(rows)
    df["date_text"] = pd.to_datetime(df["date_text"])
    return df


_CHRISTMAS_DEF = {"name": "Christmas", "month": 12, "day_range": [24, 26]}
_HALLOWEEN_DEF = {"name": "Halloween", "month": 10, "day_range": [31, 31]}


class TestBuildHolidayWindows(unittest.TestCase):
    """Tests for _build_holiday_windows."""

    def test_returns_rows_for_every_year_in_range(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        years = [w["year"] for w in windows]
        self.assertIn(2021, years)
        self.assertIn(2022, years)

    def test_window_bounds_match_day_range(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        for w in windows:
            self.assertEqual(w["start"].month, 12)
            self.assertEqual(w["start"].day, 24)
            self.assertEqual(w["end"].month, 12)
            self.assertEqual(w["end"].day, 26)

    def test_empty_df_returns_empty_list(self) -> None:
        windows = _build_holiday_windows(pd.DataFrame(), _CHRISTMAS_DEF)
        self.assertEqual(windows, [])


class TestFilterHoliday(unittest.TestCase):
    """Tests for _filter_holiday."""

    def test_keeps_rows_inside_window(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        # 2021 Christmas window
        w = next(w for w in windows if w["year"] == 2021)
        filtered = _filter_holiday(df, w)
        self.assertEqual(len(filtered), 3)  # 2 Mariah + 1 Wham! on 2021-12-25

    def test_excludes_off_holiday_rows(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        all_christmas = pd.concat([_filter_holiday(df, w) for w in windows], ignore_index=True)
        self.assertNotIn("Other Artist", all_christmas["artist"].values)
        self.assertNotIn("Michael Jackson", all_christmas["artist"].values)


class TestYearOverYearPlays(unittest.TestCase):
    """Tests for _year_over_year_plays."""

    def test_returns_dataframe_with_year_and_plays_columns(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        result = _year_over_year_plays(df, windows)
        self.assertIn("year", result.columns)
        self.assertIn("plays", result.columns)

    def test_play_counts_are_correct(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        result = _year_over_year_plays(df, windows)
        plays_2021 = result.loc[result["year"] == 2021, "plays"].iloc[0]
        plays_2022 = result.loc[result["year"] == 2022, "plays"].iloc[0]
        self.assertEqual(plays_2021, 3)
        self.assertEqual(plays_2022, 2)


class TestTopArtistsForYear(unittest.TestCase):
    """Tests for _top_artists_for_year."""

    def test_returns_top_n_artists(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        w_2021 = next(w for w in windows if w["year"] == 2021)
        top = _top_artists_for_year(df, w_2021, n=10)
        self.assertIn("Mariah Carey", top)

    def test_respects_n_limit(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        w_2021 = next(w for w in windows if w["year"] == 2021)
        top = _top_artists_for_year(df, w_2021, n=1)
        self.assertEqual(len(top), 1)

    def test_empty_window_returns_empty_set(self) -> None:
        # A window in a year with no data
        window = {
            "year": 1900,
            "start": pd.Timestamp("1900-12-24"),
            "end": pd.Timestamp("1900-12-26"),
        }
        top = _top_artists_for_year(_make_df(), window, n=10)
        self.assertEqual(len(top), 0)


class TestJaccardSimilarity(unittest.TestCase):
    """Tests for _jaccard_similarity."""

    def test_identical_sets_return_one(self) -> None:
        self.assertAlmostEqual(_jaccard_similarity({"a", "b"}, {"a", "b"}), 1.0)

    def test_disjoint_sets_return_zero(self) -> None:
        self.assertAlmostEqual(_jaccard_similarity({"a"}, {"b"}), 0.0)

    def test_partial_overlap(self) -> None:
        # {"a","b"} ∩ {"b","c"} = {"b"}, union = {"a","b","c"} → 1/3
        result = _jaccard_similarity({"a", "b"}, {"b", "c"})
        self.assertAlmostEqual(result, 1 / 3)

    def test_empty_sets_return_zero(self) -> None:
        self.assertAlmostEqual(_jaccard_similarity(set(), set()), 0.0)


class TestSignatureSong(unittest.TestCase):
    """Tests for _signature_song."""

    def test_returns_most_played_track(self) -> None:
        df = _make_df()
        windows = _build_holiday_windows(df, _CHRISTMAS_DEF)
        song = _signature_song(df, windows)
        # Mariah Carey's track appears 3 times across both Christmases
        self.assertIsNotNone(song)
        assert song is not None  # narrow type for mypy
        self.assertIn("Mariah Carey", song)

    def test_no_data_returns_none(self) -> None:
        # No Christmas rows → empty windows or zero-count holiday
        song = _signature_song(pd.DataFrame(), [])
        self.assertIsNone(song)


class TestRenderHolidaySoundtrack(unittest.TestCase):
    """Integration smoke-tests for render_holiday_soundtrack."""

    def _session_with_data(self) -> dict:
        return {"df": _make_df(), "assumptions": {"holidays": [_CHRISTMAS_DEF, _HALLOWEEN_DEF]}}

    @patch("streamlit.info")
    def test_empty_state_shows_info(self, mock_info: MagicMock) -> None:
        with patch("streamlit.session_state", {"df": None, "assumptions": {}}):
            render_holiday_soundtrack()
        mock_info.assert_called_once()

    @patch("streamlit.info")
    def test_no_holidays_shows_info(self, mock_info: MagicMock) -> None:
        df = _make_df()
        session = {"df": df, "assumptions": {"holidays": []}}
        with patch("streamlit.session_state", session):
            render_holiday_soundtrack()
        mock_info.assert_called_once()

    @patch("streamlit.plotly_chart")
    @patch("streamlit.subheader")
    @patch("streamlit.header")
    @patch("streamlit.selectbox")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    @patch("streamlit.caption")
    @patch("streamlit.markdown")
    @patch("streamlit.divider")
    def test_render_with_data(
        self,
        mock_divider: MagicMock,
        mock_md: MagicMock,
        mock_caption: MagicMock,
        mock_cols: MagicMock,
        mock_metric: MagicMock,
        mock_select: MagicMock,
        mock_header: MagicMock,
        mock_subheader: MagicMock,
        mock_plotly: MagicMock,
    ) -> None:
        """render_holiday_soundtrack renders at least one chart with valid data."""
        mock_select.return_value = "Christmas"
        # Provide enough column mock lists for every st.columns() call in the page.
        mock_cols.side_effect = [
            [MagicMock(), MagicMock(), MagicMock()],  # metric row
        ] * 20  # generous upper bound

        session = self._session_with_data()
        with patch("streamlit.session_state", session):
            render_holiday_soundtrack()

        mock_header.assert_called_once_with("Holiday Soundtrack")
        # At least the year-over-year line chart must be drawn.
        self.assertGreater(mock_plotly.call_count, 0)


if __name__ == "__main__":
    unittest.main()
