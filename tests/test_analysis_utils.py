import os
import unittest

import pandas as pd

from analysis_utils import (
    compute_vacation_stats,
    detect_trip_periods,
    get_artist_monthly_ranks,
    get_cumulative_plays,
    get_day_hour_heatmap,
    get_forgotten_favorites,
    get_genre_weekly,
    get_hourly_distribution,
    get_listening_intensity,
    get_listening_streaks,
    get_milestones,
    get_top_entities,
    label_listening_context,
    load_listening_data,
)


class TestAnalysisUtils(unittest.TestCase):
    def setUp(self):
        self.test_csv = "data/test_analysis_utils.csv"
        os.makedirs("data", exist_ok=True)
        self.df = pd.DataFrame(
            {
                "artist": ["Artist 1", "Artist 2", "Artist 1"],
                "album": ["Album 1", "Album 2", "Album 1"],
                "track": ["Track 1", "Track 2", "Track 3"],
                "timestamp": [1610000000, 1610000100, 1610000200],
                "date_text": ["2021-01-01 10:00", "2021-01-01 10:01", "2021-01-01 11:02"],
            }
        )
        self.df.to_csv(self.test_csv, index=False)

    def tearDown(self):
        if os.path.exists(self.test_csv):
            os.remove(self.test_csv)

    def test_load_listening_data(self):
        df = load_listening_data(self.test_csv)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["date_text"]))

    def test_get_top_entities(self):
        top_artists = get_top_entities(self.df, entity="artist")
        self.assertEqual(len(top_artists), 2)
        self.assertEqual(top_artists.iloc[0]["artist"], "Artist 1")
        self.assertEqual(top_artists.iloc[0]["Plays"], 2)

    def test_get_listening_intensity(self):
        df_loaded = load_listening_data(self.test_csv)
        intensity_day = get_listening_intensity(df_loaded, freq="D")
        self.assertEqual(len(intensity_day), 1)
        self.assertEqual(intensity_day.iloc[0]["Plays"], 3)

        intensity_week = get_listening_intensity(df_loaded, freq="W")
        self.assertEqual(len(intensity_week), 1)

    def test_get_listening_intensity_empty(self):
        empty_df = pd.DataFrame(columns=["artist", "date_text"])
        intensity = get_listening_intensity(empty_df)
        self.assertTrue(intensity.empty)

    def test_get_milestones(self):
        # Create a df with enough tracks for a milestone
        data = []
        for i in range(1001):
            data.append(
                {
                    "artist": f"Artist {i}",
                    "track": f"Track {i}",
                    "date_text": pd.Timestamp("2021-01-01") + pd.Timedelta(minutes=i),
                }
            )
        df = pd.DataFrame(data)
        milestones = get_milestones(df, intervals=[1000])
        self.assertEqual(len(milestones), 1)
        self.assertEqual(milestones.iloc[0]["Milestone"], "1,000 Tracks")

    def test_get_listening_streaks(self):
        # 3 consecutive days
        dates = [
            "2021-01-01 10:00",
            "2021-01-02 10:00",
            "2021-01-03 10:00",
            "2021-01-05 10:00",  # Gap
        ]
        df = pd.DataFrame({"date_text": pd.to_datetime(dates)})
        streaks = get_listening_streaks(df)
        self.assertEqual(streaks["longest_streak"], 3)

    def test_get_forgotten_favorites(self):
        # Artist 1 played 6 months ago, not recently
        now = pd.Timestamp.now()
        past = now - pd.DateOffset(months=7)
        recent = now - pd.DateOffset(days=1)

        df = pd.DataFrame({"artist": ["Artist 1", "Artist 2"], "date_text": [past, recent]})
        forgotten = get_forgotten_favorites(df, months_threshold=6)
        self.assertEqual(len(forgotten), 1)
        self.assertEqual(forgotten.iloc[0]["Artist"], "Artist 1")

    def test_get_cumulative_plays(self):
        df_loaded = load_listening_data(self.test_csv)
        cumulative = get_cumulative_plays(df_loaded)
        self.assertEqual(len(cumulative), 1)
        self.assertEqual(cumulative.iloc[0]["CumulativePlays"], 3)

    def test_get_hourly_distribution(self):
        df_loaded = load_listening_data(self.test_csv)
        hourly = get_hourly_distribution(df_loaded)
        self.assertEqual(len(hourly), 2)  # Hour 10 and 11
        self.assertEqual(hourly[hourly["hour"] == 10].iloc[0]["Plays"], 2)
        self.assertEqual(hourly[hourly["hour"] == 11].iloc[0]["Plays"], 1)

    def test_get_listening_streaks_single_date(self):
        df = pd.DataFrame({"date_text": pd.to_datetime(["2021-06-15"])})
        streaks = get_listening_streaks(df)
        self.assertEqual(streaks["longest_streak"], 1)
        self.assertEqual(streaks["last_active"].isoformat(), "2021-06-15")

    def test_get_listening_streaks_current_active(self):
        today = pd.Timestamp.now().normalize()
        dates = pd.to_datetime([today - pd.Timedelta(days=1), today])
        df = pd.DataFrame({"date_text": dates})
        streaks = get_listening_streaks(df)
        self.assertEqual(streaks["longest_streak"], 2)
        self.assertEqual(streaks["current_streak"], 2)

    def test_get_day_hour_heatmap_shape(self):
        df = load_listening_data(self.test_csv)
        pivot = get_day_hour_heatmap(df)
        self.assertFalse(pivot.empty)
        self.assertIn(10, pivot.columns)
        self.assertIn(11, pivot.columns)

    def test_get_genre_weekly_returns_expected_columns(self):
        dates = pd.to_datetime(["2021-01-04", "2021-01-04", "2021-01-11", "2021-01-11"])
        df = pd.DataFrame(
            {
                "artist": ["Artist A", "Artist B", "Artist A", "Artist A"],
                "date_text": dates,
            }
        )
        result = get_genre_weekly(df, n=5)
        self.assertListEqual(list(result.columns), ["date", "genre", "scrobbles"])

    def test_get_genre_weekly_aggregates_correctly(self):
        dates = pd.to_datetime(["2021-01-04", "2021-01-04", "2021-01-11"])
        df = pd.DataFrame({"artist": ["Artist A", "Artist A", "Artist A"], "date_text": dates})
        result = get_genre_weekly(df, n=2)
        self.assertEqual(result["scrobbles"].sum(), 3)
        self.assertEqual(len(result), 2)  # two distinct weeks

    def test_get_genre_weekly_empty(self):
        empty = pd.DataFrame(columns=["artist", "date_text"])
        result = get_genre_weekly(empty)
        self.assertTrue(result.empty)

    def test_get_genre_weekly_limits_to_top_n(self):
        dates = pd.to_datetime(["2021-01-04"] * 5)
        df = pd.DataFrame({"artist": ["A", "B", "C", "D", "E"], "date_text": dates})
        result = get_genre_weekly(df, n=3)
        self.assertLessEqual(result["genre"].nunique(), 3)

    def test_get_artist_monthly_ranks_columns(self):
        dates = pd.to_datetime(["2021-01-15", "2021-01-20", "2021-02-10"])
        df = pd.DataFrame({"artist": ["Artist A", "Artist B", "Artist A"], "date_text": dates})
        result = get_artist_monthly_ranks(df, n=5)
        self.assertListEqual(list(result.columns), ["month", "artist", "rank"])

    def test_get_artist_monthly_ranks_rank_1_is_highest_plays(self):
        dates = pd.to_datetime(["2021-01-01"] * 3 + ["2021-01-02"])
        df = pd.DataFrame(
            {"artist": ["Artist A", "Artist A", "Artist A", "Artist B"], "date_text": dates}
        )
        result = get_artist_monthly_ranks(df, n=2)
        jan = result[result["month"].dt.month == 1]
        rank1_artist = jan.loc[jan["rank"] == 1, "artist"].values[0]
        self.assertEqual(rank1_artist, "Artist A")

    def test_get_artist_monthly_ranks_empty(self):
        empty = pd.DataFrame(columns=["artist", "date_text"])
        result = get_artist_monthly_ranks(empty)
        self.assertTrue(result.empty)


class TestDetectTripPeriods(unittest.TestCase):
    """Tests for detect_trip_periods."""

    def _assumptions_with_trips(self) -> dict:
        return {
            "trips": [
                {"start": "2021-03-01", "end": "2021-03-07", "city": "Paris"},
                {"start": "2021-06-10", "end": "2021-06-15", "city": "Tokyo"},
            ],
            "defaults": {"city": "Reykjavik, IS"},
        }

    def test_returns_assumption_trips(self) -> None:
        assumptions = self._assumptions_with_trips()
        periods = detect_trip_periods(assumptions)
        self.assertEqual(len(periods), 2)
        self.assertEqual(periods[0][0], pd.Timestamp("2021-03-01"))
        self.assertEqual(periods[0][1], pd.Timestamp("2021-03-07"))

    def test_empty_trips_returns_empty(self) -> None:
        periods = detect_trip_periods({"trips": [], "defaults": {"city": "Home City"}})
        self.assertEqual(periods, [])

    def test_detects_swarm_away_days(self) -> None:
        # 3 consecutive away days should produce one trip period
        swarm_df = pd.DataFrame(
            {
                "timestamp": [
                    int(pd.Timestamp("2021-04-01").timestamp()),
                    int(pd.Timestamp("2021-04-02").timestamp()),
                    int(pd.Timestamp("2021-04-03").timestamp()),
                ],
                "city": ["Amsterdam", "Amsterdam", "Amsterdam"],
            }
        )
        assumptions = {"trips": [], "defaults": {"city": "Reykjavik, IS"}}
        periods = detect_trip_periods(assumptions, swarm_df=swarm_df, home_city="Reykjavik, IS")
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0][0], pd.Timestamp("2021-04-01"))
        self.assertEqual(periods[0][1], pd.Timestamp("2021-04-03"))

    def test_single_away_day_below_threshold_excluded(self) -> None:
        swarm_df = pd.DataFrame(
            {
                "timestamp": [int(pd.Timestamp("2021-04-01").timestamp())],
                "city": ["Amsterdam"],
            }
        )
        assumptions = {"trips": [], "defaults": {"city": "Reykjavik, IS"}}
        periods = detect_trip_periods(
            assumptions, swarm_df=swarm_df, home_city="Reykjavik, IS", min_consecutive_days=2
        )
        self.assertEqual(periods, [])

    def test_swarm_home_checkins_excluded(self) -> None:
        # All swarm check-ins are in home city — no trips detected
        swarm_df = pd.DataFrame(
            {
                "timestamp": [
                    int(pd.Timestamp("2021-04-01").timestamp()),
                    int(pd.Timestamp("2021-04-02").timestamp()),
                    int(pd.Timestamp("2021-04-03").timestamp()),
                ],
                "city": ["Reykjavik, IS", "Reykjavik, IS", "Reykjavik, IS"],
            }
        )
        assumptions = {"trips": [], "defaults": {"city": "Reykjavik, IS"}}
        periods = detect_trip_periods(assumptions, swarm_df=swarm_df, home_city="Reykjavik, IS")
        self.assertEqual(periods, [])

    def test_sorted_output(self) -> None:
        assumptions = {
            "trips": [
                {"start": "2021-06-10", "end": "2021-06-15", "city": "Tokyo"},
                {"start": "2021-03-01", "end": "2021-03-07", "city": "Paris"},
            ],
            "defaults": {"city": "Reykjavik, IS"},
        }
        periods = detect_trip_periods(assumptions)
        self.assertLessEqual(periods[0][0], periods[1][0])

    def test_malformed_trip_skipped(self) -> None:
        assumptions = {
            "trips": [
                {"start": "not-a-date", "end": "2021-03-07"},
                {"start": "2021-05-01", "end": "2021-05-05", "city": "London"},
            ],
            "defaults": {"city": "Reykjavik, IS"},
        }
        periods = detect_trip_periods(assumptions)
        # Only the valid trip should be returned
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0][0], pd.Timestamp("2021-05-01"))


class TestLabelListeningContext(unittest.TestCase):
    """Tests for label_listening_context."""

    def _make_df(self) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "artist": ["A", "B", "C", "D"],
                "date_text": pd.to_datetime(
                    ["2021-03-01", "2021-03-05", "2021-03-10", "2021-03-15"]
                ),
            }
        )
        return df

    def test_labels_trip_rows_correctly(self) -> None:
        df = self._make_df()
        periods = [(pd.Timestamp("2021-03-03"), pd.Timestamp("2021-03-07"))]
        result = label_listening_context(df, periods)
        self.assertIn("context", result.columns)
        self.assertEqual(result.iloc[0]["context"], "home")
        self.assertEqual(result.iloc[1]["context"], "trip")
        self.assertEqual(result.iloc[2]["context"], "home")

    def test_no_periods_all_home(self) -> None:
        df = self._make_df()
        result = label_listening_context(df, [])
        self.assertTrue((result["context"] == "home").all())

    def test_empty_df_returns_with_context_column(self) -> None:
        result = label_listening_context(pd.DataFrame(), [])
        self.assertIn("context", result.columns)
        self.assertTrue(result.empty)

    def test_multiple_periods(self) -> None:
        df = self._make_df()
        periods = [
            (pd.Timestamp("2021-03-01"), pd.Timestamp("2021-03-01")),
            (pd.Timestamp("2021-03-15"), pd.Timestamp("2021-03-15")),
        ]
        result = label_listening_context(df, periods)
        self.assertEqual(result.iloc[0]["context"], "trip")
        self.assertEqual(result.iloc[1]["context"], "home")
        self.assertEqual(result.iloc[3]["context"], "trip")


class TestComputeVacationStats(unittest.TestCase):
    """Tests for compute_vacation_stats."""

    def _make_labeled_df(self) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "artist": ["A", "B", "A", "C", "D"],
                "date_text": pd.to_datetime(
                    ["2021-01-01", "2021-01-02", "2021-01-03", "2021-01-04", "2021-01-05"]
                ),
                "context": ["home", "home", "trip", "trip", "home"],
            }
        )
        return df

    def test_returns_both_contexts(self) -> None:
        df = self._make_labeled_df()
        stats = compute_vacation_stats(df)
        self.assertIn("home", stats)
        self.assertIn("trip", stats)

    def test_avg_daily_scrobbles_correct(self) -> None:
        df = self._make_labeled_df()
        stats = compute_vacation_stats(df)
        # Home: rows 0 (2021-01-01), 1 (2021-01-02), 4 (2021-01-05) → 3 plays over 3 days → 1.0
        self.assertEqual(stats["home"]["avg_daily_scrobbles"], 1.0)
        # Trip: rows 2 (2021-01-03), 3 (2021-01-04) → 2 plays over 2 days → 1.0
        self.assertEqual(stats["trip"]["avg_daily_scrobbles"], 1.0)

    def test_top_artist_identified(self) -> None:
        df = self._make_labeled_df()
        stats = compute_vacation_stats(df)
        self.assertEqual(stats["home"]["top_artist"], "A")

    def test_empty_df_returns_empty_dict(self) -> None:
        stats = compute_vacation_stats(pd.DataFrame())
        self.assertEqual(stats, {})

    def test_missing_context_column_returns_empty(self) -> None:
        df = pd.DataFrame({"artist": ["A"], "date_text": pd.to_datetime(["2021-01-01"])})
        stats = compute_vacation_stats(df)
        self.assertEqual(stats, {})

    def test_single_context_returns_empty_for_missing(self) -> None:
        df = pd.DataFrame(
            {
                "artist": ["A", "B"],
                "date_text": pd.to_datetime(["2021-01-01", "2021-01-02"]),
                "context": ["home", "home"],
            }
        )
        stats = compute_vacation_stats(df)
        self.assertIn("home", stats)
        self.assertEqual(stats.get("trip"), {})


if __name__ == "__main__":
    unittest.main()
