"""Tests for the static HTML export pipeline."""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from export_html import (
    _build_places_html,
    _table_html,
    build_html,
    build_music_page_html,
    export_report,
    main,
)


def _sample_df() -> pd.DataFrame:
    """Return a minimal listening DataFrame suitable for all export tests."""
    return pd.DataFrame(
        {
            "artist": ["Artist A", "Artist B", "Artist A", "Artist C"],
            "album": ["Album 1", "Album 2", "Album 1", "Album 3"],
            "track": ["Track 1", "Track 2", "Track 3", "Track 4"],
            "timestamp": [1610000000, 1610000100, 1610000200, 1610000300],
            "date_text": pd.to_datetime(
                [
                    "2021-01-07 10:00",
                    "2021-01-08 11:00",
                    "2021-01-09 12:00",
                    "2021-01-10 13:00",
                ]
            ),
        }
    )


def _sample_swarm_df() -> pd.DataFrame:
    """Return a minimal Swarm check-in DataFrame for map tests."""
    return pd.DataFrame(
        {
            "timestamp": [1610000000, 1610000100, 1610000200, 1610000300, 1610000400],
            "offset": [0, 60, 60, 0, -300],
            "city": ["Reykjavik", "London", "London", "New York", "Sydney"],
            "state": ["IS", "ENG", "ENG", "NY", "NSW"],
            "country": [
                "Iceland",
                "United Kingdom",
                "United Kingdom",
                "United States",
                "Australia",
            ],
            "venue": ["Café A", "Pub B", "Pub C", "Bar D", "Café E"],
            "lat": [64.1265, 51.5074, 51.5080, 40.7128, -33.8688],
            "lng": [-21.8174, -0.1278, -0.1285, -74.0060, 151.2093],
        }
    )


class TestTableHtml(unittest.TestCase):
    """Tests for the _table_html helper."""

    def test_empty_df_returns_placeholder(self) -> None:
        html = _table_html(pd.DataFrame())
        self.assertIn("empty-msg", html)

    def test_non_empty_df_renders_headers(self) -> None:
        df = pd.DataFrame({"Artist": ["Radiohead"], "Plays": [42]})
        html = _table_html(df)
        self.assertIn("<th>Artist</th>", html)
        self.assertIn("<td>Radiohead</td>", html)

    def test_table_has_correct_row_count(self) -> None:
        df = pd.DataFrame({"x": [1, 2, 3]})
        html = _table_html(df)
        self.assertEqual(html.count("<tr>"), 4)  # 1 header + 3 data rows


class TestBuildHtml(unittest.TestCase):
    """Tests for the build_html report builder."""

    def setUp(self) -> None:
        self.df = _sample_df()

    def test_returns_valid_html_document(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        self.assertTrue(html.strip().startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", html)

    def test_contains_all_three_tabs(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        self.assertIn("tab-overview", html)
        self.assertIn("tab-listening", html)
        self.assertIn("tab-insights", html)

    def test_contains_plotly_js(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        # Plotly.js bundle should be inlined — the Plotly namespace must be defined.
        self.assertIn("Plotly", html)

    def test_metrics_are_present(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        # 4 tracks, 3 artists, 3 albums in the sample DataFrame.
        self.assertIn("4", html)  # total tracks
        self.assertIn("3", html)  # unique artists / albums

    def test_date_range_in_header(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        # date_range uses strftime 'Jan 2021 – Jan 2021'
        self.assertIn("2021", html)

    def test_generated_at_in_footer(self) -> None:
        html = build_html(self.df, "1999-12-31 23:59")
        self.assertIn("1999-12-31 23:59", html)

    def test_no_external_script_or_link_tags(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        # There must be no externally-loaded scripts or stylesheets.
        # (The inlined plotly.js bundle may contain CDN URL strings as literals,
        # but the document itself must not fetch from any external host.)
        import re

        external_srcs = re.findall(r'<script[^>]+src=["\']https?://', html, re.IGNORECASE)
        external_links = re.findall(r'<link[^>]+href=["\']https?://', html, re.IGNORECASE)
        self.assertEqual(external_srcs, [], "Found external <script src> tags")
        self.assertEqual(external_links, [], "Found external <link href> tags")

    def test_tab_switch_js_present(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        self.assertIn("showTab", html)
        self.assertIn("Plotly.Plots.resize", html)


class TestExportReport(unittest.TestCase):
    """Tests for the export_report file-writer."""

    def test_creates_output_file(self) -> None:
        df = _sample_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "report.html")
            export_report(df, output)
            self.assertTrue(os.path.exists(output))

    def test_output_is_readable_html(self) -> None:
        df = _sample_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "report.html")
            export_report(df, output)
            with open(output, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("<!DOCTYPE html>", content)

    def test_creates_parent_directories(self) -> None:
        df = _sample_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "nested", "deep", "report.html")
            export_report(df, output)
            self.assertTrue(os.path.exists(output))


class TestBuildPlacesHtml(unittest.TestCase):
    """Tests for the _build_places_html Places tab builder."""

    def setUp(self) -> None:
        self.swarm_df = _sample_swarm_df()

    def test_returns_html_string(self) -> None:
        html = _build_places_html(self.swarm_df)
        self.assertIsInstance(html, str)
        self.assertTrue(len(html) > 0)

    def test_contains_metric_counts(self) -> None:
        html = _build_places_html(self.swarm_df)
        # 5 check-ins, 4 unique cities, 3 unique countries in the sample.
        self.assertIn("5", html)
        self.assertIn("4", html)
        self.assertIn("3", html)

    def test_contains_map_and_city_charts(self) -> None:
        html = _build_places_html(self.swarm_df)
        self.assertIn("Where You", html)
        self.assertIn("Top 20 Cities", html)
        self.assertIn("Countries Visited", html)


class TestBuildHtmlWithSwarm(unittest.TestCase):
    """Tests for build_html with Swarm data (Places tab)."""

    def setUp(self) -> None:
        self.df = _sample_df()
        self.swarm_df = _sample_swarm_df()

    def test_places_tab_absent_without_swarm(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00")
        self.assertNotIn("tab-places", html)

    def test_places_tab_present_with_swarm(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00", swarm_df=self.swarm_df)
        self.assertIn("tab-places", html)

    def test_places_nav_button_present_with_swarm(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00", swarm_df=self.swarm_df)
        self.assertIn('data-tab="places"', html)

    def test_places_tab_absent_with_empty_swarm(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00", swarm_df=pd.DataFrame())
        self.assertNotIn("tab-places", html)

    def test_four_tab_buttons_with_swarm(self) -> None:
        html = build_html(self.df, "2024-01-01 00:00", swarm_df=self.swarm_df)
        self.assertIn("tab-overview", html)
        self.assertIn("tab-listening", html)
        self.assertIn("tab-insights", html)
        self.assertIn("tab-places", html)


class TestBuildMusicPageHtml(unittest.TestCase):
    """Tests for the build_music_page_html page-specific export."""

    def setUp(self) -> None:
        self.df = _sample_df()
        self.start = datetime.date(2021, 1, 7)
        self.end = datetime.date(2021, 1, 10)

    def test_returns_valid_html_document(self) -> None:
        html = build_music_page_html(self.df, self.start, self.end, "2024-01-01 00:00 UTC")
        self.assertTrue(html.strip().startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", html)

    def test_title_contains_date_range(self) -> None:
        html = build_music_page_html(self.df, self.start, self.end, "2024-01-01 00:00 UTC")
        self.assertIn("2021-01-07", html)
        self.assertIn("2021-01-10", html)

    def test_contains_plotly_js(self) -> None:
        html = build_music_page_html(self.df, self.start, self.end, "2024-01-01 00:00 UTC")
        self.assertIn("Plotly", html)

    def test_no_external_script_or_link_tags(self) -> None:
        import re

        html = build_music_page_html(self.df, self.start, self.end, "2024-01-01 00:00 UTC")
        external_srcs = re.findall(r'<script[^>]+src=["\']https?://', html, re.IGNORECASE)
        external_links = re.findall(r'<link[^>]+href=["\']https?://', html, re.IGNORECASE)
        self.assertEqual(external_srcs, [], "Found external <script src> tags")
        self.assertEqual(external_links, [], "Found external <link href> tags")

    def test_generated_at_in_footer(self) -> None:
        html = build_music_page_html(self.df, self.start, self.end, "1999-12-31 23:59 UTC")
        self.assertIn("1999-12-31 23:59 UTC", html)

    def test_empty_df_returns_empty_state_html(self) -> None:
        html = build_music_page_html(pd.DataFrame(), self.start, self.end, "2024-01-01 00:00 UTC")
        self.assertIn("No plays", html)
        self.assertTrue(html.strip().startswith("<!DOCTYPE html>"))

    def test_scrobble_count_in_metrics(self) -> None:
        html = build_music_page_html(self.df, self.start, self.end, "2024-01-01 00:00 UTC")
        # 4 rows in sample df
        self.assertIn("4", html)


class TestMain(unittest.TestCase):
    """Tests for the CLI entry point."""

    def test_missing_csv_exits_with_error(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(["nonexistent_file_that_does_not_exist.csv"])
        self.assertEqual(ctx.exception.code, 1)

    def test_no_args_and_no_settings_exits(self) -> None:
        with patch("export_html.LocalSettings") as mock_cls:
            mock_settings = MagicMock()
            mock_settings.get_plugin_config.return_value = {}
            mock_cls.return_value = mock_settings
            with self.assertRaises(SystemExit):
                main([])

    def test_valid_csv_produces_output(self) -> None:
        df = _sample_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "tracks.csv")
            output_path = os.path.join(tmpdir, "report.html")
            df.to_csv(csv_path, index=False)
            main([csv_path, "--output", output_path])
            self.assertTrue(os.path.exists(output_path))

    def test_from_settings_reads_local_settings(self) -> None:
        df = _sample_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "tracks.csv")
            output_path = os.path.join(tmpdir, "report.html")
            df.to_csv(csv_path, index=False)
            with patch("export_html.LocalSettings") as mock_cls:
                mock_settings = MagicMock()
                mock_settings.get_plugin_config.return_value = {"data_path": csv_path}
                mock_cls.return_value = mock_settings
                main(["--from-settings", "--output", output_path])
            self.assertTrue(os.path.exists(output_path))

    def test_swarm_dir_adds_places_tab(self) -> None:
        """Passing --swarm-dir with real check-in files produces a Places tab."""
        df = _sample_df()
        swarm_data = {
            "items": [
                {
                    "createdAt": 1610000000,
                    "timeZoneOffset": 0,
                    "venue": {
                        "name": "Test Venue",
                        "location": {
                            "city": "Reykjavik",
                            "country": "Iceland",
                            "lat": 64.1,
                            "lng": -21.8,
                        },
                    },
                    "lat": 64.1,
                    "lng": -21.8,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "tracks.csv")
            swarm_dir = os.path.join(tmpdir, "swarm")
            os.makedirs(swarm_dir)
            json_path = os.path.join(swarm_dir, "checkins.json")
            with open(json_path, "w") as fh:
                json.dump(swarm_data, fh)
            output_path = os.path.join(tmpdir, "report.html")
            df.to_csv(csv_path, index=False)
            main([csv_path, "--swarm-dir", swarm_dir, "--output", output_path])
            with open(output_path, encoding="utf-8") as fh:
                content = fh.read()
        self.assertIn("tab-places", content)

    def test_invalid_swarm_dir_warns_and_continues(self) -> None:
        """A non-existent --swarm-dir prints a warning but still produces a report."""
        df = _sample_df()
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "tracks.csv")
            output_path = os.path.join(tmpdir, "report.html")
            df.to_csv(csv_path, index=False)
            import contextlib
            import io

            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                main([csv_path, "--swarm-dir", "/nonexistent/swarm", "--output", output_path])
            self.assertIn("Warning", buf.getvalue())
            self.assertTrue(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
