"""DataBroker: loads, aligns, and merges data from registered source plugins.

The DataBroker is the central data coordinator. It holds loaded DataFrames
from each plugin, tracks which source types are available, and provides a
merged DataFrame that combines what-when and where-when sources via temporal
join (powered by apply_swarm_offsets for the Swarm/Last.fm case).

Typical usage::

    from plugins.sources import load_builtin_plugins, REGISTRY
    from plugins.sources.base import SourcePlugin
    from core.broker import DataBroker

    load_builtin_plugins()

    broker = DataBroker()
    broker.load(REGISTRY["lastfm"], {"data_path": "data/tracks.csv"})
    broker.load(REGISTRY["swarm"], {"swarm_dir": "data/swarm"})

    df = broker.get_merged_frame(assumptions=assumptions)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from plugins.sources.base import SourcePlugin


class DataBroker:
    """Coordinates loading and merging of multiple source plugins.

    Attributes:
        _sources: Loaded DataFrames keyed by plugin PLUGIN_ID.
        _available_types: Distinct PLUGIN_TYPE values of loaded sources.
    """

    def __init__(self) -> None:
        self._sources: dict[str, pd.DataFrame] = {}
        self._available_types: list[str] = []

    @property
    def available_types(self) -> list[str]:
        """Return list of distinct plugin types currently loaded.

        Returns:
            List of strings, each either "what-when" or "where-when".
        """
        return list(self._available_types)

    def load(self, plugin: SourcePlugin, config: dict[str, Any]) -> pd.DataFrame:
        """Load a source plugin and store the resulting DataFrame.

        Args:
            plugin: An instantiated SourcePlugin subclass.
            config: Config dict matching the plugin's get_config_fields() keys.

        Returns:
            The DataFrame returned by the plugin (may be empty on failure).
        """
        df = plugin.load(config)
        self._sources[plugin.PLUGIN_ID] = df
        if plugin.PLUGIN_TYPE not in self._available_types:
            self._available_types.append(plugin.PLUGIN_TYPE)
        return df

    def get_frame(self, plugin_id: str) -> pd.DataFrame:
        """Return the raw loaded DataFrame for a given plugin.

        Args:
            plugin_id: The PLUGIN_ID of the desired source.

        Returns:
            The loaded DataFrame, or an empty DataFrame if not loaded.
        """
        return self._sources.get(plugin_id, pd.DataFrame())

    def get_frames(self) -> dict[str, pd.DataFrame]:
        """Return all loaded DataFrames keyed by plugin ID.

        Returns:
            Dict of {plugin_id: DataFrame}.
        """
        return dict(self._sources)

    def get_merged_frame(self, assumptions: dict[str, Any] | None = None) -> pd.DataFrame:
        """Return a merged DataFrame combining what-when and where-when sources.

        If both a what-when source (Last.fm) and a where-when source (Swarm)
        are loaded, applies temporal merging via apply_swarm_offsets() to
        annotate what-when records with location and timezone data.

        If only a what-when source is loaded, returns it unmodified.
        If no what-when source is loaded, returns an empty DataFrame.

        Args:
            assumptions: Location assumptions dict from load_assumptions().
                         Required for the Swarm temporal join; pass None to
                         skip location enrichment.

        Returns:
            Merged DataFrame, or the raw what-when frame if no where-when
            source is available.
        """
        lastfm_df = self._sources.get("lastfm", pd.DataFrame())

        if lastfm_df.empty:
            return lastfm_df

        swarm_df = self._sources.get("swarm", pd.DataFrame())

        if swarm_df.empty or assumptions is None:
            return lastfm_df

        from analysis_utils import apply_swarm_offsets

        return apply_swarm_offsets(lastfm_df, swarm_df, assumptions)

    def is_type_available(self, plugin_type: str) -> bool:
        """Check whether any loaded source provides the given plugin type.

        Args:
            plugin_type: Either "what-when" or "where-when".

        Returns:
            True if at least one loaded source has the given type.
        """
        return plugin_type in self._available_types
