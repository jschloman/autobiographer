"""Abstract base class for all Autobiographer data source plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

# Required columns per plugin type. Validated at load time.
_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "what-when": ["timestamp", "label", "sublabel", "category", "source_id"],
    "where-when": ["timestamp", "lat", "lng", "place_name", "place_type", "source_id"],
}


def validate_schema(df: pd.DataFrame, plugin_type: str) -> None:
    """Raise ValueError if df is missing required columns for plugin_type.

    Args:
        df: DataFrame returned by a plugin's load() method.
        plugin_type: Either "what-when" or "where-when".

    Raises:
        ValueError: If any required column is absent from df.
    """
    required = _REQUIRED_COLUMNS.get(plugin_type, [])
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Plugin type '{plugin_type}' is missing required columns: {missing}")


class SourcePlugin(ABC):
    """Base class for all data source plugins.

    Subclasses must declare PLUGIN_TYPE, PLUGIN_ID, and DISPLAY_NAME as class
    attributes, and implement get_config_fields() and load().

    Plugin types:
        "what-when": Activity sources (music, films, books). Must emit columns:
            timestamp, label, sublabel, category, source_id.
        "where-when": Location sources (check-ins, GPS routes). Must emit columns:
            timestamp, lat, lng, place_name, place_type, source_id.
    """

    PLUGIN_TYPE: str  # "what-when" or "where-when"
    PLUGIN_ID: str  # unique identifier, e.g. "lastfm", "swarm"
    DISPLAY_NAME: str  # human-readable name for the UI
    ICON: str = ":material/database:"  # Material icon token shown in the sidebar

    @abstractmethod
    def get_config_fields(self) -> list[dict[str, Any]]:
        """Declare sidebar config fields required by this plugin.

        Each field dict must contain:
            key (str): Config dict key.
            label (str): Display label for the UI widget.
            type (str): Widget type. Supported values:
                "file_path" — opens a native file picker dialog.
                "dir_path"  — opens a native directory picker dialog.
                "text"      — plain text input (no file dialog).
                "toggle"    — boolean checkbox.

        Optional keys:
            file_types (list[tuple[str, str]]): Pairs of (description, glob
                pattern) passed to the file dialog, e.g.
                ``[("CSV files", "*.csv"), ("All files", "*.*")]``.
                Only used when type is "file_path".

        Returns:
            List of field descriptor dicts.
        """

    @abstractmethod
    def load(self, config: dict[str, Any]) -> pd.DataFrame:
        """Load and return a normalized DataFrame for this source.

        The returned DataFrame must include all columns required for
        PLUGIN_TYPE (see validate_schema). Implementations should call
        validate_schema() before returning.

        Args:
            config: Dict of values keyed by the fields from get_config_fields().

        Returns:
            Normalized DataFrame.
        """

    def get_schema(self) -> dict[str, str]:
        """Return column name → description metadata for this plugin.

        Override to provide richer schema documentation for downstream
        view compatibility checks.

        Returns:
            Dict mapping column names to human-readable descriptions.
        """
        return {}
