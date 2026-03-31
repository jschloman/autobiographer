"""Unit tests for the source plugin infrastructure and built-in plugins."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from plugins.sources import REGISTRY, load_builtin_plugins
from plugins.sources.base import SourcePlugin, validate_schema
from plugins.sources.lastfm.loader import LastFmPlugin
from plugins.sources.swarm.loader import SwarmPlugin


class TestValidateSchema(unittest.TestCase):
    """Tests for the schema validation helper."""

    def test_valid_what_when_schema_passes(self):
        df = pd.DataFrame(
            {
                "timestamp": [1610000000],
                "label": ["Artist A"],
                "sublabel": ["Track A"],
                "category": ["Album A"],
                "source_id": ["lastfm"],
            }
        )
        # Should not raise.
        validate_schema(df, "what-when")

    def test_valid_where_when_schema_passes(self):
        df = pd.DataFrame(
            {
                "timestamp": [1610000000],
                "lat": [40.71],
                "lng": [-74.00],
                "place_name": ["New York"],
                "place_type": ["city"],
                "source_id": ["swarm"],
            }
        )
        validate_schema(df, "where-when")

    def test_missing_column_raises(self):
        df = pd.DataFrame({"timestamp": [1], "label": ["A"]})
        with self.assertRaises(ValueError) as ctx:
            validate_schema(df, "what-when")
        self.assertIn("sublabel", str(ctx.exception))

    def test_unknown_plugin_type_passes(self):
        # Unknown types have no required columns — should not raise.
        df = pd.DataFrame({"anything": [1]})
        validate_schema(df, "unknown-type")


class TestRegistry(unittest.TestCase):
    """Tests for the plugin registry."""

    def setUp(self):
        load_builtin_plugins()

    def test_lastfm_registered(self):
        self.assertIn("lastfm", REGISTRY)

    def test_swarm_registered(self):
        self.assertIn("swarm", REGISTRY)

    def test_registry_values_are_source_plugin_subclasses(self):
        for plugin_cls in REGISTRY.values():
            self.assertTrue(issubclass(plugin_cls, SourcePlugin))


class TestLastFmPlugin(unittest.TestCase):
    """Tests for the LastFmPlugin."""

    def setUp(self):
        self.plugin = LastFmPlugin()
        self.fixture_df = pd.DataFrame(
            {
                "artist": ["Radiohead", "Radiohead"],
                "album": ["OK Computer", "OK Computer"],
                "track": ["Karma Police", "Exit Music"],
                "timestamp": [1610000000, 1610000100],
                "date_text": pd.to_datetime(["2021-01-07 10:00", "2021-01-07 10:05"]),
            }
        )

    def test_plugin_type(self):
        self.assertEqual(self.plugin.PLUGIN_TYPE, "what-when")

    def test_plugin_id(self):
        self.assertEqual(self.plugin.PLUGIN_ID, "lastfm")

    def test_config_fields_returns_list(self):
        fields = self.plugin.get_config_fields()
        self.assertIsInstance(fields, list)
        self.assertTrue(any(f["key"] == "data_path" for f in fields))

    def test_config_field_type_is_file_path(self):
        fields = self.plugin.get_config_fields()
        data_path_field = next(f for f in fields if f["key"] == "data_path")
        self.assertEqual(data_path_field["type"], "file_path")

    def test_config_field_has_file_types(self):
        fields = self.plugin.get_config_fields()
        data_path_field = next(f for f in fields if f["key"] == "data_path")
        self.assertIn("file_types", data_path_field)
        self.assertIsInstance(data_path_field["file_types"], list)

    def test_load_adds_normalized_columns(self):
        with patch("analysis_utils.load_listening_data") as mock_load:
            mock_load.return_value = self.fixture_df.copy()
            df = self.plugin.load({"data_path": "fake/path.csv"})

        self.assertIn("label", df.columns)
        self.assertIn("sublabel", df.columns)
        self.assertIn("category", df.columns)
        self.assertIn("source_id", df.columns)
        self.assertEqual(df["label"].iloc[0], "Radiohead")
        self.assertEqual(df["sublabel"].iloc[0], "Karma Police")
        self.assertEqual(df["source_id"].iloc[0], "lastfm")

    def test_load_preserves_original_columns(self):
        with patch("analysis_utils.load_listening_data") as mock_load:
            mock_load.return_value = self.fixture_df.copy()
            df = self.plugin.load({"data_path": "fake/path.csv"})

        # Original columns must still be present for backward compat.
        self.assertIn("artist", df.columns)
        self.assertIn("track", df.columns)
        self.assertIn("album", df.columns)

    def test_load_returns_empty_df_when_source_empty(self):
        with patch("analysis_utils.load_listening_data") as mock_load:
            mock_load.return_value = pd.DataFrame()
            df = self.plugin.load({"data_path": "fake/path.csv"})

        self.assertTrue(df.empty)

    def test_get_schema_returns_dict(self):
        schema = self.plugin.get_schema()
        self.assertIsInstance(schema, dict)
        self.assertIn("label", schema)


class TestSwarmPlugin(unittest.TestCase):
    """Tests for the SwarmPlugin."""

    def setUp(self):
        self.plugin = SwarmPlugin()
        self.fixture_df = pd.DataFrame(
            {
                "timestamp": [1610000000, 1610000200],
                "lat": [40.71, 51.50],
                "lng": [-74.00, -0.12],
                "place_name": ["New York", "London"],
                "source": ["venue", "venue"],
                "city": ["New York", "London"],
                "country": ["US", "GB"],
            }
        )

    def test_plugin_type(self):
        self.assertEqual(self.plugin.PLUGIN_TYPE, "where-when")

    def test_plugin_id(self):
        self.assertEqual(self.plugin.PLUGIN_ID, "swarm")

    def test_config_fields_returns_list(self):
        fields = self.plugin.get_config_fields()
        self.assertIsInstance(fields, list)
        self.assertTrue(any(f["key"] == "swarm_dir" for f in fields))

    def test_swarm_dir_field_type_is_dir_path(self):
        fields = self.plugin.get_config_fields()
        swarm_dir_field = next(f for f in fields if f["key"] == "swarm_dir")
        self.assertEqual(swarm_dir_field["type"], "dir_path")

    def test_assumptions_field_type_is_file_path(self):
        fields = self.plugin.get_config_fields()
        assumptions_field = next(f for f in fields if f["key"] == "assumptions_file")
        self.assertEqual(assumptions_field["type"], "file_path")
        self.assertIn("file_types", assumptions_field)

    def test_load_adds_normalized_columns(self):
        with patch("analysis_utils.load_swarm_data") as mock_load:
            mock_load.return_value = self.fixture_df.copy()
            df = self.plugin.load({"swarm_dir": "fake/swarm"})

        self.assertIn("place_type", df.columns)
        self.assertIn("source_id", df.columns)
        self.assertEqual(df["source_id"].iloc[0], "swarm")

    def test_load_returns_empty_df_when_no_swarm_dir(self):
        df = self.plugin.load({"swarm_dir": ""})
        self.assertTrue(df.empty)

    def test_load_returns_empty_df_when_source_empty(self):
        with patch("analysis_utils.load_swarm_data") as mock_load:
            mock_load.return_value = pd.DataFrame()
            df = self.plugin.load({"swarm_dir": "fake/swarm"})

        self.assertTrue(df.empty)

    def test_get_schema_returns_dict(self):
        schema = self.plugin.get_schema()
        self.assertIsInstance(schema, dict)
        self.assertIn("lat", schema)


if __name__ == "__main__":
    unittest.main()
