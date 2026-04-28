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

    Fetchability:
        Set ``FETCHABLE = True`` and override ``get_fetch_env_vars()``, ``fetch()``,
        and ``get_manual_download_instructions()`` for plugins that can retrieve data
        programmatically. Non-fetchable plugins should only override
        ``get_manual_download_instructions()`` to guide users through a manual export.
    """

    PLUGIN_TYPE: str  # "what-when" or "where-when"
    PLUGIN_ID: str  # unique identifier, e.g. "lastfm", "swarm"
    DISPLAY_NAME: str  # human-readable name for the UI
    ICON: str = ":material/database:"  # Material icon token shown in the sidebar

    FETCHABLE: bool = False
    """True if this plugin can programmatically retrieve data from its source."""

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

    def get_fetch_env_vars(self) -> list[dict[str, str]]:
        """Return environment variables required to fetch data for this plugin.

        Each entry is a dict with:
            var (str): Environment variable name (e.g. ``"AUTOBIO_LASTFM_API_KEY"``).
            description (str): Human-readable description shown when the var is absent.

        Returns:
            List of required env var descriptors. Empty when ``FETCHABLE`` is False.
        """
        return []

    def fetch(self, output_path: str | None = None, **kwargs: Any) -> None:
        """Programmatically fetch data from the source and write it to disk.

        Only called when ``FETCHABLE`` is True. The default implementation raises
        ``NotImplementedError``; fetchable plugins must override this method.

        Args:
            output_path: Destination path for the fetched file or directory.
                If None the plugin writes to its default location under ``data/``.
            **kwargs: Plugin-specific options (e.g. ``pages``, ``from_ts``, ``to_ts``
                for the Last.fm plugin).

        Raises:
            NotImplementedError: Always, unless overridden by a fetchable plugin.
            OSError: If required env vars declared by ``get_fetch_env_vars()`` are
                missing — raised by the overriding implementation, not this base.
        """
        raise NotImplementedError(
            f"{self.PLUGIN_ID} does not support automatic fetching. "
            "Run `python autobiographer.py fetch "
            f"{self.PLUGIN_ID}` for manual download instructions."
        )

    def get_default_output_path(self) -> str | None:
        """Return the default path where fetched data will be saved.

        Used by the sidebar to show the user exactly where the file will land
        before they click Fetch, and to auto-populate the config field after
        a successful fetch.

        Returns:
            Absolute or project-relative path string, or None if the plugin
            does not write to a fixed default location.
        """
        return None

    def get_fetch_identity(self) -> str | None:
        """Return a short string identifying the account or source that will be fetched.

        Shown in the app sidebar next to the fetch button so users can confirm
        the correct account is configured before triggering a download.

        Returns:
            Human-readable identity string (e.g. ``"@username"``), or None if
            not applicable for this plugin.
        """
        return None

    def get_manual_download_instructions(self) -> str:
        """Return human-readable instructions for obtaining this plugin's data.

        Shown in the CLI when ``fetch`` is called on a non-fetchable plugin and
        in the app sidebar when data has not been configured yet. Override in
        every plugin to provide source-specific guidance.

        Returns:
            Multi-line instruction string.
        """
        return (
            f"{self.DISPLAY_NAME} data must be obtained manually. "
            "Please refer to the source's documentation for export options, "
            "then point the plugin's config field at the downloaded file."
        )

    def get_schema(self) -> dict[str, str]:
        """Return column name → description metadata for this plugin.

        Override to provide richer schema documentation for downstream
        view compatibility checks.

        Returns:
            Dict mapping column names to human-readable descriptions.
        """
        return {}
