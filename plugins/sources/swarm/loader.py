"""Foursquare/Swarm source plugin.

Wraps the existing load_swarm_data() and load_assumptions() functions and
normalizes the resulting DataFrame to the "where-when" schema expected by
the DataBroker.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from plugins.sources import register
from plugins.sources.base import SourcePlugin, validate_schema


@register
class SwarmPlugin(SourcePlugin):
    """Load Foursquare/Swarm check-in history from a local JSON export directory."""

    PLUGIN_TYPE = "where-when"
    PLUGIN_ID = "swarm"
    DISPLAY_NAME = "Foursquare / Swarm Check-ins"

    def get_config_fields(self) -> list[dict[str, Any]]:
        """Declare sidebar config fields for the Swarm plugin.

        Returns:
            List of field descriptors for swarm_dir and assumptions_file.
        """
        return [
            {
                "key": "swarm_dir",
                "label": "Swarm JSON export directory",
                "type": "path",
            },
            {
                "key": "assumptions_file",
                "label": "Location assumptions JSON (optional)",
                "type": "path",
            },
        ]

    def load(self, config: dict[str, Any]) -> pd.DataFrame:
        """Load Swarm check-ins and return a normalized where-when DataFrame.

        Reads check-in JSON files from swarm_dir via load_swarm_data(), then
        maps existing columns to the normalized schema (place_name, place_type).
        Original columns are preserved. The assumptions file is loaded but not
        applied here — temporal merging is the DataBroker's responsibility.

        Args:
            config: Must contain "swarm_dir". May contain "assumptions_file".

        Returns:
            DataFrame with original columns plus normalized schema columns.

        Raises:
            ValueError: If required schema columns cannot be produced.
        """
        from analysis_utils import load_swarm_data

        swarm_dir: str = config.get("swarm_dir", "")
        if not swarm_dir:
            return pd.DataFrame()

        df = load_swarm_data(swarm_dir)

        if df.empty:
            return df

        # Normalize to where-when schema. Existing columns already include
        # lat, lng, and place_name. Map 'source' → place_type if present.
        if "place_type" not in df.columns:
            df = df.assign(place_type=df.get("source", "venue"))

        df = df.assign(source_id=self.PLUGIN_ID)

        validate_schema(df, self.PLUGIN_TYPE)
        return df

    def get_schema(self) -> dict[str, str]:
        """Return column descriptions for the Swarm plugin.

        Returns:
            Dict mapping column names to descriptions.
        """
        return {
            "timestamp": "Unix timestamp of the check-in (UTC)",
            "lat": "Latitude (WGS84)",
            "lng": "Longitude (WGS84)",
            "place_name": "Venue or location name",
            "place_type": "Location category (e.g. 'venue', 'city')",
            "source_id": "Plugin identifier ('swarm')",
        }
