"""Shared sidebar component for data source configuration and loading.

Renders the data-source config inputs and loads the active DataFrame into
``st.session_state["df"]`` so every page can access it without reloading.
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


def render_sidebar() -> None:
    """Render the data-source sidebar and populate ``st.session_state['df']``.

    Reads config inputs, loads Last.fm + Swarm data (with local caching),
    applies location assumptions, and stores the resulting DataFrame under
    ``st.session_state['df']``. Pages read from session state rather than
    reloading data on every navigation event.
    """
    st.sidebar.header("Data Sources")

    default_data_dir = os.getenv("AUTOBIO_LASTFM_DATA_DIR", "data")
    data_dir = st.sidebar.text_input("Last.fm Data Directory", default_data_dir)

    if not os.path.exists(data_dir):
        st.sidebar.error(f"Directory '{data_dir}' not found.")
        st.session_state["df"] = None
        return

    files = [f for f in os.listdir(data_dir) if f.endswith("_tracks.csv")]
    if not files:
        st.sidebar.warning(f"No tracking data found in {data_dir}.")
        st.session_state["df"] = None
        return

    selected_file = st.sidebar.selectbox("Select a data file", files)
    file_path = os.path.join(data_dir, selected_file)

    default_swarm_dir = os.getenv("AUTOBIO_SWARM_DIR", "")
    swarm_dir = st.sidebar.text_input("Swarm Data Directory (Optional)", default_swarm_dir)

    default_assumptions_path = os.getenv("AUTOBIO_ASSUMPTIONS_FILE", "default_assumptions.json")
    assumptions_path = st.sidebar.text_input(
        "Location Assumptions File (JSON)", default_assumptions_path
    )
    assumptions = load_assumptions(assumptions_path)

    st.sidebar.header("Cache Management")
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
                    st.sidebar.warning("No Swarm or assumptions found; using Reykjavik default.")

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
        st.sidebar.header("Global Filters")
        min_date = df["date_text"].min().date()
        max_date = df["date_text"].max().date()
        date_range = st.sidebar.date_input("Filter by Date Range", [min_date, max_date])

        if len(date_range) == 2:
            df = df[
                (df["date_text"].dt.date >= date_range[0])
                & (df["date_text"].dt.date <= date_range[1])
            ]

    st.session_state["df"] = df
