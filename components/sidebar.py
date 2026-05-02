"""Shared sidebar component — shows plugin health badges and loads data.

Plugin configuration and fetch controls have moved to the Data Sources page
(``pages/data_sources.py``). The sidebar now shows a compact health indicator
per plugin and handles data loading into ``st.session_state["df"]``.
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
    settings,
)
from plugins.sources import REGISTRY, load_builtin_plugins

_HEALTH_BADGES: dict[str, str] = {
    "healthy": "✅",
    "stale": "⚠️",
    "error": "❌",
    "unconfigured": "◻️",
}


def render_sidebar() -> None:
    """Render the sidebar health indicators and populate ``st.session_state['df']``.

    Loads persisted path config from disk, renders a one-line health badge per
    source plugin, then loads Last.fm + Swarm data (with local caching), applies
    location assumptions, and stores the resulting DataFrame under
    ``st.session_state['df']`` so every page can access it.
    """
    load_builtin_plugins()
    load_config_into_session_state()

    st.sidebar.markdown(
        '<p class="autobio-section-header">Data Sources</p>', unsafe_allow_html=True
    )

    configs: dict[str, dict[str, str]] = {}

    for plugin_id, plugin_cls in REGISTRY.items():
        plugin = plugin_cls()
        fields = plugin.get_config_fields()
        config = get_plugin_config_from_session(plugin_id, fields)
        configs[plugin_id] = config

        history = settings.get_fetch_history(plugin_id)
        health = plugin.get_health_status(config, history)
        badge = _HEALTH_BADGES.get(health["status"], "◻️")
        st.sidebar.markdown(f"{plugin.DISPLAY_NAME}&nbsp;&nbsp;{badge}")

    # --- Data loading ---------------------------------------------------------
    lastfm_cfg = configs.get("lastfm", {})
    swarm_cfg = configs.get("swarm", {})
    assumptions_cfg = configs.get("assumptions", {})

    file_path: str = lastfm_cfg.get("data_path", "")
    swarm_dir: str = swarm_cfg.get("swarm_dir", "")
    assumptions_path: str = assumptions_cfg.get("assumptions_file", "default_assumptions.json")

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
