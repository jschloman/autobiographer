"""Shared sidebar component — config hydration, global date filter, and lazy data loading.

Data loading is deliberately deferred out of ``render_sidebar()`` and into
``ensure_data_loaded()``, which individual pages call at the top of their
render functions.  This lets the navigation shell and sidebar config appear
instantly on every page load; the slow file I/O only happens once per session
(or when the configured data paths change), with a visible progress indicator.

Session state contract
----------------------
``_current_config``  : ``(file_path, swarm_dir, assumptions_path)`` tuple —
                        written by ``render_sidebar()`` so pages can read it.
``_loaded_config``   : same tuple — written by ``ensure_data_loaded()`` to
                        mark that data was loaded for this config.
``_raw_df``          : unfiltered merged DataFrame (Last.fm + Swarm offsets).
``swarm_df``         : raw Swarm checkins DataFrame, or None.
``df``               : date-filtered view of ``_raw_df`` for the active session.
``_cache_status``    : ``"hit"`` or ``"miss"`` — shown in Data Sources page.
"""

from __future__ import annotations

import os

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
from components.plugin_config import (
    get_plugin_config_from_session,
    load_config_into_session_state,
)
from plugins.sources import REGISTRY, load_builtin_plugins

_DEFAULT_ASSUMPTIONS = "default_assumptions.json"


def _resolve_configs() -> tuple[str, str, str]:
    """Read plugin config paths from session state.

    Returns:
        ``(file_path, swarm_dir, assumptions_path)`` tuple.
    """
    configs: dict[str, dict[str, str]] = {}
    for plugin_id, plugin_cls in REGISTRY.items():
        plugin = plugin_cls()
        fields = plugin.get_config_fields()
        configs[plugin_id] = get_plugin_config_from_session(plugin_id, fields)

    file_path = configs.get("lastfm", {}).get("data_path", "")
    swarm_dir = configs.get("swarm", {}).get("swarm_dir", "")
    assumptions_path = configs.get("assumptions", {}).get("assumptions_file", _DEFAULT_ASSUMPTIONS)
    return file_path, swarm_dir, assumptions_path


def _load_data_with_progress(
    file_path: str,
    swarm_dir: str,
    assumptions_path: str,
) -> None:
    """Load all data sources with a visible progress widget; store in session state.

    Reads the Last.fm CSV, optionally reads Swarm JSONs, checks the file
    cache, and runs ``apply_swarm_offsets`` on a cache miss.  Results are
    stored in ``st.session_state`` keys defined in the module docstring.

    Args:
        file_path: Path to the Last.fm CSV file.
        swarm_dir: Directory containing Swarm JSON exports (may be empty).
        assumptions_path: Path to the assumptions JSON file.
    """
    assumptions = load_assumptions(assumptions_path)

    with st.status("Loading your data…", expanded=True) as status:
        st.write("Reading listening history…")
        raw_df = load_listening_data(file_path)

        if raw_df is None or raw_df.empty:
            status.update(label="No listening data found.", state="error", expanded=False)
            st.session_state["_raw_df"] = None
            st.session_state["swarm_df"] = None
            st.session_state["_cache_status"] = "miss"
            return

        swarm_df: pd.DataFrame
        if swarm_dir and os.path.exists(swarm_dir):
            st.write("Loading location data…")
            swarm_df = load_swarm_data(swarm_dir)
        else:
            swarm_df = pd.DataFrame()

        cache_key = get_cache_key(file_path, swarm_dir, assumptions_path)
        cached = get_cached_data(cache_key)

        if cached is not None:
            merged_df = cached
            st.session_state["_cache_status"] = "hit"
            st.write("Restored from cache.")
        else:
            st.session_state["_cache_status"] = "miss"
            st.write("Applying timezone offsets — first-time setup, may take a minute…")
            merged_df = apply_swarm_offsets(raw_df, swarm_df, assumptions)
            save_to_cache(merged_df, cache_key)

        status.update(label="Data ready.", state="complete", expanded=False)

    st.session_state["_raw_df"] = merged_df
    st.session_state["swarm_df"] = swarm_df if not swarm_df.empty else None


def ensure_data_loaded() -> None:
    """Ensure data is loaded in session state; load with progress if not.

    Call this at the top of every page function that displays data.  On the
    first visit (or after a config change) it shows a step-by-step status
    widget while reading files, then calls ``st.rerun()`` so the sidebar date
    filter can render with the correct date bounds.  On all subsequent reruns
    within the same session it is a cheap no-op.
    """
    current_config: tuple[str, str, str] = st.session_state.get(
        "_current_config", ("", "", _DEFAULT_ASSUMPTIONS)
    )
    file_path, _swarm_dir, _assumptions_path = current_config

    if not file_path or not os.path.exists(file_path):
        return

    already_loaded = (
        st.session_state.get("_loaded_config") == current_config
        and st.session_state.get("_raw_df") is not None
    )
    if already_loaded:
        return

    _load_data_with_progress(*current_config)
    st.session_state["_loaded_config"] = current_config
    st.rerun()


def render_sidebar() -> None:
    """Hydrate config, publish ``_current_config``, and render the date filter.

    Data loading is **not** performed here — pages call ``ensure_data_loaded()``
    instead.  The date filter only appears after data has been loaded into
    ``st.session_state['_raw_df']`` by a prior call to ``ensure_data_loaded()``.

    Populates:
        ``st.session_state["_current_config"]`` — the active config tuple.
        ``st.session_state["df"]`` — date-filtered view of ``_raw_df``, or None.
    """
    load_builtin_plugins()
    load_config_into_session_state()

    file_path, swarm_dir, assumptions_path = _resolve_configs()

    current_config = (file_path, swarm_dir, assumptions_path)
    st.session_state["_current_config"] = current_config

    if not file_path or not os.path.exists(file_path):
        for key in ("_raw_df", "_loaded_config"):
            st.session_state.pop(key, None)
        st.session_state["df"] = None
        st.session_state["swarm_df"] = None
        return

    raw_df: pd.DataFrame | None = st.session_state.get("_raw_df")

    if raw_df is not None and not raw_df.empty:
        st.sidebar.markdown(
            '<p class="autobio-section-header">Global Filters</p>', unsafe_allow_html=True
        )
        min_date = raw_df["date_text"].min().date()
        max_date = raw_df["date_text"].max().date()
        date_range = st.sidebar.date_input("Filter by Date Range", [min_date, max_date])

        df: pd.DataFrame = raw_df
        if len(date_range) == 2:
            df = raw_df[
                (raw_df["date_text"].dt.date >= date_range[0])
                & (raw_df["date_text"].dt.date <= date_range[1])
            ]
        st.session_state["df"] = df
    else:
        st.session_state.setdefault("df", None)
