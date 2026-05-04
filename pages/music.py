"""Music page — date-ranged listening report mirroring Last.fm's weekly report."""

from __future__ import annotations

import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis_utils import (
    get_artist_monthly_ranks,
    get_cumulative_plays,
    get_genre_weekly,
    get_hourly_distribution,
    get_listening_intensity,
    get_top_entities,
)
from components.theme import (
    ACCENT_INDIGO,
    AMBER,
    COLORWAY,
    LIFTED_BG,
    TEAL,
    apply_dark_theme,
    card_container,
)


def _filter_by_date(df: pd.DataFrame, start: datetime.date, end: datetime.date) -> pd.DataFrame:
    """Return rows where date_text falls within [start, end] inclusive."""
    mask = (df["date_text"].dt.date >= start) & (df["date_text"].dt.date <= end)
    return df[mask]


def _prev_period(start: datetime.date, end: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Return the immediately preceding period of identical duration."""
    delta = (end - start) + datetime.timedelta(days=1)
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - delta + datetime.timedelta(days=1)
    return prev_start, prev_end


def _pct_delta(current: float, previous: float) -> float | None:
    """Return percentage change as a float, or None when previous is zero."""
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def render_date_range(df: pd.DataFrame) -> tuple[datetime.date, datetime.date]:
    """Render start/end date pickers and return the selected range.

    Defaults to the most recent 7 days of data. Uses explicit session-state
    keys so that the user's selection survives Streamlit reruns without being
    reset to the default value on every script execution.

    Args:
        df: Full listening history DataFrame with a ``date_text`` column.

    Returns:
        Tuple of (start_date, end_date).
    """
    min_date: datetime.date = df["date_text"].dt.date.min()
    max_date: datetime.date = df["date_text"].dt.date.max()

    # Seed session state only on the first render (or when the dataset changes
    # and the stored dates fall outside the new valid range).
    stored_from: datetime.date | None = st.session_state.get("music_date_from")
    if stored_from is None or not (min_date <= stored_from <= max_date):
        st.session_state["music_date_from"] = max(min_date, max_date - datetime.timedelta(days=6))

    stored_to: datetime.date | None = st.session_state.get("music_date_to")
    if stored_to is None or not (min_date <= stored_to <= max_date):
        st.session_state["music_date_to"] = max_date

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("From", key="music_date_from", min_value=min_date, max_value=max_date)
    with col2:
        end = st.date_input("To", key="music_date_to", min_value=min_date, max_value=max_date)

    if start > end:
        st.error("Start date must be on or before the end date.")
        st.stop()

    return start, end


def render_quick_facts(filtered: pd.DataFrame, prev: pd.DataFrame) -> None:
    """Render four summary metrics comparing the selected period to the previous one.

    Args:
        filtered: Rows within the selected date range.
        prev: Rows within the preceding period of equal length.
    """
    n = len(filtered)
    prev_n = len(prev)

    days = (
        (filtered["date_text"].dt.date.max() - filtered["date_text"].dt.date.min()).days + 1
        if not filtered.empty
        else 1
    )
    avg_daily = n / days
    hours = n * 3.5 / 60  # ~3.5 min average track length

    most_active_label = "—"
    most_active_count = 0
    if not filtered.empty:
        daily_counts = filtered.groupby(filtered["date_text"].dt.date).size()
        peak_date = daily_counts.idxmax()
        most_active_count = int(daily_counts[peak_date])
        most_active_label = f"{most_active_count} on {peak_date.strftime('%d %b')}"

    prev_days = (
        (prev["date_text"].dt.date.max() - prev["date_text"].dt.date.min()).days + 1
        if not prev.empty
        else 1
    )
    prev_avg = len(prev) / prev_days if not prev.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Scrobbles", f"{n:,}", delta=_pct_delta(n, prev_n))
    with c2:
        st.metric("Listening Time", f"{hours:.0f}h")
    with c3:
        st.metric("Avg / Day", f"{avg_daily:.0f}", delta=_pct_delta(avg_daily, prev_avg))
    with c4:
        st.metric("Most Active Day", most_active_label)


def render_entity_columns(filtered: pd.DataFrame, full_df: pd.DataFrame) -> None:
    """Render Artists / Albums / Tracks side-by-side with counts and top-5 lists.

    Marks entities as "new" if they first appear within the selected period.

    Args:
        filtered: Rows within the selected date range.
        full_df: Complete listening history for computing new-entity rates.
    """
    period_start = filtered["date_text"].min() if not filtered.empty else None
    entities = [
        ("artist", "Artists"),
        ("album", "Albums"),
        ("track", "Tracks"),
    ]

    cols = st.columns(3)
    for col, (entity, label) in zip(cols, entities):
        with col:
            st.subheader(label)
            if entity not in filtered.columns:
                st.caption("No data")
                continue

            unique_count = int(filtered[entity].nunique())
            new_pct_str = "—"
            if period_start is not None and entity in full_df.columns:
                prior = set(full_df[full_df["date_text"] < period_start][entity].dropna())
                period_set = set(filtered[entity].dropna())
                new_count = len(period_set - prior)
                if unique_count:
                    new_pct_str = f"{new_count / unique_count * 100:.0f}% new"

            st.metric(f"Unique {label}", f"{unique_count:,}", delta=new_pct_str)

            top = get_top_entities(filtered, entity, limit=5)
            if not top.empty:
                st.markdown("---")
                for rank, (_, row) in enumerate(top.iterrows(), start=1):
                    name = str(row[entity])
                    plays = int(row["Plays"])
                    if entity == "track" and "artist" in filtered.columns:
                        artist = filtered[filtered["track"] == name]["artist"].mode().iloc[0]
                        label_str = f'{artist} — "{name}"'
                    else:
                        label_str = name
                    st.markdown(f"{rank}. **{label_str}** &nbsp; `{plays}`")


def render_daily_chart(filtered: pd.DataFrame) -> None:
    """Render a bar chart of daily scrobble counts.

    Args:
        filtered: Rows within the selected date range.
    """
    intensity = get_listening_intensity(filtered, "D")
    if intensity.empty:
        return
    fig = px.bar(intensity, x="date", y="Plays", title="Daily Scrobbles")
    fig.update_traces(marker_color=TEAL)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_listening_clock(filtered: pd.DataFrame) -> None:
    """Render hourly scrobble distribution as a bar chart.

    Args:
        filtered: Rows within the selected date range.
    """
    hourly = get_hourly_distribution(filtered)
    if hourly.empty:
        return

    all_hours = pd.DataFrame({"hour": range(24)})
    hourly = all_hours.merge(hourly, on="hour", how="left").fillna(0)
    hourly["Plays"] = hourly["Plays"].astype(int)

    peak = hourly.loc[hourly["Plays"].idxmax()]
    peak_label = f"{int(peak['hour']):02d}:00 ({int(peak['Plays'])} plays)"

    fig = px.bar(hourly, x="hour", y="Plays", title=f"Listening Clock · Peak: {peak_label}")
    fig.update_traces(marker_color=AMBER)
    fig.update_xaxes(tickmode="linear", tick0=0, dtick=2)
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_plays_growth(filtered: pd.DataFrame) -> None:
    """Render cumulative plays area chart for the selected period.

    Args:
        filtered: Rows within the selected date range.
    """
    cumulative = get_cumulative_plays(filtered)
    if cumulative.empty:
        return
    fig = px.area(cumulative, x="date", y="CumulativePlays", title="Plays Growth")
    fig.update_traces(line_color=TEAL, fillcolor="rgba(0,200,200,0.15)")
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_top_charts(df: pd.DataFrame) -> None:
    """Render top entity charts with rank badges and a type toggle.

    The #1 entry is highlighted in indigo; remaining bars use the lifted
    background colour.  A scrobble count label appears outside each bar and
    a rank badge is embedded in the y-axis label.

    Args:
        df: Loaded listening history DataFrame.
    """
    st.header("Top Charts")
    entity_type = st.radio("Select chart type", ["artist", "album", "track"], horizontal=True)
    limit = st.slider(f"Top {entity_type.capitalize()}s to show", 5, 50, 10)
    top_data = get_top_entities(df, entity_type, limit=limit)
    col1, col2 = st.columns([2, 1])
    with col1:
        plays = top_data["Plays"].tolist()
        ranked_labels = [f"#{r}  {n}" for r, n in enumerate(top_data[entity_type], 1)]
        colors = [ACCENT_INDIGO] + [LIFTED_BG] * (len(top_data) - 1)

        fig_bar = go.Figure(
            go.Bar(
                x=plays,
                y=ranked_labels,
                orientation="h",
                marker_color=colors,
                text=[f"{p:,}" for p in plays],
                textposition="outside",
                cliponaxis=False,
            )
        )
        fig_bar.update_layout(
            title=f"Top {limit} {entity_type.capitalize()}s",
            yaxis={"categoryorder": "total ascending"},
            margin={"r": 80},
        )
        apply_dark_theme(fig_bar)
        st.plotly_chart(fig_bar, width="stretch")
    with col2:
        fig_pie = px.pie(
            top_data.head(10), values="Plays", names=entity_type, title="Market Share (Top 10)"
        )
        apply_dark_theme(fig_pie)
        st.plotly_chart(fig_pie, width="stretch")


def render_streamgraph(df: pd.DataFrame) -> None:
    """Render a stacked-area streamgraph of top-artist scrobble volume by week.

    Uses artist as the category dimension because Last.fm exports do not
    include genre tags.

    Args:
        df: Listening history DataFrame (already filtered to the selected date range).
    """
    weekly = get_genre_weekly(df)
    if weekly.empty:
        return
    fig = px.area(
        weekly,
        x="date",
        y="scrobbles",
        color="genre",
        title="Artist Listening Timeline",
        color_discrete_sequence=COLORWAY,
        labels={"genre": "Artist", "scrobbles": "Scrobbles", "date": ""},
    )
    fig.update_layout(legend_title_text="Artist")
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_bump_chart(df: pd.DataFrame) -> None:
    """Render a monthly artist rank bump chart for the top 10 artists.

    Hidden when fewer than two months of data are available.

    Args:
        df: Listening history DataFrame (already filtered to the selected date range).
    """
    ranks = get_artist_monthly_ranks(df)
    if ranks.empty or ranks["month"].nunique() < 2:
        return
    fig = px.line(
        ranks,
        x="month",
        y="rank",
        color="artist",
        title="Artist Rank Over Time",
        color_discrete_sequence=COLORWAY,
        labels={"month": "", "rank": "Rank", "artist": "Artist"},
        markers=True,
    )
    fig.update_yaxes(autorange="reversed", dtick=1, title="Rank")
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")


def render_activity_over_time(df: pd.DataFrame) -> None:
    """Render listening intensity and cumulative growth charts for the given period.

    Args:
        df: Listening history DataFrame (already filtered to the selected date range).
    """
    st.subheader("Activity Over Time")
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq_label = st.selectbox("Grouping", list(freq_map.keys()))
    intensity = get_listening_intensity(df, freq_map[freq_label])
    fig = px.line(intensity, x="date", y="Plays", title=f"Plays per {freq_label}")
    apply_dark_theme(fig)
    st.plotly_chart(fig, width="stretch")

    cumulative = get_cumulative_plays(df)
    fig2 = px.area(cumulative, x="date", y="CumulativePlays", title="Total Plays")
    fig2.update_traces(line_color=TEAL, fillcolor="rgba(0,200,200,0.15)")
    apply_dark_theme(fig2)
    st.plotly_chart(fig2, width="stretch")


def render_music() -> None:
    """Render the Music page: date-ranged listening report with all-time charts.

    Reads the active DataFrame from ``st.session_state['df']``.
    Shows an empty state when no data has been loaded.
    """
    df = st.session_state.get("df")
    if df is None or df.empty:
        st.info(
            "No music data loaded yet. "
            "Configure a Last.fm source in the sidebar and select a data file."
        )
        return

    st.header("Listening Report")

    start, end = render_date_range(df)
    filtered = _filter_by_date(df, start, end)

    if filtered.empty:
        st.warning("No plays found in the selected date range.")
        return

    prev_start, prev_end = _prev_period(start, end)
    prev = _filter_by_date(df, prev_start, prev_end)

    with st.spinner("Loading charts..."):
        st.divider()
        render_quick_facts(filtered, prev)

        st.divider()
        render_entity_columns(filtered, df)

        st.divider()
        render_daily_chart(filtered)

        col1, col2 = st.columns(2)
        with col1:
            render_listening_clock(filtered)
        with col2:
            render_plays_growth(filtered)

        st.divider()
        with card_container():
            render_top_charts(filtered)

        st.divider()
        render_streamgraph(filtered)
        render_bump_chart(filtered)
        render_activity_over_time(filtered)
