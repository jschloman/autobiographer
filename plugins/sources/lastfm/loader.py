"""Last.fm source plugin.

Wraps the existing load_listening_data() function and normalizes the resulting
DataFrame to the "what-when" schema expected by the DataBroker.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from plugins.sources import register
from plugins.sources.base import SourcePlugin, validate_schema


@register
class LastFmPlugin(SourcePlugin):
    """Load Last.fm listening history from a local CSV file.

    The CSV is produced by the built-in fetch pipeline (run
    ``python autobiographer.py fetch lastfm`` to download it).
    """

    PLUGIN_TYPE = "what-when"
    PLUGIN_ID = "lastfm"
    DISPLAY_NAME = "Last.fm Music History"
    ICON = ":material/headphones:"
    FETCHABLE = True

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

        if df is None or df.empty:
            return pd.DataFrame()

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

    def get_fetch_env_vars(self) -> list[dict[str, str]]:
        """Return env vars required to fetch Last.fm data.

        Returns:
            List of required env var descriptors.
        """
        return [
            {"var": "AUTOBIO_LASTFM_API_KEY", "description": "Last.fm API key"},
            {"var": "AUTOBIO_LASTFM_API_SECRET", "description": "Last.fm API secret"},
            {"var": "AUTOBIO_LASTFM_USERNAME", "description": "Last.fm username"},
        ]

    def get_default_output_path(self) -> str | None:
        """Return the default CSV save path based on the configured username.

        Returns:
            ``"data/lastfm_{username}_tracks.csv"``, or None if the username
            env var is not set.
        """
        username = os.getenv("AUTOBIO_LASTFM_USERNAME", "").strip()
        return f"data/lastfm_{username}_tracks.csv" if username else None

    def get_fetch_identity(self) -> str | None:
        """Return the configured Last.fm username as the fetch identity.

        Returns:
            ``"@username"`` if the env var is set, otherwise None.
        """
        username = os.getenv("AUTOBIO_LASTFM_USERNAME", "").strip()
        return f"@{username}" if username else None

    def fetch(self, output_path: str | None = None, **kwargs: Any) -> None:
        """Fetch Last.fm listening history and save it to a local CSV file.

        Reads credentials from env vars declared by ``get_fetch_env_vars()``.
        Raises ``OSError`` with a descriptive message if any are missing.

        Args:
            output_path: Destination CSV path. Defaults to
                ``data/lastfm_{username}_tracks.csv``.
            **kwargs: Passed through to ``Autobiographer.fetch_recent_tracks()``.
                Recognised keys: ``pages`` (int), ``from_ts`` (int), ``to_ts`` (int),
                ``progress_callback`` (callable(page, total)).

        Raises:
            OSError: If required env vars are not set.
        """
        from autobiographer import Autobiographer

        missing = [v for v in self.get_fetch_env_vars() if not os.getenv(v["var"])]
        if missing:
            lines = "\n".join(f"  {v['var']}: {v['description']}" for v in missing)
            raise OSError(f"Missing required environment variables:\n{lines}")

        api_key = os.getenv("AUTOBIO_LASTFM_API_KEY", "")
        api_secret = os.getenv("AUTOBIO_LASTFM_API_SECRET", "")
        username = os.getenv("AUTOBIO_LASTFM_USERNAME", "")

        save_path = output_path or f"data/lastfm_{username}_tracks.csv"
        client = Autobiographer(api_key, api_secret, username)
        tracks = client.fetch_recent_tracks(
            pages=kwargs.get("pages"),
            from_ts=kwargs.get("from_ts"),
            to_ts=kwargs.get("to_ts"),
            progress_callback=kwargs.get("progress_callback"),
        )
        client.save_tracks_to_csv(tracks, filename=save_path)

    def get_manual_download_instructions(self) -> str:
        """Return instructions for fetching Last.fm data via the CLI.

        Returns:
            Multi-line instruction string.
        """
        return (
            "Last.fm listening history can be fetched automatically.\n\n"
            "1. Set your credentials as environment variables:\n"
            "     AUTOBIO_LASTFM_API_KEY=<your key>\n"
            "     AUTOBIO_LASTFM_API_SECRET=<your secret>\n"
            "     AUTOBIO_LASTFM_USERNAME=<your username>\n\n"
            "2. Run the fetch command:\n"
            "     python autobiographer.py fetch lastfm\n\n"
            "Get an API key at: https://www.last.fm/api/account/create"
        )

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
