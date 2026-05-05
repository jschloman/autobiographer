"""Shared sidebar component — silently loads data and provides the global date filter.

Plugin health badges and cache management have moved to the Data Sources pages.
This module's only responsibilities are:
  1. Hydrate session state from disk.
  2. Load and process the active dataset into ``st.session_state["df"]``.
  3. Expose the global date-range filter.
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


def render_sidebar() -> None:
    """Hydrate config, load the dataset, and render the global date filter.

    Populates ``st.session_state["df"]`` with the processed DataFrame (or None
    if no Last.fm file is configured).  Stores ``st.session_state["_cache_status"]``
    as ``"hit"`` or ``"miss"`` for the Cache Management tab on the Data Sources page.
    """
    load_builtin_plugins()
    load_config_into_session_state()

    configs: dict[str, dict[str, str]] = {}
    for plugin_id, plugin_cls in REGISTRY.items():
        plugin = plugin_cls()
        fields = plugin.get_config_fields()
        configs[plugin_id] = get_plugin_config_from_session(plugin_id, fields)

    lastfm_cfg = configs.get("lastfm", {})
    swarm_cfg = configs.get("swarm", {})
    assumptions_cfg = configs.get("assumptions", {})

    file_path: str = lastfm_cfg.get("data_path", "")
    swarm_dir: str = swarm_cfg.get("swarm_dir", "")
    assumptions_path: str = assumptions_cfg.get("assumptions_file", "default_assumptions.json")

    if not file_path or not os.path.exists(file_path):
        st.session_state["df"] = None
        st.session_state["swarm_df"] = None
        return

    assumptions = load_assumptions(assumptions_path)

    swarm_df = (
        load_swarm_data(swarm_dir) if swarm_dir and os.path.exists(swarm_dir) else pd.DataFrame()
    )

    cache_key = get_cache_key(file_path, swarm_dir, assumptions_path)
    df: pd.DataFrame | None = get_cached_data(cache_key)

    if df is None:
        st.session_state["_cache_status"] = "miss"
        df = load_listening_data(file_path)
        if df is not None:
            with st.spinner("Adjusting timezones and geocoding…"):
                df = apply_swarm_offsets(df, swarm_df, assumptions)
            save_to_cache(df, cache_key)
    else:
        st.session_state["_cache_status"] = "hit"

    st.session_state["swarm_df"] = swarm_df if not swarm_df.empty else None

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
