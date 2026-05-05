"""Static HTML export for the Autobiographer dashboard.

Generates a fully self-contained HTML report from a Last.fm listening
history CSV.  Optionally enriches the report with a Foursquare/Swarm check-in
directory to add a Places tab with a world map and city/country breakdowns.
All JavaScript (plotly.js) is inlined — no external network calls are made
during rendering, preserving full data sovereignty.

Usage::

    # Listening data only
    python export_html.py data/tracks.csv

    # With Swarm check-ins (adds Places map tab)
    python export_html.py data/tracks.csv --swarm-dir data/swarm/

    # Read both paths from local_settings.json
    python export_html.py --from-settings

    # Specify an output path (default: autobiographer_report.html)
    python export_html.py data/tracks.csv --output reports/my_report.html
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date as date_type
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from analysis_utils import (
    get_artist_monthly_ranks,
    get_cumulative_plays,
    get_day_hour_heatmap,
    get_forgotten_favorites,
    get_genre_weekly,
    get_hourly_distribution,
    get_listening_intensity,
    get_listening_streaks,
    get_milestones,
    get_top_entities,
    load_listening_data,
    load_swarm_data,
)
from components.theme import COLORWAY, SEQUENTIAL_SCALE, apply_dark_theme
from core.local_settings import LocalSettings

# ── Palette constants (mirrors components/theme.py) ────────────────────────
_TEAL = "#00C8C8"
_AMBER = "#FFA014"
_BG = "#0e1117"
_PANEL_BG = "#1a1e26"
_BORDER = "#2d3142"
_TEXT = "#fafafa"
_MUTED = "#9aa0ae"


# ── HTML helpers ────────────────────────────────────────────────────────────


def _chart_div(fig: go.Figure, *, include_js: bool = False) -> str:
    """Serialise a Plotly figure to an HTML div string.

    Args:
        fig: Any Plotly Figure to serialise.
        include_js: When True, embeds the full plotly.js bundle inline.
            Set this to True for the very first chart in the document so
            the bundle is available for all subsequent ``include_js=False``
            charts.

    Returns:
        HTML string containing the chart div (and optionally the plotly.js
        script tag).
    """
    return str(
        pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs="inline" if include_js else False,
            config={"responsive": True},
        )
    )


def _table_html(df: pd.DataFrame) -> str:
    """Render a DataFrame as a styled dark HTML table.

    Args:
        df: DataFrame to render.  Empty DataFrames produce a placeholder message.

    Returns:
        HTML string for the table or an empty-state paragraph.
    """
    if df.empty:
        return "<p class='empty-msg'>No data available.</p>"

    headers = "".join(f"<th>{col}</th>" for col in df.columns)
    rows = ""
    for _, row in df.iterrows():
        cells = "".join(f"<td>{val}</td>" for val in row)
        rows += f"<tr>{cells}</tr>\n"

    return (
        f"<div class='table-wrap'>"
        f"<table><thead><tr>{headers}</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"</div>"
    )


# ── Shared HTML scaffold ────────────────────────────────────────────────────


def _html_styles() -> str:
    """Return the CSS block shared by all self-contained HTML exports."""
    return f"""
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: {_BG};
    color: {_TEXT};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 15px;
    line-height: 1.5;
  }}

  .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1.5rem; }}

  .app-header {{
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 2rem;
    border-bottom: 1px solid {_BORDER};
    padding-bottom: 1rem;
  }}
  .app-header h1 {{ font-size: 1.75rem; font-weight: 700; color: {_TEAL}; }}
  .app-header .subtitle {{ color: {_MUTED}; font-size: 0.9rem; }}

  .metrics-row {{
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 2rem;
  }}
  .metric-card {{
    background: {_PANEL_BG};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 1rem 1.5rem;
    min-width: 160px;
    flex: 1;
  }}
  .metric-card .label {{
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {_MUTED};
    margin-bottom: 0.25rem;
  }}
  .metric-card .value {{
    font-size: 1.6rem;
    font-weight: 700;
    color: {_TEAL};
  }}

  .tab-nav {{
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    border-bottom: 1px solid {_BORDER};
    padding-bottom: 0;
  }}
  .tab-btn {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: {_MUTED};
    cursor: pointer;
    font-size: 0.95rem;
    padding: 0.5rem 1rem;
    margin-bottom: -1px;
    transition: color 0.15s, border-color 0.15s;
  }}
  .tab-btn:hover {{ color: {_TEXT}; }}
  .tab-btn.active {{ color: {_TEAL}; border-bottom-color: {_TEAL}; font-weight: 600; }}

  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  .section-title {{
    font-size: 1.1rem;
    font-weight: 600;
    color: {_TEXT};
    margin: 1.5rem 0 0.75rem 0;
  }}
  .section-desc {{
    font-size: 0.85rem;
    color: {_MUTED};
    margin-bottom: 1rem;
  }}

  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }}
  @media (max-width: 800px) {{ .grid-2, .grid-3 {{ grid-template-columns: 1fr; }} }}

  .card {{
    background: {_PANEL_BG};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 1rem;
    overflow: hidden;
  }}

  .table-wrap {{ overflow-x: auto; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }}
  th {{
    text-align: left;
    padding: 0.4rem 0.75rem;
    background: rgba(0,200,200,0.08);
    color: {_TEAL};
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  td {{
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid {_BORDER};
    color: {_TEXT};
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}

  .streak-row {{ display: flex; gap: 1rem; flex-wrap: wrap; margin-top: 0.5rem; }}
  .streak-card {{
    background: {_PANEL_BG};
    border: 1px solid {_BORDER};
    border-radius: 8px;
    padding: 0.75rem 1.25rem;
  }}
  .streak-card .s-label {{ font-size: 0.75rem; color: {_MUTED}; }}
  .streak-card .s-value {{ font-size: 1.4rem; font-weight: 700; color: {_AMBER}; }}

  .empty-msg {{ color: {_MUTED}; font-style: italic; padding: 0.5rem 0; }}

  .app-footer {{
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid {_BORDER};
    color: {_MUTED};
    font-size: 0.8rem;
    text-align: center;
  }}
"""


# ── Places tab builder ──────────────────────────────────────────────────────


def _build_places_html(swarm_df: pd.DataFrame) -> str:
    """Generate the HTML content for the Places tab from Swarm check-in data.

    Produces a world scatter-geo map (zero external tiles), a top-cities bar
    chart, and a top-countries bar chart — all inlined as Plotly divs.

    Args:
        swarm_df: Swarm check-in DataFrame with at minimum ``lat``, ``lng``,
            ``city``, and ``country`` columns.

    Returns:
        HTML string for the inner content of the Places tab (no wrapper div).
    """
    geo_data = (
        swarm_df.dropna(subset=["lat", "lng"])
        .groupby(["lat", "lng", "city", "country"], as_index=False)
        .size()
        .rename(columns={"size": "Check-ins"})
    )

    fig_map = px.scatter_geo(
        geo_data,
        lat="lat",
        lon="lng",
        size="Check-ins",
        color="Check-ins",
        hover_name="city",
        hover_data={"country": True, "Check-ins": True, "lat": False, "lng": False},
        title="Where You've Been",
        color_continuous_scale=SEQUENTIAL_SCALE,
        size_max=25,
        projection="natural earth",
    )
    fig_map.update_layout(
        height=500,
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            landcolor=_PANEL_BG,
            oceancolor=_BG,
            countrycolor=_BORDER,
            subunitcolor=_BORDER,
            showland=True,
            showocean=True,
            showcountries=True,
            showlakes=False,
        ),
    )
    apply_dark_theme(fig_map)

    top_cities = (
        swarm_df.groupby("city")
        .size()
        .reset_index(name="Check-ins")
        .sort_values("Check-ins", ascending=False)
        .head(20)
    )
    fig_cities = px.bar(top_cities, x="Check-ins", y="city", orientation="h", title="Top 20 Cities")
    fig_cities.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    apply_dark_theme(fig_cities)

    top_countries = (
        swarm_df.groupby("country")
        .size()
        .reset_index(name="Check-ins")
        .sort_values("Check-ins", ascending=False)
    )
    fig_countries = px.bar(
        top_countries, x="Check-ins", y="country", orientation="h", title="Countries Visited"
    )
    fig_countries.update_layout(yaxis={"categoryorder": "total ascending"})
    apply_dark_theme(fig_countries)

    total_checkins = len(swarm_df)
    unique_cities = swarm_df["city"].nunique()
    unique_countries = swarm_df["country"].nunique()

    div_map = _chart_div(fig_map)
    div_cities = _chart_div(fig_cities)
    div_countries = _chart_div(fig_countries)

    return f"""
    <div class="metrics-row" style="margin-bottom:1.5rem">
      <div class="metric-card">
        <div class="label">Total Check-ins</div>
        <div class="value">{total_checkins:,}</div>
      </div>
      <div class="metric-card">
        <div class="label">Cities Visited</div>
        <div class="value">{unique_cities:,}</div>
      </div>
      <div class="metric-card">
        <div class="label">Countries Visited</div>
        <div class="value">{unique_countries:,}</div>
      </div>
    </div>
    <div class="card">{div_map}</div>
    <div class="grid-2" style="margin-top:1rem">
      <div class="card">{div_cities}</div>
      <div class="card">{div_countries}</div>
    </div>"""


# ── Music page export ───────────────────────────────────────────────────────


def build_music_page_html(
    filtered_df: pd.DataFrame,
    start: date_type,
    end: date_type,
    generated_at: str,
) -> str:
    """Build a self-contained HTML export of the Music listening page.

    Mirrors the charts rendered by ``pages/music.py`` for the given date range:
    quick-facts metrics, daily scrobbles, listening clock, plays growth, top
    artists/tracks/albums, streamgraph, bump chart, and monthly activity.

    Args:
        filtered_df: Listening history already filtered to ``[start, end]``.
        start: Start date of the selected range (used in the title and footer).
        end: End date of the selected range.
        generated_at: Human-readable UTC timestamp shown in the footer.

    Returns:
        A complete ``<!DOCTYPE html>`` document as a string.
    """
    if filtered_df.empty:
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Listening Report</title><style>{_html_styles()}</style></head><body>
<div class="container"><header class="app-header"><h1>Listening Report</h1>
<span class="subtitle">{start} – {end}</span></header>
<p class="empty-msg">No plays found in the selected date range.</p>
<footer class="app-footer">Generated by Autobiographer &mdash; {generated_at}</footer>
</div></body></html>"""

    n = len(filtered_df)
    days = max(1, (end - start).days + 1)
    hours = n * 3.5 / 60

    daily_counts = filtered_df.groupby(filtered_df["date_text"].dt.date).size()
    peak_date = daily_counts.idxmax()
    most_active_label = f"{int(daily_counts[peak_date])} on {peak_date.strftime('%d %b')}"

    # ── Entity columns (top-5 per entity) ────────────────────────────────────
    def _entity_col_html(entity: str, label: str) -> str:
        top5 = get_top_entities(filtered_df, entity, limit=5)
        unique_n = int(filtered_df[entity].nunique()) if entity in filtered_df.columns else 0
        items = "".join(
            f'<li style="padding:0.2rem 0;border-bottom:1px solid {_BORDER}">'
            f'<span style="color:{_TEXT}">{row[entity]}</span>'
            f'<span style="color:{_MUTED};float:right">{int(row["Plays"])}</span></li>'
            for _, row in top5.iterrows()
        )
        return (
            f'<div class="card"><div class="section-title">{label}</div>'
            f'<div style="color:{_MUTED};font-size:0.8rem;margin-bottom:0.5rem">'
            f"{unique_n:,} unique</div>"
            f'<ol style="padding-left:1.2rem;margin:0;list-style:decimal">{items}</ol></div>'
        )

    entity_cols_html = (
        f'<div class="grid-3" style="margin-bottom:1.5rem">'
        f"{_entity_col_html('artist', 'Artists')}"
        f"{_entity_col_html('album', 'Albums')}"
        f"{_entity_col_html('track', 'Tracks')}"
        f"</div>"
    )

    # Closure tracks which chart gets the inlined plotly.js bundle.
    first_chart: list[bool] = [True]

    def _chart(fig: go.Figure) -> str:
        include = first_chart[0]
        first_chart[0] = False
        return _chart_div(fig, include_js=include)

    # ── Daily scrobbles ──────────────────────────────────────────────────────
    intensity_d = get_listening_intensity(filtered_df, "D")
    div_daily = ""
    if not intensity_d.empty:
        fig = px.bar(intensity_d, x="date", y="Plays", title="Daily Scrobbles")
        fig.update_traces(marker_color=_TEAL)
        apply_dark_theme(fig)
        div_daily = f'<div class="card">{_chart(fig)}</div>'

    # ── Listening clock ──────────────────────────────────────────────────────
    hourly = get_hourly_distribution(filtered_df)
    div_clock = ""
    if not hourly.empty:
        all_hours = pd.DataFrame({"hour": range(24)})
        hourly = all_hours.merge(hourly, on="hour", how="left").fillna(0)
        hourly["Plays"] = hourly["Plays"].astype(int)
        peak = hourly.loc[hourly["Plays"].idxmax()]
        peak_label = f"{int(peak['hour']):02d}:00 ({int(peak['Plays'])} plays)"
        fig = px.bar(hourly, x="hour", y="Plays", title=f"Listening Clock · Peak: {peak_label}")
        fig.update_traces(marker_color=_AMBER)
        fig.update_xaxes(tickmode="linear", tick0=0, dtick=2)
        apply_dark_theme(fig)
        div_clock = f'<div class="card">{_chart(fig)}</div>'

    # ── Plays growth ─────────────────────────────────────────────────────────
    cumulative = get_cumulative_plays(filtered_df)
    div_growth = ""
    if not cumulative.empty:
        fig = px.area(cumulative, x="date", y="CumulativePlays", title="Plays Growth")
        fig.update_traces(line_color=_TEAL, fillcolor="rgba(0,200,200,0.15)")
        apply_dark_theme(fig)
        div_growth = f'<div class="card">{_chart(fig)}</div>'

    # ── Top artists / tracks / albums ────────────────────────────────────────
    def _top_bar(entity: str, limit: int = 20) -> str:
        top = get_top_entities(filtered_df, entity, limit=limit)
        if top.empty:
            return ""
        fig = px.bar(
            top,
            x="Plays",
            y=entity,
            orientation="h",
            title=f"Top {limit} {entity.capitalize()}s",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=600)
        apply_dark_theme(fig)
        return f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    div_artists = _top_bar("artist")
    div_tracks = _top_bar("track")
    div_albums = _top_bar("album")

    # ── Streamgraph ──────────────────────────────────────────────────────────
    weekly = get_genre_weekly(filtered_df)
    div_stream = ""
    if not weekly.empty:
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
        div_stream = f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    # ── Bump chart ───────────────────────────────────────────────────────────
    ranks = get_artist_monthly_ranks(filtered_df)
    div_bump = ""
    if not ranks.empty and ranks["month"].nunique() >= 2:
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
        div_bump = f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    # ── Monthly intensity + cumulative ───────────────────────────────────────
    intensity_m = get_listening_intensity(filtered_df, "ME")
    div_monthly = ""
    if not intensity_m.empty:
        fig = px.line(intensity_m, x="date", y="Plays", title="Monthly Listening Activity")
        apply_dark_theme(fig)
        div_monthly = f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    div_cumulative = ""
    if not cumulative.empty:
        fig = px.area(cumulative, x="date", y="CumulativePlays", title="Total Plays (Cumulative)")
        fig.update_traces(line_color=_TEAL, fillcolor="rgba(0,200,200,0.15)")
        apply_dark_theme(fig)
        div_cumulative = f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listening Report · {start} – {end}</title>
<style>{_html_styles()}</style>
</head>
<body>
<div class="container">

  <header class="app-header">
    <h1>Listening Report</h1>
    <span class="subtitle">{start} – {end}</span>
  </header>

  <div class="metrics-row">
    <div class="metric-card">
      <div class="label">Scrobbles</div>
      <div class="value">{n:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Listening Time</div>
      <div class="value">{hours:.0f}h</div>
    </div>
    <div class="metric-card">
      <div class="label">Avg / Day</div>
      <div class="value">{n / days:.0f}</div>
    </div>
    <div class="metric-card">
      <div class="label">Most Active Day</div>
      <div class="value" style="font-size:0.95rem;padding-top:0.3rem">{most_active_label}</div>
    </div>
  </div>

  <div class="section-title">Top Artists · Albums · Tracks</div>
  {entity_cols_html}

  <div class="section-title">Daily Activity</div>
  {div_daily}

  <div class="grid-2" style="margin-top:1rem">
    {div_clock}
    {div_growth}
  </div>

  <div class="section-title">Top Charts</div>
  {div_artists}
  {div_tracks}
  {div_albums}

  <div class="section-title">Timeline</div>
  {div_stream}
  {div_bump}
  {div_monthly}
  {div_cumulative}

  <footer class="app-footer">
    Generated by Autobiographer &mdash; {generated_at}
    &mdash; all data processed locally, no external network calls.
  </footer>

</div>
</body>
</html>"""


# ── Overview page export ────────────────────────────────────────────────────


def build_overview_page_html(
    df: pd.DataFrame,
    swarm_df: pd.DataFrame | None,
    generated_at: str,
) -> str:
    """Build a self-contained HTML export of the Overview page.

    Args:
        df: Listening history DataFrame.
        swarm_df: Optional Swarm check-in DataFrame.
        generated_at: Human-readable UTC timestamp shown in the footer.

    Returns:
        A complete ``<!DOCTYPE html>`` document as a string.
    """
    total_scrobbles = len(df)
    unique_artists = df["artist"].nunique() if "artist" in df.columns else 0
    unique_albums = df["album"].nunique() if "album" in df.columns else 0
    unique_tracks = df["track"].nunique() if "track" in df.columns else 0
    active_days = df["date_text"].dt.date.nunique()
    date_min = df["date_text"].min()
    date_max = df["date_text"].max()
    date_range_str = (
        f"{date_min.strftime('%b %Y')} – {date_max.strftime('%b %Y')}"
        if pd.notna(date_min) and pd.notna(date_max)
        else "N/A"
    )

    swarm_html = ""
    if swarm_df is not None and not swarm_df.empty:
        total_checkins = len(swarm_df)
        unique_venues = swarm_df["venue"].nunique() if "venue" in swarm_df.columns else 0
        unique_cities = swarm_df["city"].nunique() if "city" in swarm_df.columns else 0
        unique_countries = swarm_df["country"].nunique() if "country" in swarm_df.columns else 0
        swarm_html = f"""
    <div class="metric-card">
      <div class="label">Check-ins</div><div class="value">{total_checkins:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Venues</div><div class="value">{unique_venues:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Cities</div><div class="value">{unique_cities:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Countries</div><div class="value">{unique_countries:,}</div>
    </div>"""

    first_chart: list[bool] = [True]

    def _chart(fig: go.Figure) -> str:
        include = first_chart[0]
        first_chart[0] = False
        return _chart_div(fig, include_js=include)

    def _top_bar(entity: str, limit: int = 20) -> str:
        top = get_top_entities(df, entity, limit=limit)
        if top.empty:
            return ""
        fig = px.bar(
            top,
            x="Plays",
            y=entity,
            orientation="h",
            title=f"Top {limit} {entity.capitalize()}s",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
        apply_dark_theme(fig)
        return f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    div_artists = _top_bar("artist")
    div_tracks = _top_bar("track")
    div_albums = _top_bar("album")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Overview · {date_range_str}</title>
<style>{_html_styles()}</style>
</head>
<body>
<div class="container">

  <header class="app-header">
    <h1>Overview</h1>
    <span class="subtitle">{date_range_str}</span>
  </header>

  <div class="metrics-row">
    <div class="metric-card">
      <div class="label">Scrobbles</div><div class="value">{total_scrobbles:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Artists</div><div class="value">{unique_artists:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Albums</div><div class="value">{unique_albums:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Tracks</div><div class="value">{unique_tracks:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Active Days</div><div class="value">{active_days:,}</div>
    </div>
    {swarm_html}
  </div>

  <div class="section-title">Top Artists</div>
  {div_artists}
  <div class="section-title">Top Tracks</div>
  {div_tracks}
  <div class="section-title">Top Albums</div>
  {div_albums}

  <footer class="app-footer">
    Generated by Autobiographer &mdash; {generated_at}
    &mdash; all data processed locally, no external network calls.
  </footer>

</div>
</body>
</html>"""


# ── Insights page export ─────────────────────────────────────────────────────


def build_insights_page_html(
    filtered_df: pd.DataFrame,
    generated_at: str,
) -> str:
    """Build a self-contained HTML export of the Insights page.

    Args:
        filtered_df: Listening history filtered by the page's active filters.
        generated_at: Human-readable UTC timestamp shown in the footer.

    Returns:
        A complete ``<!DOCTYPE html>`` document as a string.
    """
    if filtered_df.empty:
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Insights</title><style>{_html_styles()}</style></head><body>
<div class="container"><header class="app-header"><h1>Insights &amp; Narrative</h1></header>
<p class="empty-msg">No data found for the selected filters.</p>
<footer class="app-footer">Generated by Autobiographer &mdash; {generated_at}</footer>
</div></body></html>"""

    first_chart: list[bool] = [True]

    def _chart(fig: go.Figure) -> str:
        include = first_chart[0]
        first_chart[0] = False
        return _chart_div(fig, include_js=include)

    # ── Sunburst ─────────────────────────────────────────────────────────────
    div_sunburst = ""
    if "album" in filtered_df.columns:
        top_artists = get_top_entities(filtered_df, "artist", limit=12)["artist"].tolist()
        subset = filtered_df[filtered_df["artist"].isin(top_artists)].copy()
        grouped = subset.groupby(["artist", "album"]).size().reset_index(name="scrobbles")
        if not grouped.empty:
            fig = px.sunburst(
                grouped,
                path=["artist", "album"],
                values="scrobbles",
                title="Music Listening Hierarchy",
                color_discrete_sequence=COLORWAY,
            )
            fig.update_traces(textinfo="label+percent parent")
            apply_dark_theme(fig)
            div_sunburst = f'<div class="card">{_chart(fig)}</div>'

    # ── Top entities tables ───────────────────────────────────────────────────
    def _top_table(entity: str, limit: int = 20) -> str:
        top = get_top_entities(filtered_df, entity, limit=limit)
        return _table_html(top)

    # ── Time patterns ─────────────────────────────────────────────────────────
    hourly = get_hourly_distribution(filtered_df)
    div_hourly = ""
    if not hourly.empty:
        fig = px.bar(hourly, x="hour", y="Plays", title="Listening by Hour of Day")
        apply_dark_theme(fig)
        div_hourly = f'<div class="card">{_chart(fig)}</div>'

    heatmap_pivot = get_day_hour_heatmap(filtered_df)
    div_heatmap = ""
    if not heatmap_pivot.empty:
        fig = px.imshow(
            heatmap_pivot,
            labels=dict(x="Hour of Day", y="Day of Week", color="Plays"),
            title="Listening Intensity (Day vs Hour)",
            aspect="auto",
            color_continuous_scale=SEQUENTIAL_SCALE,
        )
        apply_dark_theme(fig)
        div_heatmap = f'<div class="card">{_chart(fig)}</div>'

    # ── Narrative ─────────────────────────────────────────────────────────────
    milestones_html = _table_html(get_milestones(filtered_df))
    streaks = get_listening_streaks(filtered_df)
    forgotten = get_forgotten_favorites(filtered_df)
    forgotten_html = (
        _table_html(forgotten)
        if not forgotten.empty
        else "<p class='empty-msg'>No forgotten favorites identified.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Insights &amp; Narrative</title>
<style>{_html_styles()}</style>
</head>
<body>
<div class="container">

  <header class="app-header">
    <h1>Insights &amp; Narrative</h1>
  </header>

  <div class="section-title">Music Listening Hierarchy</div>
  {div_sunburst}

  <div class="grid-2" style="margin-top:1.5rem">
    <div>
      <div class="section-title">Top Artists</div>
      <div class="card">{_top_table("artist")}</div>
    </div>
    <div>
      <div class="section-title">Top Tracks</div>
      <div class="card">{_top_table("track")}</div>
    </div>
  </div>

  <div class="section-title">Time-based Patterns</div>
  <div class="grid-2">
    {div_hourly}
    {div_heatmap}
  </div>

  <div class="section-title">Autobiographical Milestones</div>
  <div class="card">{milestones_html}</div>

  <div class="section-title">Listening Streaks</div>
  <div class="streak-row">
    <div class="streak-card">
      <div class="s-label">Longest Streak</div>
      <div class="s-value">{streaks["longest_streak"]} days</div>
    </div>
    <div class="streak-card">
      <div class="s-label">Current Streak</div>
      <div class="s-value">{streaks["current_streak"]} days</div>
    </div>
  </div>

  <div class="section-title">Forgotten Favorites</div>
  <div class="card">{forgotten_html}</div>

  <footer class="app-footer">
    Generated by Autobiographer &mdash; {generated_at}
    &mdash; all data processed locally, no external network calls.
  </footer>

</div>
</body>
</html>"""


# ── Places / Check-in Insights page exports ──────────────────────────────────


def build_checkin_insights_html(
    swarm_df: pd.DataFrame,
    generated_at: str,
) -> str:
    """Build a self-contained HTML export of the Check-in Insights page.

    Args:
        swarm_df: Swarm/Foursquare check-in DataFrame.
        generated_at: Human-readable UTC timestamp shown in the footer.

    Returns:
        A complete ``<!DOCTYPE html>`` document as a string.
    """
    places_body = _build_places_html(swarm_df)

    country_counts = (
        swarm_df.groupby("country").size().reset_index(name="Check-ins")
        if "country" in swarm_df.columns
        else pd.DataFrame(columns=["country", "Check-ins"])
    )
    country_counts = country_counts.sort_values("Check-ins", ascending=False)

    first_chart: list[bool] = [True]

    def _chart(fig: go.Figure) -> str:
        include = first_chart[0]
        first_chart[0] = False
        return _chart_div(fig, include_js=include)

    div_countries_bar = ""
    if not country_counts.empty:
        fig = px.bar(
            country_counts,
            x="country",
            y="Check-ins",
            title=f"Check-ins across {len(country_counts)} countries",
        )
        apply_dark_theme(fig)
        div_countries_bar = f'<div class="card">{_chart(fig)}</div>'

    div_cities_bar = ""
    if "city" in swarm_df.columns:
        city_counts = (
            swarm_df.groupby(["city", "country"]).size().reset_index(name="Check-ins")
            if "country" in swarm_df.columns
            else swarm_df.groupby("city").size().reset_index(name="Check-ins")
        )
        city_counts = city_counts.sort_values("Check-ins", ascending=False).head(20)
        fig = px.bar(
            city_counts,
            x="Check-ins",
            y="city",
            orientation="h",
            title="Top 20 Cities",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
        apply_dark_theme(fig)
        div_cities_bar = f'<div class="card" style="margin-top:1rem">{_chart(fig)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Check-in Insights</title>
<style>{_html_styles()}</style>
</head>
<body>
<div class="container">

  <header class="app-header">
    <h1>Check-in Insights</h1>
  </header>

  {places_body}

  <div class="section-title">By Country</div>
  {div_countries_bar}
  <div class="card" style="margin-top:1rem">{_table_html(country_counts)}</div>

  <div class="section-title">Top Cities</div>
  {div_cities_bar}

  <footer class="app-footer">
    Generated by Autobiographer &mdash; {generated_at}
    &mdash; all data processed locally, no external network calls.
  </footer>

</div>
</body>
</html>"""


def build_places_page_html(
    df: pd.DataFrame,
    generated_at: str,
) -> str:
    """Build a self-contained HTML export of the Places (spatial) page.

    The interactive 3D deck.gl map cannot be exported to static HTML; this
    export renders an equivalent Plotly scatter-geo world map with city columns
    and country counts.

    Args:
        df: Listening history DataFrame with ``lat``, ``lng``, and ``city`` columns.
        generated_at: Human-readable UTC timestamp shown in the footer.

    Returns:
        A complete ``<!DOCTYPE html>`` document as a string.
    """
    geo_data = (
        df.dropna(subset=["lat", "lng"])
        .groupby(["lat", "lng", "city"], as_index=False)
        .size()
        .rename(columns={"size": "Plays"})
    )

    if geo_data.empty:
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Places</title><style>{_html_styles()}</style></head><body>
<div class="container"><header class="app-header"><h1>Places</h1></header>
<p class="empty-msg">No geographic data available.</p>
<footer class="app-footer">Generated by Autobiographer &mdash; {generated_at}</footer>
</div></body></html>"""

    first_chart: list[bool] = [True]

    def _chart(fig: go.Figure) -> str:
        include = first_chart[0]
        first_chart[0] = False
        return _chart_div(fig, include_js=include)

    fig_map = px.scatter_geo(
        geo_data,
        lat="lat",
        lon="lng",
        size="Plays",
        color="Plays",
        hover_name="city",
        hover_data={"Plays": True, "lat": False, "lng": False},
        title="Where You've Listened",
        color_continuous_scale=SEQUENTIAL_SCALE,
        size_max=25,
        projection="natural earth",
    )
    fig_map.update_layout(
        height=500,
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            landcolor=_PANEL_BG,
            oceancolor=_BG,
            countrycolor=_BORDER,
            showland=True,
            showocean=True,
            showcountries=True,
        ),
    )
    apply_dark_theme(fig_map)

    top_cities = (
        df.dropna(subset=["lat", "lng"])
        .groupby("city")
        .size()
        .reset_index(name="Plays")
        .sort_values("Plays", ascending=False)
        .head(20)
    )
    fig_cities = px.bar(
        top_cities,
        x="Plays",
        y="city",
        orientation="h",
        title="Top 20 Cities by Listening Plays",
    )
    fig_cities.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    apply_dark_theme(fig_cities)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Places</title>
<style>{_html_styles()}</style>
</head>
<body>
<div class="container">

  <header class="app-header">
    <h1>Places</h1>
    <span class="subtitle">Where you've listened</span>
  </header>

  <p class="section-desc" style="margin-bottom:1rem">
    Note: the interactive 3D map is not available in static exports.
    A Plotly equivalent is shown below.
  </p>

  <div class="card">{_chart(fig_map)}</div>
  <div class="card" style="margin-top:1rem">{_chart(fig_cities)}</div>

  <footer class="app-footer">
    Generated by Autobiographer &mdash; {generated_at}
    &mdash; all data processed locally, no external network calls.
  </footer>

</div>
</body>
</html>"""


# ── Core report builder ─────────────────────────────────────────────────────


def build_html(
    df: pd.DataFrame,
    generated_at: str,
    swarm_df: pd.DataFrame | None = None,
) -> str:
    """Build a complete self-contained HTML report from a listening DataFrame.

    Generates tabbed sections (Overview, Listening, Insights, and optionally
    Places) using the same analysis functions as the Streamlit dashboard.  All
    Plotly.js JavaScript is embedded inline so the file can be opened in any
    browser without an internet connection.

    Args:
        df: Listening history DataFrame.  Must contain at minimum the columns
            ``artist``, ``album``, ``track``, and ``date_text`` (datetime).
        generated_at: Human-readable timestamp string shown in the report footer.
        swarm_df: Optional Swarm/Foursquare check-in DataFrame.  When provided,
            a Places tab is added with a world map and city/country breakdowns.

    Returns:
        A complete ``<!DOCTYPE html>`` document as a string.
    """
    # ── Metrics ──────────────────────────────────────────────────────────────
    total_tracks = len(df)
    unique_artists = df["artist"].nunique() if "artist" in df.columns else 0
    unique_albums = df["album"].nunique() if "album" in df.columns else 0
    date_min = df["date_text"].min()
    date_max = df["date_text"].max()
    date_range = (
        f"{date_min.strftime('%b %Y')} – {date_max.strftime('%b %Y')}"
        if pd.notna(date_min) and pd.notna(date_max)
        else "N/A"
    )

    # ── Overview charts ───────────────────────────────────────────────────────
    top_artists = get_top_entities(df, "artist", limit=20)
    top_tracks = get_top_entities(df, "track", limit=20)
    top_albums = get_top_entities(df, "album", limit=20)

    fig_artists = px.bar(
        top_artists, x="Plays", y="artist", orientation="h", title="Top 20 Artists"
    )
    fig_artists.update_layout(yaxis={"categoryorder": "total ascending"}, height=600)
    apply_dark_theme(fig_artists)

    fig_tracks = px.bar(top_tracks, x="Plays", y="track", orientation="h", title="Top 20 Tracks")
    fig_tracks.update_layout(yaxis={"categoryorder": "total ascending"}, height=600)
    apply_dark_theme(fig_tracks)

    fig_albums = px.bar(top_albums, x="Plays", y="album", orientation="h", title="Top 20 Albums")
    fig_albums.update_layout(yaxis={"categoryorder": "total ascending"}, height=600)
    apply_dark_theme(fig_albums)

    # ── Listening charts ──────────────────────────────────────────────────────
    monthly = get_listening_intensity(df, "ME")
    fig_monthly = px.line(monthly, x="date", y="Plays", title="Monthly Listening Activity")
    apply_dark_theme(fig_monthly)

    cumulative = get_cumulative_plays(df)
    fig_cumulative = px.area(
        cumulative, x="date", y="CumulativePlays", title="Cumulative Plays Over Time"
    )
    apply_dark_theme(fig_cumulative)

    # ── Insights charts ───────────────────────────────────────────────────────
    hourly = get_hourly_distribution(df)
    fig_hourly = px.bar(hourly, x="hour", y="Plays", title="Listening by Hour of Day")
    apply_dark_theme(fig_hourly)

    df_copy = df.copy()
    df_copy["day_of_week"] = df_copy["date_text"].dt.day_name()
    df_copy["hour"] = df_copy["date_text"].dt.hour
    heatmap_data = df_copy.groupby(["day_of_week", "hour"]).size().reset_index(name="Plays")
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heatmap_data["day_of_week"] = pd.Categorical(
        heatmap_data["day_of_week"], categories=days_order, ordered=True
    )
    heatmap_pivot = heatmap_data.pivot(index="day_of_week", columns="hour", values="Plays").fillna(
        0
    )
    fig_heatmap = px.imshow(
        heatmap_pivot,
        labels={"x": "Hour of Day", "y": "Day of Week", "color": "Plays"},
        title="Listening Intensity (Day vs Hour)",
        aspect="auto",
        color_continuous_scale=SEQUENTIAL_SCALE,
    )
    apply_dark_theme(fig_heatmap)

    # ── Narrative tables ──────────────────────────────────────────────────────
    milestones_html = _table_html(get_milestones(df))
    streaks = get_listening_streaks(df)

    # ── Serialise charts ──────────────────────────────────────────────────────
    # The very first chart carries the inlined plotly.js bundle (~3 MB).
    # All subsequent charts emit only their div + inline newPlot() call.
    div_artists = _chart_div(fig_artists, include_js=True)
    div_tracks = _chart_div(fig_tracks)
    div_albums = _chart_div(fig_albums)
    div_monthly = _chart_div(fig_monthly)
    div_cumulative = _chart_div(fig_cumulative)
    div_hourly = _chart_div(fig_hourly)
    div_heatmap = _chart_div(fig_heatmap)

    # ── Places tab (optional) ─────────────────────────────────────────────────
    has_places = swarm_df is not None and not swarm_df.empty
    places_nav_btn = (
        '<button class="tab-btn" data-tab="places" onclick="showTab(\'places\')">Places</button>'
        if has_places
        else ""
    )
    places_tab_html = (
        f'<div id="tab-places" class="tab-content">'
        f'<p class="section-desc">Where you\'ve been, based on Foursquare/Swarm check-ins.</p>'
        f"{_build_places_html(swarm_df)}"
        f"</div>"
        if has_places
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autobiographer</title>
<style>{_html_styles()}</style>
<script>
  function showTab(id) {{
    document.querySelectorAll('.tab-content').forEach(function(el) {{
      el.classList.remove('active');
    }});
    document.querySelectorAll('.tab-btn').forEach(function(el) {{
      el.classList.remove('active');
    }});
    document.getElementById('tab-' + id).classList.add('active');
    document.querySelector('[data-tab="' + id + '"]').classList.add('active');
    // Resize Plotly charts so they fill the newly visible container correctly.
    document.getElementById('tab-' + id).querySelectorAll('.plotly-graph-div').forEach(function(div) {{
      if (window.Plotly) {{ Plotly.Plots.resize(div); }}
    }});
  }}
  document.addEventListener('DOMContentLoaded', function() {{
    showTab('overview');
  }});
</script>
</head>
<body>
<div class="container">

  <!-- ── Header ── -->
  <header class="app-header">
    <h1>Autobiographer</h1>
    <span class="subtitle">{date_range}</span>
  </header>

  <!-- ── Key metrics ── -->
  <div class="metrics-row">
    <div class="metric-card">
      <div class="label">Total Tracks</div>
      <div class="value">{total_tracks:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Unique Artists</div>
      <div class="value">{unique_artists:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Unique Albums</div>
      <div class="value">{unique_albums:,}</div>
    </div>
    <div class="metric-card">
      <div class="label">Date Range</div>
      <div class="value" style="font-size:1rem; padding-top:0.3rem">{date_range}</div>
    </div>
  </div>

  <!-- ── Tab navigation ── -->
  <nav class="tab-nav">
    <button class="tab-btn" data-tab="overview" onclick="showTab('overview')">Overview</button>
    <button class="tab-btn" data-tab="listening" onclick="showTab('listening')">Listening</button>
    <button class="tab-btn" data-tab="insights" onclick="showTab('insights')">Insights</button>
    {places_nav_btn}
  </nav>

  <!-- ════════════════════════════════ OVERVIEW ═══════════════════════════════ -->
  <div id="tab-overview" class="tab-content">
    <p class="section-desc">Top artists, albums, and tracks by total play count.</p>

    <!-- plotly.js bundle is inlined with the first chart -->
    <div class="card">{div_artists}</div>
    <div class="card" style="margin-top:1rem">{div_tracks}</div>
    <div class="card" style="margin-top:1rem">{div_albums}</div>
  </div>

  <!-- ════════════════════════════════ LISTENING ══════════════════════════════ -->
  <div id="tab-listening" class="tab-content">
    <p class="section-desc">Listening activity and cumulative growth over time.</p>

    <div class="card">{div_monthly}</div>
    <div class="card" style="margin-top:1rem">{div_cumulative}</div>
  </div>

  <!-- ════════════════════════════════ INSIGHTS ═══════════════════════════════ -->
  <div id="tab-insights" class="tab-content">
    <p class="section-desc">Patterns, narrative milestones, and autobiographical highlights.</p>

    <div class="grid-2">
      <div class="card">{div_hourly}</div>
      <div class="card">{div_heatmap}</div>
    </div>

    <div class="section-title" style="margin-top:1.5rem">Autobiographical Milestones</div>
    <div class="card">{milestones_html}</div>

    <div class="section-title">Listening Streaks</div>
    <div class="streak-row">
      <div class="streak-card">
        <div class="s-label">Longest Streak</div>
        <div class="s-value">{streaks["longest_streak"]} days</div>
      </div>
      <div class="streak-card">
        <div class="s-label">Current Streak</div>
        <div class="s-value">{streaks["current_streak"]} days</div>
      </div>
    </div>
  </div>

  {places_tab_html}

  <!-- ── Footer ── -->
  <footer class="app-footer">
    Generated by Autobiographer &mdash; {generated_at}
    &mdash; all data processed locally, no external network calls.
  </footer>

</div>
</body>
</html>"""


# ── Export pipeline ─────────────────────────────────────────────────────────


def export_report(
    df: pd.DataFrame,
    output_path: str,
    swarm_df: pd.DataFrame | None = None,
) -> None:
    """Write a self-contained HTML report to *output_path*.

    Args:
        df: Listening history DataFrame as returned by :func:`load_listening_data`.
        output_path: Filesystem path for the output ``.html`` file.  Parent
            directories are created automatically.
        swarm_df: Optional Swarm check-in DataFrame.  When provided, a Places
            tab with a world map is added to the report.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = build_html(df, generated_at, swarm_df=swarm_df)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Report written → {output_path}")


# ── CLI ─────────────────────────────────────────────────────────────────────


def _resolve_paths(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Determine data file paths from CLI args or local_settings.json.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Tuple of ``(csv_path, swarm_dir)``, either of which may be None if
        not provided on the command line or found in local_settings.json.
    """
    csv_path: str | None = str(args.csv) if args.csv else None
    swarm_dir: str | None = str(args.swarm_dir) if args.swarm_dir else None

    if not csv_path or not swarm_dir:
        settings = LocalSettings()
        if not csv_path:
            csv_path = settings.get_plugin_config("lastfm").get("data_path")
        if not swarm_dir:
            swarm_dir = settings.get_plugin_config("swarm").get("swarm_dir")

    return csv_path, swarm_dir


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``export_html`` CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when None).
    """
    parser = argparse.ArgumentParser(
        description="Export a self-contained Autobiographer HTML report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "csv",
        nargs="?",
        metavar="CSV",
        help="Path to Last.fm listening history CSV.  "
        "Omit to read the path from local_settings.json (--from-settings).",
    )
    parser.add_argument(
        "--swarm-dir",
        metavar="DIR",
        help="Path to Foursquare/Swarm JSON export directory.  "
        "Adds a Places tab with a world map to the report.",
    )
    parser.add_argument(
        "--from-settings",
        action="store_true",
        help="Load all data paths stored in local_settings.json "
        "(set once via the Streamlit dashboard).",
    )
    parser.add_argument(
        "--output",
        default="autobiographer_report.html",
        metavar="PATH",
        help="Output HTML file path (default: autobiographer_report.html).",
    )

    args = parser.parse_args(argv)

    csv_path, swarm_dir = _resolve_paths(args)
    if not csv_path:
        parser.error(
            "No CSV path provided.  Pass a CSV file as a positional argument "
            "or use --from-settings if a path is saved in local_settings.json."
        )

    assert csv_path is not None  # parser.error() exits if csv_path is None
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = load_listening_data(csv_path)
    if df is None or df.empty:
        print(f"Error: no data loaded from {csv_path}", file=sys.stderr)
        sys.exit(1)

    swarm_df: pd.DataFrame | None = None
    if swarm_dir:
        if not os.path.isdir(swarm_dir):
            print(
                f"Warning: --swarm-dir not found, skipping Places tab: {swarm_dir}", file=sys.stderr
            )
        else:
            swarm_df = load_swarm_data(swarm_dir)
            if swarm_df.empty:
                print("Warning: no Swarm check-ins loaded, skipping Places tab.", file=sys.stderr)
                swarm_df = None

    export_report(df, args.output, swarm_df=swarm_df)


if __name__ == "__main__":
    main()
