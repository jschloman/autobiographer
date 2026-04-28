import os
import time
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from autobiographer import Autobiographer


class TestAutobiographer(unittest.TestCase):
    def setUp(self):
        self.api_key = "test_key"
        self.api_secret = "test_secret"
        self.username = "test_user"
        self.visualizer = Autobiographer(self.api_key, self.api_secret, self.username)

    @patch("requests.get")
    def test_fetch_recent_tracks(self, mock_get):
        # Mock response from Last.fm
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "recenttracks": {
                "track": [
                    {
                        "artist": {"#text": "Artist 1"},
                        "album": {"#text": "Album 1"},
                        "name": "Track 1",
                        "date": {"uts": "1610000000", "#text": "Date 1"},
                    }
                ],
                "@attr": {"totalPages": "1"},
            }
        }
        mock_get.return_value = mock_response

        tracks = self.visualizer.fetch_recent_tracks(pages=1)

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["name"], "Track 1")
        self.assertEqual(tracks[0]["artist"]["#text"], "Artist 1")

    @patch("requests.get")
    def test_fetch_page(self, mock_get):
        # Mock response from Last.fm
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_get.return_value = mock_response

        data = self.visualizer._fetch_page("user.getinfo", {})

        self.assertEqual(data, {"test": "data"})
        mock_get.assert_called_once()

    def test_save_tracks_to_csv(self):
        # Sample data to save
        tracks = [
            {
                "artist": {"#text": "Artist 1"},
                "album": {"#text": "Album 1"},
                "name": "Track 1",
                "date": {"uts": "1610000000", "#text": "Date 1"},
            }
        ]
        test_filename = "data/test_tracks.csv"

        # Save to CSV
        self.visualizer.save_tracks_to_csv(tracks, filename=test_filename)

        # Verify file exists and content is correct
        self.assertTrue(os.path.exists(test_filename))
        df = pd.read_csv(test_filename)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["artist"], "Artist 1")
        self.assertEqual(df.iloc[0]["track"], "Track 1")

        # Cleanup
        os.remove(test_filename)

    @patch("requests.get")
    def test_fetch_recent_tracks_with_dates(self, mock_get):
        # Mock response from Last.fm
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "recenttracks": {"track": [], "@attr": {"totalPages": "1"}}
        }
        mock_get.return_value = mock_response

        self.visualizer.fetch_recent_tracks(from_ts=1610000000, to_ts=1610000100)

        # Verify that the correct parameters were passed to requests.get
        args, kwargs = mock_get.call_args
        params = kwargs.get("params", {})
        self.assertEqual(params.get("from"), 1610000000)
        self.assertEqual(params.get("to"), 1610000100)

    def test_parse_date_valid(self):
        from autobiographer import _parse_date

        ts = _parse_date("2024-06-15", "from_date")
        self.assertIsInstance(ts, int)
        self.assertGreater(ts, 0)

    def test_parse_date_empty_returns_none(self):
        from autobiographer import _parse_date

        self.assertIsNone(_parse_date("", "from_date"))

    def test_parse_date_invalid_raises(self):
        from autobiographer import _parse_date

        with self.assertRaises(SystemExit):
            _parse_date("not-a-date", "from_date")


class TestRunFetch(unittest.TestCase):
    """Tests for the _run_fetch CLI dispatcher."""

    def _make_args(self, plugin: str, **kwargs: object) -> MagicMock:
        args = MagicMock()
        args.plugin = plugin
        args.output = kwargs.get("output", None)
        args.pages = kwargs.get("pages", None)
        args.from_date = kwargs.get("from_date", None)
        args.to_date = kwargs.get("to_date", None)
        return args

    def test_unknown_plugin_exits(self):
        from autobiographer import _run_fetch

        with patch("plugins.sources.load_builtin_plugins"), patch("plugins.sources.REGISTRY", {}):
            with self.assertRaises(SystemExit):
                _run_fetch(self._make_args("unknown_plugin"))

    def test_non_fetchable_plugin_prints_instructions(self):
        from autobiographer import _run_fetch

        fake_plugin = MagicMock()
        fake_plugin.FETCHABLE = False
        fake_plugin.DISPLAY_NAME = "Test Plugin"
        fake_plugin.get_manual_download_instructions.return_value = "Do this manually."
        fake_cls = MagicMock(return_value=fake_plugin)

        with (
            patch("plugins.sources.load_builtin_plugins"),
            patch("plugins.sources.REGISTRY", {"testplugin": fake_cls}),
            patch("builtins.print") as mock_print,
        ):
            _run_fetch(self._make_args("testplugin"))

        fake_plugin.get_manual_download_instructions.assert_called_once()
        printed = " ".join(str(c) for c in mock_print.call_args_list)
        self.assertIn("Do this manually.", printed)

    def test_missing_env_vars_exits(self):
        from autobiographer import _run_fetch

        fake_plugin = MagicMock()
        fake_plugin.FETCHABLE = True
        fake_plugin.get_fetch_env_vars.return_value = [
            {"var": "AUTOBIO_MISSING_VAR", "description": "A required var"}
        ]
        fake_cls = MagicMock(return_value=fake_plugin)

        with (
            patch("plugins.sources.load_builtin_plugins"),
            patch("plugins.sources.REGISTRY", {"myplugin": fake_cls}),
            patch("os.getenv", return_value=None),
        ):
            with self.assertRaises(SystemExit):
                _run_fetch(self._make_args("myplugin"))

    def test_fetchable_plugin_calls_fetch(self):
        from autobiographer import _run_fetch

        fake_plugin = MagicMock()
        fake_plugin.FETCHABLE = True
        fake_plugin.get_fetch_env_vars.return_value = []
        fake_cls = MagicMock(return_value=fake_plugin)

        with (
            patch("plugins.sources.load_builtin_plugins"),
            patch("plugins.sources.REGISTRY", {"myplugin": fake_cls}),
            patch("builtins.print"),
        ):
            _run_fetch(self._make_args("myplugin", output="/tmp/out.csv", pages=2))

        fake_plugin.fetch.assert_called_once_with(
            output_path="/tmp/out.csv",
            pages=2,
            from_ts=None,
            to_ts=None,
        )

    def test_to_date_shifted_to_end_of_day(self):
        from autobiographer import _run_fetch

        fake_plugin = MagicMock()
        fake_plugin.FETCHABLE = True
        fake_plugin.get_fetch_env_vars.return_value = []
        fake_cls = MagicMock(return_value=fake_plugin)

        with (
            patch("plugins.sources.load_builtin_plugins"),
            patch("plugins.sources.REGISTRY", {"myplugin": fake_cls}),
            patch("builtins.print"),
        ):
            _run_fetch(self._make_args("myplugin", to_date="2026-01-01"))

        _, call_kwargs = fake_plugin.fetch.call_args
        to_ts = call_kwargs["to_ts"]
        expected_base = int(time.mktime(time.strptime("2026-01-01", "%Y-%m-%d")))
        self.assertEqual(to_ts, expected_base + 86399)


if __name__ == "__main__":
    unittest.main()
