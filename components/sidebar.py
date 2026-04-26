"""Shared sidebar component for data source configuration and loading.

Iterates over the registered source plugins, renders a file-path selector for
each declared config field, then loads the active DataFrame into
``st.session_state["df"]`` so every page can access it without reloading.

Path selections are persisted to ``local_settings.json`` (gitignored) via
:class:`~core.local_settings.LocalSettings` so they survive application
restarts and do not need to be re-entered each session.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import pandas as pd
import streamlit as st

from analysis_utils import (
    apply_swarm_offsets,
    get_cache_key,
    get_cached_data,
    load_assumptions,
    load_listening_data,
    load_swarm_data,
    save_to_cache,
)
from core.local_settings import LocalSettings
from plugins.sources import REGISTRY, load_builtin_plugins

# Detect tkinter availability at import time so the browse button is only
# shown in environments where a display is available (e.g. not in CI).
try:
    import tkinter as _tk  # noqa: F401

    _TKINTER_AVAILABLE = True
except Exception:
    _TKINTER_AVAILABLE = False

_CONFIG_LOADED_KEY = "_autobio_config_loaded"

# Module-level singleton — reads local_settings.json once on first import.
_settings = LocalSettings()


def _load_config_into_session_state() -> None:
    """Hydrate session state from local_settings.json (once per browser session).

    Only runs on the first script execution in a new browser session. Existing
    session state keys are not overwritten so that in-session changes take
    precedence over the saved config.
    """
    if st.session_state.get(_CONFIG_LOADED_KEY):
        return
    for plugin_id, plugin_cfg in _settings.get_all_plugin_configs().items():
        for field_key, value in plugin_cfg.items():
            session_key = f"{plugin_id}_{field_key}"
            if session_key not in st.session_state:
                st.session_state[session_key] = value
    st.session_state[_CONFIG_LOADED_KEY] = True


def _path_input(
    label: str,
    session_key: str,
    on_persist: Callable[[str], None],
    default: str = "",
    file_types: list[tuple[str, str]] | None = None,
    is_dir: bool = False,
) -> str:
    """Render a path text input with a native browse button.

    The browse button opens a tkinter file or directory dialog on the local
    machine. This is valid because the Streamlit server is localhost for this
    application.

    Streamlit forbids writing to a session state key that is already bound to a
    widget in the same script run. We work around this with a pending-key
    pattern: the browse dialog stores its result under ``_pending_{session_key}``
    and triggers a rerun. At the top of the *next* run this value is transferred
    to the widget key before the widget is instantiated, which is always allowed.

    Any path selected via the dialog or typed into the text input is passed to
    ``on_persist`` so it can be saved to ``local_settings.json``.

    Args:
        label: Display label for the text input.
        session_key: Session state key used to persist the path value.
        on_persist: Callback invoked with the new path string whenever the value
            changes; responsible for writing to ``local_settings.json``.
        default: Default path value when neither session state nor the saved
            config has an entry for this key.
        file_types: List of (description, glob pattern) tuples for the file
            dialog filter, e.g. ``[("CSV files", "*.csv")]``. Ignored when
            ``is_dir`` is True.
        is_dir: If True, open a directory picker; otherwise open a file picker.

    Returns:
        The current path string from session state.
    """
    pending_key = f"_pending_{session_key}"

    # Transfer any pending value from a previous browse action BEFORE the
    # widget is instantiated so Streamlit allows the assignment.
    if pending_key in st.session_state:
        value = str(st.session_state.pop(pending_key))
        st.session_state[session_key] = value
        on_persist(value)
    elif session_key not in st.session_state:
        st.session_state[session_key] = default

    def _on_change() -> None:
        on_persist(str(st.session_state.get(session_key, "")))

    if _TKINTER_AVAILABLE:
        # Use st.columns / st.text_input (not st.sidebar.*) so widgets render
        # inside whatever container is currently active — critically, inside the
        # expander when called from _render_plugin_config.
        col1, col2 = st.columns([4, 1])
        col1.text_input(label, key=session_key, on_change=_on_change)

        if col2.button("...", key=f"browse_{session_key}", help="Browse for path"):
            import threading

            # Streamlit's script runner executes on a background thread.
            # Tkinter requires its event loop to be owned by the thread that
            # creates the Tk() root, and on Windows it cannot share the main
            # thread's message loop. Spawning a dedicated thread for each
            # dialog call avoids the "main thread is not in main loop" error.
            _result: list[str] = []

            def _open_dialog() -> None:
                import tkinter as tk
                from tkinter import filedialog

                root = tk.Tk()
                root.withdraw()
                try:
                    root.wm_attributes("-topmost", 1)
                except Exception:  # noqa: S110 — not available on all platforms
                    pass
                if is_dir:
                    path = filedialog.askdirectory(title=label)
                else:
                    path = filedialog.askopenfilename(
                        title=label,
                        filetypes=file_types or [("All files", "*.*")],
                    )
                root.destroy()
                if path:
                    _result.append(path)

            t = threading.Thread(target=_open_dialog, daemon=True)
            t.start()
            t.join()

            # Store under pending_key, not session_key — the widget bound to
            # session_key has already been instantiated this run.
            if _result:
                st.session_state[pending_key] = _result[0]
                st.rerun()
    else:
        st.text_input(label, key=session_key, on_change=_on_change)

    return str(st.session_state.get(session_key, default))


def _render_plugin_config(plugin_id: str, fields: list[dict[str, Any]]) -> dict[str, str]:
    """Render sidebar config fields for one plugin and return collected values.

    Args:
        plugin_id: The plugin's PLUGIN_ID, used to namespace session state keys.
        fields: Field descriptor list from ``plugin.get_config_fields()``.

    Returns:
        Dict mapping each field key to its current path value.
    """
    config: dict[str, str] = {}
    for field in fields:
        env_key = f"AUTOBIO_{plugin_id.upper()}_{field['key'].upper()}"
        default = os.getenv(env_key, "")
        is_dir = field.get("type") == "dir_path"
        field_key = field["key"]

        def _make_persist(fk: str = field_key) -> Callable[[str], None]:
            def _persist(path: str) -> None:
                _settings.set_plugin_value(plugin_id, fk, path)

            return _persist

        value = _path_input(
            label=field["label"],
            session_key=f"{plugin_id}_{field['key']}",
            on_persist=_make_persist(),
            default=default,
            file_types=field.get("file_types"),
            is_dir=is_dir,
        )
        config[field["key"]] = value
    return config


def render_sidebar() -> None:
    """Render the data-source sidebar and populate ``st.session_state['df']``.

    Loads persisted path config from disk, loads the plugin registry, renders a
    labelled file-path selector for every config field declared by each plugin,
    then loads Last.fm + Swarm data (with local caching), applies location
    assumptions, and stores the resulting DataFrame under
    ``st.session_state['df']``.
    """
    load_builtin_plugins()
    _load_config_into_session_state()

    st.sidebar.markdown(
        '<p class="autobio-section-header">Data Sources</p>', unsafe_allow_html=True
    )

    configs: dict[str, dict[str, str]] = {}
    for plugin_id, plugin_cls in REGISTRY.items():
        plugin = plugin_cls()
        fields = plugin.get_config_fields()

        # Auto-expand the section when the primary path is not yet configured
        # so first-time users immediately see they need to fill it in.
        primary_key = f"{plugin_id}_{fields[0]['key']}" if fields else ""
        is_configured = bool(st.session_state.get(primary_key, "").strip())

        with st.sidebar.expander(
            f"{plugin.ICON}  {plugin.DISPLAY_NAME}", expanded=not is_configured
        ):
            configs[plugin_id] = _render_plugin_config(plugin_id, fields)

    # --- Data loading ---------------------------------------------------------
    lastfm_cfg = configs.get("lastfm", {})
    swarm_cfg = configs.get("swarm", {})

    file_path: str = lastfm_cfg.get("data_path", "")
    swarm_dir: str = swarm_cfg.get("swarm_dir", "")
    assumptions_path: str = swarm_cfg.get("assumptions_file", "default_assumptions.json")

    if not file_path or not os.path.exists(file_path):
        if file_path:
            st.sidebar.error(f"File not found: '{file_path}'")
        st.session_state["df"] = None
        return

    assumptions = load_assumptions(assumptions_path)

    st.sidebar.markdown(
        '<p class="autobio-section-header">Cache Management</p>', unsafe_allow_html=True
    )
    cache_key = get_cache_key(file_path, swarm_dir, assumptions_path)
    df: pd.DataFrame | None = get_cached_data(cache_key)

    if df is None:
        df = load_listening_data(file_path)
        if df is not None:
            with st.spinner("Adjusting timezones and geocoding..."):
                swarm_df = (
                    load_swarm_data(swarm_dir)
                    if swarm_dir and os.path.exists(swarm_dir)
                    else pd.DataFrame()
                )
                df = apply_swarm_offsets(df, swarm_df, assumptions)

                if not swarm_df.empty:
                    st.sidebar.success(f"Applied offsets from {len(swarm_df)} checkins.")
                elif os.path.exists(assumptions_path):
                    st.sidebar.info("Applied location assumptions from file.")
                else:
                    st.sidebar.warning("No Swarm data or assumptions found; using default.")

            save_to_cache(df, cache_key)
            st.sidebar.info("Data processed and cached locally.")
    else:
        st.sidebar.success("Loaded from local cache.")

    if st.sidebar.button("Clear Local Cache"):
        cache_dir = "data/cache"
        if os.path.exists(cache_dir):
            import shutil

            shutil.rmtree(cache_dir)
            st.sidebar.success("Cache cleared!")
            st.rerun()

    if df is not None:
        st.sidebar.markdown(
            '<p class="autobio-section-header">Global Filters</p>', unsafe_allow_html=True
        )
        min_date = df["date_text"].min().date()
        max_date = df["date_text"].max().date()
        date_range = st.sidebar.date_input("Filter by Date Range", [min_date, max_date])

        if len(date_range) == 2:
            df = df[
                (df["date_text"].dt.date >= date_range[0])
                & (df["date_text"].dt.date <= date_range[1])
            ]

    st.session_state["df"] = df
