"""Last.fm source plugin.

Wraps the existing load_listening_data() function and normalizes the resulting
DataFrame to the "what-when" schema expected by the DataBroker.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from plugins.sources import register
from plugins.sources.base import SourcePlugin, validate_schema


@register
class LastFmPlugin(SourcePlugin):
    """Load Last.fm listening history from a local CSV file.

    The CSV is produced by autobiographer.py's fetch + save pipeline.
    """

    PLUGIN_TYPE = "what-when"
    PLUGIN_ID = "lastfm"
    DISPLAY_NAME = "Last.fm Music History"

    def get_config_fields(self) -> list[dict[str, Any]]:
        """Declare sidebar config fields for the Last.fm plugin.

        Returns:
            List containing a single path field for the CSV file.
        """
        return [
            {
                "key": "data_path",
                "label": "Last.fm CSV file",
                "type": "file_path",
                "file_types": [("CSV files", "*.csv"), ("All files", "*.*")],
            }
        ]

    def load(self, config: dict[str, Any]) -> pd.DataFrame:
        """Load Last.fm CSV and return a normalized what-when DataFrame.

        Reads the CSV via load_listening_data(), then adds normalized
        schema columns (label, sublabel, category, source_id) mapped from
        the existing artist/track/album columns. Original columns are
        preserved so visualize.py continues to work without changes.

        Args:
            config: Must contain "data_path" key with path to CSV file.

        Returns:
            DataFrame with original columns plus normalized schema columns.

        Raises:
            ValueError: If required schema columns cannot be produced.
        """
        from analysis_utils import load_listening_data

        data_path: str = config["data_path"]
        df = load_listening_data(data_path)

        if df.empty:
            return df

        # Add normalized schema columns alongside originals so downstream
        # views can use either naming convention.
        df = df.assign(
            label=df["artist"],
            sublabel=df["track"],
            category=df["album"],
            source_id=self.PLUGIN_ID,
        )

        validate_schema(df, self.PLUGIN_TYPE)
        return df

    def get_schema(self) -> dict[str, str]:
        """Return column descriptions for the Last.fm plugin.

        Returns:
            Dict mapping column names to descriptions.
        """
        return {
            "timestamp": "Unix timestamp of the listen (UTC)",
            "label": "Artist name",
            "sublabel": "Track name",
            "category": "Album name",
            "source_id": "Plugin identifier ('lastfm')",
        }
