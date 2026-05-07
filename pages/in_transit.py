"""In Transit page — airport and travel hub listening patterns (Issue #61).

Compares listening behaviour on days with airport/transit Foursquare check-ins
("travel days") against all other days ("home days").

Metrics surfaced:
- Top-20 transit artists
- Average plays per travel day vs. non-travel day
- New artist discovery rate on transit vs. home days
- Common listening hours during transit
- Longest transit session (track count)
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st
from pandas import DataFrame

from analysis_utils import (
    get_avg_plays_per_day,
    get_longest_transit_session,
    get_new_artist_discovery_rate,
    get_top_entities,
    get_transit_days,
    get_transit_listening_hours,
    split_transit_listens,
)
from components.theme import ACCENT_INDIGO, AMBER, COLORWAY, TEAL, apply_dark_theme, card_container


def render_in_transit() -> None:
    """Render the In Transit page.

    Reads ``st.session_state['df']`` (Last.fm listens) and
    ``st.session_state['swarm_df']`` (Foursquare/Swarm check-ins).
    Shows an informative empty state when either dataset is absent.
    """
    st.header("In Transit")
    st.caption(
        "Listening patterns on days with airport or transit hub check-ins versus all other days."
    )

    listens_df: DataFrame | None = st.session_state.get("df")
    swarm_df: DataFrame | None = st.session_state.get("swarm_df")

    # ── Guard: require both datasets ─────────────────────────────────────────
    if listens_df is None or listens_df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    if swarm_df is None or swarm_df.empty:
        st.info(
            "No Foursquare/Swarm data loaded. "
            "Configure the Swarm export directory in the sidebar to enable transit analysis."
        )
        return

    # ── Identify transit days ────────────────────────────────────────────────
    transit_days = get_transit_days(swarm_df)

    if not transit_days:
        st.warning(
            "No transit check-ins found (Airport, Train Station, Transit, etc.). "
            "Make sure your Swarm export includes venue category data."
        )
        return

    transit_df, home_df = split_transit_listens(listens_df, transit_days)

    if transit_df.empty:
        st.info(
            f"Found {len(transit_days)} transit day(s) in Swarm data "
            "but no Last.fm listens overlap with those days."
        )
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    n_transit_days = len(transit_days)
    avg_transit = get_avg_plays_per_day(transit_df)
    avg_home = get_avg_plays_per_day(home_df)
    transit_discoveries, transit_rate = get_new_artist_discovery_rate(transit_df, listens_df)
    _home_discoveries, home_rate = get_new_artist_discovery_rate(home_df, listens_df)
    longest_session = get_longest_transit_session(transit_df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        with card_container():
            st.metric("Transit Days", n_transit_days)
    with col2:
        delta_pct = round((avg_transit - avg_home) / avg_home * 100, 1) if avg_home else None
        delta_str = f"{delta_pct:+.1f}% vs home" if delta_pct is not None else None
        with card_container():
            st.metric(
                "Avg Plays / Transit Day",
                f"{avg_transit:.1f}",
                delta=delta_str,
            )
    with col3:
        with card_container():
            st.metric(
                "New Artist Discovery Rate",
                f"{transit_rate:.0%}",
                delta=(
                    f"{transit_rate - home_rate:+.0%} vs home" if home_rate is not None else None
                ),
            )
    with col4:
        with card_container():
            st.metric("Longest Transit Session", f"{longest_session} tracks")

    st.markdown("---")

    # ── Top transit artists ───────────────────────────────────────────────────
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Top 20 Transit Artists")
        top_transit = get_top_entities(transit_df, entity="artist", limit=20)
        if not top_transit.empty:
            fig_artists = px.bar(
                top_transit,
                x="Plays",
                y="artist",
                orientation="h",
                title="Most played artists on transit days",
                color_discrete_sequence=[ACCENT_INDIGO],
            )
            fig_artists.update_layout(yaxis={"categoryorder": "total ascending"})
            apply_dark_theme(fig_artists)
            st.plotly_chart(fig_artists, width="stretch")
        else:
            st.info("No artist data available for transit days.")

    # ── Plays per day comparison bar ──────────────────────────────────────────
    with col_right:
        st.subheader("Avg Plays per Day")
        comparison_data = {
            "Day Type": ["Transit Days", "Home Days"],
            "Avg Plays": [avg_transit, avg_home],
        }
        import pandas as pd

        fig_cmp = px.bar(
            pd.DataFrame(comparison_data),
            x="Day Type",
            y="Avg Plays",
            title="Average plays: transit vs. home",
            color="Day Type",
            color_discrete_map={"Transit Days": TEAL, "Home Days": AMBER},
        )
        apply_dark_theme(fig_cmp)
        fig_cmp.update_layout(showlegend=False)
        st.plotly_chart(fig_cmp, width="stretch")

    st.markdown("---")

    # ── Hourly listening distribution during transit ───────────────────────────
    st.subheader("Listening Hours During Transit")
    hourly = get_transit_listening_hours(transit_df)
    if not hourly.empty:
        fig_hours = px.bar(
            hourly,
            x="hour",
            y="Plays",
            title="Play count by hour of day (transit days only)",
            color_discrete_sequence=COLORWAY,
        )
        fig_hours.update_layout(xaxis={"dtick": 1, "title": "Hour of Day (local)"})
        apply_dark_theme(fig_hours)
        st.plotly_chart(fig_hours, width="stretch")

    st.markdown("---")

    # ── Discovery rate comparison ────────────────────────────────────────────
    st.subheader("New Artist Discovery")

    disc_col1, disc_col2 = st.columns(2)
    with disc_col1:
        st.markdown(
            f"**{transit_discoveries}** new artists were first heard on a transit day "
            f"({transit_rate:.0%} of transit-day artists)."
        )
    with disc_col2:
        fig_disc = px.bar(
            x=["Transit Days", "Home Days"],
            y=[transit_rate * 100, home_rate * 100],
            labels={"x": "Day Type", "y": "Discovery Rate (%)"},
            title="New artist discovery rate (%)",
            color=["Transit Days", "Home Days"],
            color_discrete_map={"Transit Days": TEAL, "Home Days": AMBER},
        )
        apply_dark_theme(fig_disc)
        fig_disc.update_layout(showlegend=False)
        st.plotly_chart(fig_disc, width="stretch")

    st.markdown("---")

    # ── Raw data expander ────────────────────────────────────────────────────
    with st.expander("Transit day listens (raw data)"):
        candidate_cols = ["date_text", "artist", "track", "album"]
        display_cols = [c for c in candidate_cols if c in transit_df.columns]
        st.dataframe(
            transit_df[display_cols].sort_values("date_text", ascending=False),
            hide_index=True,
        )
