"""Tests for the Life in Chapters page and the build_life_chapters utility."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from analysis_utils import build_life_chapters, detect_trips_from_swarm
from pages.life_in_chapters import (
    _duration_label,
    _format_date_range,
    _load_detected_trips_cache,
    _save_detected_trips_cache,
    render_life_in_chapters,
)


def _make_df(
    artists: list[str] | None = None,
    dates: list[str] | None = None,
) -> pd.DataFrame:
    """Return a minimal listening-history DataFrame for testing."""
    if artists is None:
        artists = ["Alpha", "Beta", "Alpha", "Gamma", "Delta"]
    if dates is None:
        dates = [
            "2020-03-10",
            "2020-03-15",
            "2020-06-01",
            "2021-01-05",
            "2021-01-20",
        ]
    df = pd.DataFrame(
        {
            "artist": artists,
            "album": [f"Album {a}" for a in artists],
            "track": [f"Track {i}" for i in range(len(artists))],
            "timestamp": list(range(len(artists))),
            "date_text": pd.to_datetime(dates),
        }
    )
    return df


def _make_assumptions(include_trips: bool = True) -> dict:
    """Return a minimal assumptions dict for testing."""
    assumptions: dict = {
        "defaults": {},
        "holidays": [],
        "residency": [
            {
                "start": "2020-01-01",
                "end": "2020-12-31",
                "city": "Reykjavik",
                "country": "Iceland",
                "lat": 64.13,
                "lng": -21.82,
            }
        ],
        "trips": [],
    }
    if include_trips:
        assumptions["trips"] = [
            {
                "start": "2021-01-01",
                "end": "2021-03-31",
                "city": "Berlin",
                "country": "Germany",
            }
        ]
    return assumptions


def _make_swarm_df(
    lats: list[float],
    lngs: list[float],
    timestamps: list[int],
    cities: list[str] | None = None,
    countries: list[str] | None = None,
) -> pd.DataFrame:
    """Return a minimal Swarm check-in DataFrame for testing."""
    n = len(lats)
    return pd.DataFrame(
        {
            "lat": lats,
            "lng": lngs,
            "timestamp": timestamps,
            "city": cities or ["TestCity"] * n,
            "country": countries or ["TC"] * n,
        }
    )


class TestFormatDateRange(unittest.TestCase):
    """Unit tests for the _format_date_range helper."""

    def test_same_year_uses_short_format(self) -> None:
        start = pd.Timestamp("2024-01-15")
        end = pd.Timestamp("2024-03-20")
        result = _format_date_range(start, end)
        self.assertIn("2024", result)
        self.assertIn("Jan", result)
        self.assertIn("Mar", result)

    def test_different_years_uses_month_year(self) -> None:
        start = pd.Timestamp("2023-11-01")
        end = pd.Timestamp("2024-02-28")
        result = _format_date_range(start, end)
        self.assertIn("2023", result)
        self.assertIn("2024", result)


class TestDurationLabel(unittest.TestCase):
    """Unit tests for the _duration_label helper."""

    def test_less_than_one_day(self) -> None:
        start = pd.Timestamp("2024-01-01 08:00")
        end = pd.Timestamp("2024-01-01 10:00")
        self.assertEqual(_duration_label(start, end), "< 1 day")

    def test_single_day(self) -> None:
        start = pd.Timestamp("2024-01-01")
        end = pd.Timestamp("2024-01-01")
        result = _duration_label(start, end)
        self.assertIn("day", result)

    def test_multiple_days(self) -> None:
        start = pd.Timestamp("2024-01-01")
        end = pd.Timestamp("2024-01-20")
        result = _duration_label(start, end)
        self.assertIn("day", result)
        self.assertIn("19", result)

    def test_months(self) -> None:
        start = pd.Timestamp("2024-01-01")
        end = pd.Timestamp("2024-04-30")
        result = _duration_label(start, end)
        self.assertIn("month", result)

    def test_years(self) -> None:
        # 2 years 6 months → uses "yr mo" abbreviated form
        start = pd.Timestamp("2020-01-01")
        end = pd.Timestamp("2022-07-15")
        result = _duration_label(start, end)
        self.assertIn("yr", result)

    def test_exactly_one_year(self) -> None:
        start = pd.Timestamp("2020-01-01")
        end = pd.Timestamp("2020-12-31")
        result = _duration_label(start, end)
        self.assertIn("year", result)


class TestBuildLifeChapters(unittest.TestCase):
    """Unit tests for build_life_chapters in analysis_utils."""

    def test_returns_empty_list_for_empty_df(self) -> None:
        result = build_life_chapters(pd.DataFrame(), _make_assumptions())
        self.assertEqual(result, [])

    def test_returns_empty_list_for_no_assumptions(self) -> None:
        df = _make_df()
        assumptions = {"residency": [], "trips": [], "holidays": [], "defaults": {}}
        result = build_life_chapters(df, assumptions)
        self.assertEqual(result, [])

    def test_returns_one_chapter_per_period(self) -> None:
        df = _make_df()
        assumptions = _make_assumptions(include_trips=True)
        chapters = build_life_chapters(df, assumptions)
        # 1 residency + 1 trip
        self.assertEqual(len(chapters), 2)

    def test_chapters_sorted_chronologically(self) -> None:
        df = _make_df()
        assumptions = _make_assumptions(include_trips=True)
        chapters = build_life_chapters(df, assumptions)
        starts = [c["start"] for c in chapters]
        self.assertEqual(starts, sorted(starts))

    def test_chapter_has_required_keys(self) -> None:
        df = _make_df()
        assumptions = _make_assumptions(include_trips=False)
        chapters = build_life_chapters(df, assumptions)
        required_keys = {
            "label",
            "location",
            "start",
            "end",
            "kind",
            "lat",
            "lng",
            "total_plays",
            "top_artists",
            "top_album",
            "discovery_count",
            "exclusive_artists",
        }
        for chapter in chapters:
            self.assertTrue(required_keys.issubset(chapter.keys()), chapter.keys())

    def test_total_plays_counts_filtered_rows(self) -> None:
        df = _make_df()
        assumptions = _make_assumptions(include_trips=False)
        # Only 2020 data: dates 2020-03-10, 2020-03-15, 2020-06-01
        chapters = build_life_chapters(df, assumptions)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["total_plays"], 3)

    def test_top_artists_respects_limit(self) -> None:
        artists = [f"Artist{i}" for i in range(10)]
        dates = [f"2020-0{i + 1}-01" for i in range(9)] + ["2020-10-01"]
        df = _make_df(artists=artists, dates=dates)
        assumptions = _make_assumptions(include_trips=False)
        chapters = build_life_chapters(df, assumptions)
        self.assertLessEqual(len(chapters[0]["top_artists"]), 5)

    def test_discovery_count_for_first_heard_in_chapter(self) -> None:
        # All plays are in the 2020 residency — every artist is first-heard there
        df = _make_df()
        assumptions = _make_assumptions(include_trips=False)
        chapters = build_life_chapters(df, assumptions)
        # Artists heard in 2020 chapter: Alpha, Beta, Gamma (dates 2020-03-10,
        # 2020-03-15, 2020-06-01) — Delta is in 2021
        self.assertGreater(chapters[0]["discovery_count"], 0)

    def test_zero_plays_chapter_has_empty_top_artists(self) -> None:
        # No plays in the trip period (2021 artists not in df)
        df = _make_df(
            artists=["Alpha", "Beta"],
            dates=["2020-03-10", "2020-03-15"],
        )
        assumptions = _make_assumptions(include_trips=True)
        chapters = build_life_chapters(df, assumptions)
        trip_chapter = next(c for c in chapters if "Berlin" in c["label"])
        self.assertEqual(trip_chapter["total_plays"], 0)
        self.assertEqual(trip_chapter["top_artists"], [])
        self.assertIsNone(trip_chapter["top_album"])

    def test_exclusive_artists_high_concentration(self) -> None:
        # Artist "Solo" appears only in the trip period with many plays
        artists = ["Solo"] * 10 + ["Common"] * 3
        dates = (
            ["2021-01-05"] * 10  # all in trip period
            + ["2020-03-10", "2020-06-01", "2021-01-10"]  # Common across periods
        )
        df = _make_df(artists=artists, dates=dates)
        assumptions = _make_assumptions(include_trips=True)
        chapters = build_life_chapters(df, assumptions, min_plays_exclusive=5)
        trip_chapter = next(c for c in chapters if "Berlin" in c["label"])
        # "Solo" plays 10 out of 10 total — uniqueness = 1.0 >= 0.8
        self.assertIn("Solo", trip_chapter["exclusive_artists"])

    def test_location_includes_city_and_country(self) -> None:
        df = _make_df()
        assumptions = _make_assumptions(include_trips=True)
        chapters = build_life_chapters(df, assumptions)
        residency_chapter = chapters[0]
        self.assertIn("Reykjavik", residency_chapter["location"])
        self.assertIn("Iceland", residency_chapter["location"])

    def test_trip_label_prefixed_with_trip_to(self) -> None:
        df = _make_df()
        assumptions = _make_assumptions(include_trips=True)
        chapters = build_life_chapters(df, assumptions)
        trip_chapter = next(c for c in chapters if "Berlin" in c["label"])
        self.assertTrue(trip_chapter["label"].startswith("Trip to"))

    def test_top_album_is_most_played(self) -> None:
        artists = ["A", "A", "A", "B"]
        dates = ["2020-03-01", "2020-04-01", "2020-05-01", "2020-06-01"]
        df = _make_df(artists=artists, dates=dates)
        # Override albums so "Popular Album" dominates
        df["album"] = ["Popular Album", "Popular Album", "Popular Album", "Other Album"]
        assumptions = _make_assumptions(include_trips=False)
        chapters = build_life_chapters(df, assumptions)
        self.assertEqual(chapters[0]["top_album"], "Popular Album")

    def test_missing_residency_only_trips(self) -> None:
        df = _make_df()
        assumptions = {
            "residency": [],
            "trips": [
                {"start": "2021-01-01", "end": "2021-03-31", "city": "Paris", "country": "France"}
            ],
            "holidays": [],
            "defaults": {},
        }
        chapters = build_life_chapters(df, assumptions)
        self.assertEqual(len(chapters), 1)
        self.assertIn("Paris", chapters[0]["label"])


class TestDetectTripsFromSwarm(unittest.TestCase):
    """Unit tests for detect_trips_from_swarm in analysis_utils."""

    def _home_assumptions(self) -> dict:
        """Assumptions with a home residency in Reykjavik (lat 64.13, lng -21.82)."""
        return {
            "residency": [
                {
                    "start": "2020-01-01",
                    "end": "2025-12-31",
                    "city": "Reykjavik",
                    "country": "Iceland",
                    "lat": 64.13,
                    "lng": -21.82,
                    "timezone": "Atlantic/Reykjavik",
                }
            ],
            "trips": [],
            "holidays": [],
            "defaults": {},
        }

    def test_returns_empty_for_empty_df(self) -> None:
        result = detect_trips_from_swarm(pd.DataFrame(), self._home_assumptions())
        self.assertEqual(result, [])

    def test_returns_empty_for_missing_columns(self) -> None:
        df = pd.DataFrame({"lat": [1.0], "lng": [2.0]})  # no timestamp
        result = detect_trips_from_swarm(df, self._home_assumptions())
        self.assertEqual(result, [])

    def test_home_checkins_not_included(self) -> None:
        # Check-in right in Reykjavik — distance 0 km, should not trigger a trip
        ts = int(pd.Timestamp("2021-06-01").timestamp())
        df = _make_swarm_df([64.13], [-21.82], [ts])
        result = detect_trips_from_swarm(df, self._home_assumptions(), radius_km=80)
        self.assertEqual(result, [])

    def test_far_checkins_detected_as_trip(self) -> None:
        # Berlin is ~3000 km from Reykjavik
        ts = int(pd.Timestamp("2021-06-01 12:00").timestamp())
        df = _make_swarm_df([52.52], [13.40], [ts], cities=["Berlin"], countries=["Germany"])
        result = detect_trips_from_swarm(df, self._home_assumptions(), radius_km=80)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["city"], "Berlin")
        self.assertEqual(result[0]["country"], "Germany")

    def test_consecutive_checkins_merged_into_one_trip(self) -> None:
        # Two check-ins 1 day apart — should form one cluster (gap_days=2)
        ts1 = int(pd.Timestamp("2021-06-01").timestamp())
        ts2 = int(pd.Timestamp("2021-06-02").timestamp())
        df = _make_swarm_df([52.52, 52.52], [13.40, 13.40], [ts1, ts2])
        result = detect_trips_from_swarm(df, self._home_assumptions(), radius_km=80, gap_days=2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["checkin_count"], 2)

    def test_gap_splits_into_two_trips(self) -> None:
        # Two check-ins 10 days apart — should be two trips (gap_days=2)
        ts1 = int(pd.Timestamp("2021-06-01").timestamp())
        ts2 = int(pd.Timestamp("2021-06-15").timestamp())
        df = _make_swarm_df([52.52, 48.86], [13.40, 2.35], [ts1, ts2])
        result = detect_trips_from_swarm(df, self._home_assumptions(), radius_km=80, gap_days=2)
        self.assertEqual(len(result), 2)

    def test_trip_dict_has_required_keys(self) -> None:
        ts = int(pd.Timestamp("2021-06-01 12:00").timestamp())
        df = _make_swarm_df([52.52], [13.40], [ts])
        result = detect_trips_from_swarm(df, self._home_assumptions(), radius_km=80)
        self.assertEqual(len(result), 1)
        required = {"start", "end", "city", "country", "lat", "lng", "checkin_count"}
        self.assertTrue(required.issubset(result[0].keys()))

    def test_progress_callback_called(self) -> None:
        ts = int(pd.Timestamp("2021-06-01 12:00").timestamp())
        df = _make_swarm_df([52.52], [13.40], [ts])
        messages: list[str] = []
        detect_trips_from_swarm(
            df, self._home_assumptions(), radius_km=80, progress_cb=messages.append
        )
        self.assertTrue(len(messages) > 0)

    def test_returns_empty_when_no_home_assumption(self) -> None:
        ts = int(pd.Timestamp("2021-06-01 12:00").timestamp())
        df = _make_swarm_df([52.52], [13.40], [ts])
        empty_assumptions: dict = {"residency": [], "trips": [], "holidays": [], "defaults": {}}
        result = detect_trips_from_swarm(df, empty_assumptions, radius_km=80)
        self.assertEqual(result, [])

    def test_most_common_city_used_for_cluster(self) -> None:
        # Three Berlin check-ins + one Paris — Berlin should win
        ts_base = int(pd.Timestamp("2021-06-01").timestamp())
        one_day = 86_400
        lats = [52.52, 52.52, 52.52, 48.86]
        lngs = [13.40, 13.40, 13.40, 2.35]
        timestamps = [ts_base, ts_base + one_day, ts_base + 2 * one_day, ts_base + 3 * one_day]
        cities = ["Berlin", "Berlin", "Berlin", "Paris"]
        countries = ["Germany", "Germany", "Germany", "France"]
        df = _make_swarm_df(lats, lngs, timestamps, cities=cities, countries=countries)
        result = detect_trips_from_swarm(df, self._home_assumptions(), radius_km=80, gap_days=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["city"], "Berlin")


class TestCacheHelpers(unittest.TestCase):
    """Unit tests for the JSON cache I/O helpers."""

    def test_load_returns_empty_list_when_file_missing(self) -> None:
        result = _load_detected_trips_cache("/nonexistent/path/trips.json")
        self.assertEqual(result, [])

    def test_save_and_load_roundtrip(self) -> None:
        trips = [
            {
                "start": "2021-06-01",
                "end": "2021-06-07",
                "city": "Berlin",
                "country": "Germany",
                "lat": 52.52,
                "lng": 13.40,
                "checkin_count": 5,
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "trips.json")
            _save_detected_trips_cache(trips, path)
            loaded = _load_detected_trips_cache(path)
        self.assertEqual(loaded, trips)

    def test_save_creates_parent_directories(self) -> None:
        trips: list[dict] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nested", "dir", "trips.json")
            _save_detected_trips_cache(trips, path)
            self.assertTrue(os.path.exists(path))


class TestRenderLifeInChapters(unittest.TestCase):
    """Integration tests for the render_life_in_chapters Streamlit page function."""

    def _make_full_df(self) -> pd.DataFrame:
        """Return a listening DataFrame with 2020 and 2021 data."""
        return _make_df()

    @patch("streamlit.info")
    @patch("streamlit.header")
    @patch("streamlit.caption")
    def test_empty_state_when_no_df(
        self,
        mock_caption: MagicMock,
        mock_header: MagicMock,
        mock_info: MagicMock,
    ) -> None:
        with patch("streamlit.session_state", {"df": None}):
            render_life_in_chapters()
        mock_info.assert_called_once()

    @patch("pages.life_in_chapters._load_detected_trips_cache", return_value=[])
    @patch("streamlit.expander")
    @patch("streamlit.warning")
    @patch("streamlit.header")
    @patch("streamlit.caption")
    def test_warning_when_no_assumptions(
        self,
        mock_caption: MagicMock,
        mock_header: MagicMock,
        mock_warning: MagicMock,
        mock_expander: MagicMock,
        _mock_cache: MagicMock,
    ) -> None:
        expander_cm = MagicMock()
        expander_cm.__enter__ = MagicMock(return_value=expander_cm)
        expander_cm.__exit__ = MagicMock(return_value=False)
        mock_expander.return_value = expander_cm

        df = self._make_full_df()
        assumptions_no_periods = {
            "residency": [],
            "trips": [],
            "holidays": [],
            "defaults": {},
        }
        with (
            patch("streamlit.session_state", {"df": df, "_loaded_config": None}),
            patch(
                "pages.life_in_chapters.load_assumptions",
                return_value=assumptions_no_periods,
            ),
        ):
            render_life_in_chapters()
        mock_warning.assert_called_once()

    @patch("pages.life_in_chapters._load_detected_trips_cache", return_value=[])
    @patch("streamlit.selectbox")
    @patch("streamlit.info")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    @patch("streamlit.expander")
    @patch("streamlit.header")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.container")
    @patch("streamlit.slider")
    def test_renders_chapters_with_data(
        self,
        mock_slider: MagicMock,
        mock_container: MagicMock,
        mock_subheader: MagicMock,
        mock_markdown: MagicMock,
        mock_divider: MagicMock,
        mock_caption: MagicMock,
        mock_header: MagicMock,
        mock_expander: MagicMock,
        mock_columns: MagicMock,
        mock_metric: MagicMock,
        mock_info: MagicMock,
        mock_selectbox: MagicMock,
        _mock_cache: MagicMock,
    ) -> None:
        df = self._make_full_df()
        assumptions = _make_assumptions(include_trips=True)

        # Set up context manager mocks for expander and container
        expander_cm = MagicMock()
        expander_cm.__enter__ = MagicMock(return_value=expander_cm)
        expander_cm.__exit__ = MagicMock(return_value=False)
        mock_expander.return_value = expander_cm

        container_cm = MagicMock()
        container_cm.__enter__ = MagicMock(return_value=container_cm)
        container_cm.__exit__ = MagicMock(return_value=False)
        mock_container.return_value = container_cm

        col_mock = MagicMock()

        def _columns_side_effect(spec: object) -> list[MagicMock]:
            """Return correct number of column mocks based on the spec argument."""
            if isinstance(spec, int):
                return [col_mock] * spec
            if isinstance(spec, (list, tuple)):
                return [col_mock] * len(spec)
            return [col_mock, col_mock]

        mock_columns.side_effect = _columns_side_effect
        # Range slider returns a (min, max) tuple; selectbox returns "All years"
        mock_slider.return_value = (0, 9999)
        mock_selectbox.return_value = "All years"

        with (
            patch(
                "streamlit.session_state",
                {"df": df, "_loaded_config": (None, None, None), "swarm_df": None},
            ),
            patch(
                "pages.life_in_chapters.load_assumptions",
                return_value=assumptions,
            ),
        ):
            render_life_in_chapters()

        mock_header.assert_called_with("Life in Chapters")
        # Banner metrics should be called
        self.assertTrue(mock_metric.called)

    @patch("pages.life_in_chapters._load_detected_trips_cache", return_value=[])
    @patch("streamlit.info")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    @patch("streamlit.expander")
    @patch("streamlit.header")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.container")
    @patch("streamlit.slider")
    def test_filter_hides_low_play_chapters(
        self,
        mock_slider: MagicMock,
        mock_container: MagicMock,
        mock_subheader: MagicMock,
        mock_markdown: MagicMock,
        mock_divider: MagicMock,
        mock_caption: MagicMock,
        mock_header: MagicMock,
        mock_expander: MagicMock,
        mock_columns: MagicMock,
        mock_metric: MagicMock,
        mock_info: MagicMock,
        _mock_cache: MagicMock,
    ) -> None:
        """Chapters with plays outside the filter range are hidden."""
        df = self._make_full_df()
        assumptions = _make_assumptions(include_trips=True)

        expander_cm = MagicMock()
        expander_cm.__enter__ = MagicMock(return_value=expander_cm)
        expander_cm.__exit__ = MagicMock(return_value=False)
        mock_expander.return_value = expander_cm

        container_cm = MagicMock()
        container_cm.__enter__ = MagicMock(return_value=container_cm)
        container_cm.__exit__ = MagicMock(return_value=False)
        mock_container.return_value = container_cm

        col_mock = MagicMock()

        def _columns_side_effect(spec: object) -> list[MagicMock]:
            if isinstance(spec, int):
                return [col_mock] * spec
            if isinstance(spec, (list, tuple)):
                return [col_mock] * len(spec)
            return [col_mock, col_mock]

        mock_columns.side_effect = _columns_side_effect

        # Set filter range so no chapters qualify (min=9999 > any chapter's plays)
        mock_slider.return_value = (9999, 10000)

        with (
            patch(
                "streamlit.session_state",
                {"df": df, "_loaded_config": (None, None, None), "swarm_df": None},
            ),
            patch(
                "pages.life_in_chapters.load_assumptions",
                return_value=assumptions,
            ),
        ):
            render_life_in_chapters()

        # st.info should be called because no chapters pass the filter
        mock_info.assert_called()

    @patch("pages.life_in_chapters._load_detected_trips_cache", return_value=[])
    @patch("streamlit.selectbox")
    @patch("streamlit.info")
    @patch("streamlit.metric")
    @patch("streamlit.columns")
    @patch("streamlit.expander")
    @patch("streamlit.header")
    @patch("streamlit.caption")
    @patch("streamlit.divider")
    @patch("streamlit.markdown")
    @patch("streamlit.subheader")
    @patch("streamlit.container")
    @patch("streamlit.slider")
    def test_year_filter_limits_chapters(
        self,
        mock_slider: MagicMock,
        mock_container: MagicMock,
        mock_subheader: MagicMock,
        mock_markdown: MagicMock,
        mock_divider: MagicMock,
        mock_caption: MagicMock,
        mock_header: MagicMock,
        mock_expander: MagicMock,
        mock_columns: MagicMock,
        mock_metric: MagicMock,
        mock_info: MagicMock,
        mock_selectbox: MagicMock,
        _mock_cache: MagicMock,
    ) -> None:
        """Selecting a specific year shows only chapters that overlap that year."""
        df = self._make_full_df()
        # Two chapters: 2020 residency (3 plays) and 2021 trip (2 plays)
        assumptions = _make_assumptions(include_trips=True)

        expander_cm = MagicMock()
        expander_cm.__enter__ = MagicMock(return_value=expander_cm)
        expander_cm.__exit__ = MagicMock(return_value=False)
        mock_expander.return_value = expander_cm

        container_cm = MagicMock()
        container_cm.__enter__ = MagicMock(return_value=container_cm)
        container_cm.__exit__ = MagicMock(return_value=False)
        mock_container.return_value = container_cm

        col_mock = MagicMock()

        def _columns_side_effect(spec: object) -> list[MagicMock]:
            if isinstance(spec, int):
                return [col_mock] * spec
            if isinstance(spec, (list, tuple)):
                return [col_mock] * len(spec)
            return [col_mock, col_mock]

        mock_columns.side_effect = _columns_side_effect
        mock_slider.return_value = (0, 9999)
        # Select 2020 — only the Reykjavik chapter should render
        mock_selectbox.return_value = "2020"

        rendered_subheaders: list[str] = []
        mock_subheader.side_effect = rendered_subheaders.append

        with (
            patch(
                "streamlit.session_state",
                {"df": df, "_loaded_config": (None, None, None), "swarm_df": None},
            ),
            patch("pages.life_in_chapters.load_assumptions", return_value=assumptions),
        ):
            render_life_in_chapters()

        # Only the 2020 Reykjavik chapter title should appear
        self.assertIn("Reykjavik", rendered_subheaders)
        self.assertNotIn("Berlin", rendered_subheaders)


if __name__ == "__main__":
    unittest.main()
