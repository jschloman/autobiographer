"""Persistent local settings manager for autobiographer.

Settings are stored in ``local_settings.json`` at the project root. That file
is gitignored so personal paths and preferences never enter version control.
Copy ``local_settings.json.example`` to ``local_settings.json`` to pre-populate
plugin paths without going through the UI.
"""

from __future__ import annotations

import json
import os
from typing import Any

_DEFAULT_PATH = "local_settings.json"


class LocalSettings:
    """Read/write persistent local settings to a gitignored JSON file.

    Plugin configs are stored under a ``"plugins"`` key, grouped by plugin ID::

        {
          "plugins": {
            "lastfm": {"data_path": "/path/to/tracks.csv"},
            "swarm":  {"swarm_dir": "/path/to/export/"}
          }
        }

    Args:
        path: Path to the settings file. Defaults to ``local_settings.json``
            relative to the current working directory.
    """

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self._path = path
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Read the settings file from disk.

        Returns:
            Parsed settings dict, or empty dict if file absent or unreadable.
        """
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self) -> None:
        """Write current settings to disk atomically.

        Uses a tmp-then-rename pattern to prevent partial-write corruption.
        Creates parent directories as needed.
        """
        parent = os.path.dirname(os.path.abspath(self._path))
        os.makedirs(parent, exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self._path)

    # ── Plugin config helpers ─────────────────────────────────────────────────

    def get_all_plugin_configs(self) -> dict[str, dict[str, Any]]:
        """Return stored configs for all plugins.

        Returns:
            Dict of plugin_id → {field_key: value}. Empty if none saved.
        """
        plugins = self._data.get("plugins", {})
        if not isinstance(plugins, dict):
            return {}
        return {k: dict(v) for k, v in plugins.items() if isinstance(v, dict)}

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any]:
        """Return all stored settings for a single plugin.

        Args:
            plugin_id: Plugin identifier (e.g. ``"lastfm"``).

        Returns:
            Dict of field_key → value. Empty dict if no settings saved yet.
        """
        return self.get_all_plugin_configs().get(plugin_id, {})

    def set_plugin_value(self, plugin_id: str, field_key: str, value: str) -> None:
        """Persist a single plugin config value and write to disk.

        Args:
            plugin_id: Plugin identifier (e.g. ``"lastfm"``).
            field_key: Config field key (e.g. ``"data_path"``).
            value: String value to store.
        """
        plugins: dict[str, Any] = self._data.setdefault("plugins", {})
        plugin_cfg: dict[str, str] = plugins.setdefault(plugin_id, {})
        plugin_cfg[field_key] = value
        self._save()

    # ── Fetch history helpers ─────────────────────────────────────────────────

    _MAX_HISTORY = 20

    def add_fetch_history(
        self, plugin_id: str, timestamp: str, record_count: int, file_path: str
    ) -> None:
        """Prepend a fetch record to the plugin's history list.

        Keeps at most ``_MAX_HISTORY`` entries, newest first.

        Args:
            plugin_id: Plugin identifier (e.g. ``"lastfm"``).
            timestamp: ISO-format timestamp string for the fetch.
            record_count: Number of records in the fetched file.
            file_path: Path where the versioned snapshot was saved.
        """
        plugins: dict[str, Any] = self._data.setdefault("plugins", {})
        plugin_cfg: dict[str, Any] = plugins.setdefault(plugin_id, {})
        history: list[dict[str, Any]] = plugin_cfg.setdefault("fetch_history", [])
        entry = {"timestamp": timestamp, "record_count": record_count, "file_path": file_path}
        history.insert(0, entry)
        plugin_cfg["fetch_history"] = history[: self._MAX_HISTORY]
        self._save()

    def get_fetch_history(self, plugin_id: str) -> list[dict[str, Any]]:
        """Return the fetch history list for a plugin, newest first.

        Args:
            plugin_id: Plugin identifier (e.g. ``"lastfm"``).

        Returns:
            List of ``{timestamp, record_count, file_path}`` dicts. Empty if none.
        """
        raw = self.get_plugin_config(plugin_id).get("fetch_history", [])
        return raw if isinstance(raw, list) else []

    # ── General key/value helpers ─────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return a top-level setting value.

        Args:
            key: Setting key.
            default: Value to return if key is absent.

        Returns:
            The stored value, or ``default`` if the key is not present.
        """
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Write a top-level setting value and persist to disk.

        Args:
            key: Setting key.
            value: Value to store (must be JSON-serializable).
        """
        self._data[key] = value
        self._save()
