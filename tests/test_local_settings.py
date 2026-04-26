"""Tests for core.local_settings.LocalSettings."""

from __future__ import annotations

import json
import os

import pytest

from core.local_settings import LocalSettings


@pytest.fixture
def settings_path(tmp_path: pytest.TempPathFactory) -> str:
    """Return a path inside tmp_path for a settings file that does not yet exist."""
    return str(tmp_path / "local_settings.json")


# ── Construction / loading ────────────────────────────────────────────────────


def test_missing_file_returns_empty(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    assert s.get_all_plugin_configs() == {}
    assert s.get("anything") is None


def test_invalid_json_returns_empty(settings_path: str) -> None:
    with open(settings_path, "w") as f:
        f.write("not json {{{")
    s = LocalSettings(settings_path)
    assert s.get_all_plugin_configs() == {}


def test_non_dict_json_returns_empty(settings_path: str) -> None:
    with open(settings_path, "w") as f:
        json.dump([1, 2, 3], f)
    s = LocalSettings(settings_path)
    assert s.get_all_plugin_configs() == {}


# ── Top-level get/set ─────────────────────────────────────────────────────────


def test_set_and_get_toplevel(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set("theme", "dark")
    assert s.get("theme") == "dark"


def test_set_persists_to_disk(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set("key", "value")
    s2 = LocalSettings(settings_path)
    assert s2.get("key") == "value"


def test_get_missing_key_returns_default(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    assert s.get("missing", "fallback") == "fallback"


# ── Plugin config ─────────────────────────────────────────────────────────────


def test_set_plugin_value_and_retrieve(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set_plugin_value("lastfm", "data_path", "/data/tracks.csv")
    cfg = s.get_plugin_config("lastfm")
    assert cfg["data_path"] == "/data/tracks.csv"


def test_set_plugin_value_persists_to_disk(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set_plugin_value("swarm", "swarm_dir", "/data/swarm/")
    s2 = LocalSettings(settings_path)
    assert s2.get_plugin_config("swarm")["swarm_dir"] == "/data/swarm/"


def test_multiple_plugins_do_not_interfere(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set_plugin_value("lastfm", "data_path", "/tracks.csv")
    s.set_plugin_value("swarm", "swarm_dir", "/swarm/")
    assert s.get_plugin_config("lastfm") == {"data_path": "/tracks.csv"}
    assert s.get_plugin_config("swarm") == {"swarm_dir": "/swarm/"}


def test_get_plugin_config_missing_returns_empty(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    assert s.get_plugin_config("nonexistent") == {}


def test_get_all_plugin_configs(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set_plugin_value("lastfm", "data_path", "/tracks.csv")
    s.set_plugin_value("swarm", "swarm_dir", "/swarm/")
    all_cfgs = s.get_all_plugin_configs()
    assert set(all_cfgs.keys()) == {"lastfm", "swarm"}


def test_update_existing_plugin_value(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set_plugin_value("lastfm", "data_path", "/old.csv")
    s.set_plugin_value("lastfm", "data_path", "/new.csv")
    assert s.get_plugin_config("lastfm")["data_path"] == "/new.csv"


# ── Atomic write ──────────────────────────────────────────────────────────────


def test_tmp_file_not_left_behind(settings_path: str) -> None:
    s = LocalSettings(settings_path)
    s.set("key", "val")
    assert not os.path.exists(settings_path + ".tmp")
    assert os.path.exists(settings_path)


# ── Robustness: non-dict plugins entry ───────────────────────────────────────


def test_malformed_plugins_value_ignored(settings_path: str) -> None:
    with open(settings_path, "w") as f:
        json.dump({"plugins": "not-a-dict"}, f)
    s = LocalSettings(settings_path)
    assert s.get_all_plugin_configs() == {}
