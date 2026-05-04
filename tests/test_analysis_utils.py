import os
import unittest

import pandas as pd

from analysis_utils import (
    get_artist_monthly_ranks,
    get_cumulative_plays,
    get_forgotten_favorites,
    get_genre_weekly,
    get_hourly_distribution,
    get_listening_intensity,
    get_listening_streaks,
    get_milestones,
    get_top_entities,
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


if __name__ == "__main__":
    unittest.main()
