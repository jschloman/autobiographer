"""Places page — geographic listening history map and check-in insights."""

from __future__ import annotations

import io
import json
import os
import time

import numpy as np
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st
from pandas import DataFrame

from components.theme import (
    MAP_COLUMN_DEFAULT_RGBA,
    MAP_COUNTRY_BORDER_RGB,
    MAP_COUNTRY_UNVISITED_RGBA,
    MAP_COUNTRY_VISITED_RGBA,
    MAP_STATE_BORDER_RGBA,
    apply_dark_theme,
)


def render_spatial_analysis(df: DataFrame) -> None:
    """Render 3D geographical visualization of listening history.

    Args:
        df: Listening history DataFrame with lat/lng/city columns.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    st.header("Spatial Music Explorer")

    if "lat" not in df.columns or df["lat"].isna().all():
        st.warning(
            "No geographic data found. Please provide a Swarm data directory to enable this view."
        )
        return

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        artists = ["All"] + sorted(df["artist"].dropna().unique().tolist())
        selected_artist = st.selectbox("Filter by Artist", artists)
    with col_f2:
        min_date = df["date_text"].min().date()
        max_date = df["date_text"].max().date()
        date_range = st.date_input(
            "Filter by Date Range", [min_date, max_date], key="spatial_date_range"
        )

    map_df = df.copy()
    if selected_artist != "All":
        map_df = map_df[map_df["artist"] == selected_artist]

    if len(date_range) == 2:
        map_df = map_df[
            (map_df["date_text"].dt.date >= date_range[0])
            & (map_df["date_text"].dt.date <= date_range[1])
        ]

    if map_df.empty:
        st.info("No data matches the selected filters.")
        return

    geo_data = map_df.groupby(["lat", "lng", "city"]).size().reset_index(name="Plays")

    if "spatial_view_state" not in st.session_state:
        st.session_state.spatial_view_state = pdk.ViewState(
            latitude=geo_data["lat"].mean(),
            longitude=geo_data["lng"].mean(),
            zoom=3,
            pitch=45,
            bearing=0,
        )

    col_a, col_b, col_c = st.columns(3)

    def get_view_val(attr: str, default: float) -> float:
        """Return a float view state attribute with a safe fallback."""
        val = getattr(st.session_state.spatial_view_state, attr, default)
        return float(val) if val is not None else float(default)

    with col_a:
        zoom_level = st.slider(
            "Map Zoom",
            min_value=1.0,
            max_value=15.0,
            value=get_view_val("zoom", 3.0),
            step=0.5,
            key="zoom_slider",
        )
    with col_b:
        bearing = st.slider(
            "Rotation",
            min_value=-180.0,
            max_value=180.0,
            value=get_view_val("bearing", 0.0),
            step=5.0,
            key="bearing_slider",
        )
    with col_c:
        pitch = st.slider(
            "Tilt",
            min_value=0.0,
            max_value=90.0,
            value=get_view_val("pitch", 45.0),
            step=5.0,
            key="pitch_slider",
        )

    st.session_state.spatial_view_state.zoom = zoom_level
    st.session_state.spatial_view_state.bearing = bearing
    st.session_state.spatial_view_state.pitch = pitch

    st.subheader("Cinematic Fly-through")
    fly_col1, fly_col2 = st.columns([1, 3])
    with fly_col1:
        if st.button("Play Fly-through"):
            top_cities = geo_data.sort_values("Plays", ascending=False).head(5)
            keyframes = []
            for _, row in top_cities.iterrows():
                keyframes.append(
                    {"lat": row["lat"], "lng": row["lng"], "zoom": 12, "pitch": 60, "bearing": 30}
                )
            keyframes.append(
                {
                    "lat": geo_data["lat"].mean(),
                    "lng": geo_data["lng"].mean(),
                    "zoom": 2,
                    "pitch": 0,
                    "bearing": 0,
                }
            )
            st.session_state.fly_keyframes = keyframes
            st.session_state.fly_index = 0
            st.rerun()

    with fly_col2:
        if st.button("Export Recording HTML"):
            top_cities = geo_data.sort_values("Plays", ascending=False).head(8)
            export_keyframes: list[dict[str, float | int]] = [
                {
                    "latitude": geo_data["lat"].mean(),
                    "longitude": geo_data["lng"].mean(),
                    "zoom": 2,
                    "pitch": 0,
                    "bearing": 0,
                    "duration": 2000,
                }
            ]
            for _, row in top_cities.iterrows():
                export_keyframes.append(
                    {
                        "latitude": row["lat"],
                        "longitude": row["lng"],
                        "zoom": 11,
                        "pitch": 60,
                        "bearing": 45,
                        "duration": 4000,
                    }
                )
            export_keyframes.append(
                {
                    "latitude": geo_data["lat"].mean(),
                    "longitude": geo_data["lng"].mean(),
                    "zoom": 3,
                    "pitch": 45,
                    "bearing": 0,
                    "duration": 4000,
                }
            )

            export_deck = pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ColumnLayer",
                        geo_data,
                        get_position=["lng", "lat"],
                        get_elevation="elevation",
                        elevation_scale=10,
                        radius=5000,
                        get_fill_color="color",
                    )
                ],
                initial_view_state=pdk.ViewState(
                    latitude=export_keyframes[0]["latitude"],
                    longitude=export_keyframes[0]["longitude"],
                    zoom=export_keyframes[0]["zoom"],
                ),
                map_style="dark",
            )

            html_content = export_deck.to_html(as_string=True)
            animation_script = f"""
            <script>
            const keyframes = {json.dumps(export_keyframes)};
            let currentStep = 0;
            function nextStep() {{
                if (currentStep >= keyframes.length) return;
                const kf = keyframes[currentStep];
                const deckgl = window.deck.deck;
                deckgl.setProps({{
                    initialViewState: {{
                        ...kf,
                        transitionDuration: kf.duration,
                        transitionInterpolator: new window.deck.FlyToInterpolator()
                    }}
                }});
                currentStep++;
                setTimeout(nextStep, kf.duration + 500);
            }}
            setTimeout(nextStep, 2000);
            </script>
            """
            html_content = html_content.replace("</body>", f"{animation_script}</body>")

            st.download_button(
                label="Download Fly-through HTML",
                data=html_content,
                file_name="music_flythrough.html",
                mime="text/html",
            )

    if "fly_keyframes" in st.session_state and st.session_state.fly_index < len(
        st.session_state.fly_keyframes
    ):
        kf = st.session_state.fly_keyframes[st.session_state.fly_index]
        st.session_state.spatial_view_state = pdk.ViewState(
            latitude=kf["lat"],
            longitude=kf["lng"],
            zoom=kf["zoom"],
            pitch=kf["pitch"],
            bearing=kf["bearing"],
            transition_duration=3000,
            transition_interp="FLY_TO",
        )
        st.session_state.fly_index += 1
        time.sleep(3.2)
        st.rerun()
    elif "fly_keyframes" in st.session_state:
        del st.session_state.fly_keyframes
        del st.session_state.fly_index
        st.success("Fly-through complete!")

    def get_spectrum_color(val: float, max_val: float) -> list[int]:
        """Return an RGBA color interpolated from teal to amber for dark basemaps.

        Low-play locations render as deep teal; high-play locations render as
        warm amber, both of which read clearly against the dark map background.
        """
        if max_val == 0:
            return MAP_COLUMN_DEFAULT_RGBA
        ratio = val / max_val
        if ratio < 0.5:
            # Deep teal [0, 200, 200] → cyan-green [100, 220, 120]
            t = ratio * 2
            r = int(0 + 100 * t)
            g = int(200 + 20 * t)
            b = int(200 - 80 * t)
        else:
            # Cyan-green [100, 220, 120] → warm amber [255, 160, 20]
            t = (ratio - 0.5) * 2
            r = int(100 + 155 * t)
            g = int(220 - 60 * t)
            b = int(120 - 100 * t)
        return [r, g, b, 220]

    dynamic_radius = 50000 / (2 ** (zoom_level - 1))

    geo_data["elevation_log"] = np.log1p(geo_data["Plays"])
    max_log = geo_data["elevation_log"].max()

    geo_data["elevation"] = (
        (geo_data["elevation_log"] / max_log) * (1.4 * dynamic_radius) if max_log > 0 else 0
    )
    geo_data["color"] = geo_data["elevation_log"].apply(lambda x: get_spectrum_color(x, max_log))

    @st.cache_data
    def get_highlighted_map(geo_points_json: str) -> tuple[object, str | None]:
        """Load world/states GeoJSON and mark countries with listening history."""
        countries_path = os.path.join("assets", "countries.geojson")
        states_path = os.path.join("assets", "states.geojson")
        if not os.path.exists(countries_path):
            return None, None
        world = gpd.read_file(countries_path)
        points_df = __import__("pandas").read_json(io.StringIO(geo_points_json))
        geometry = [Point(xy) for xy in zip(points_df.lng, points_df.lat)]
        points_gpd = gpd.GeoDataFrame(points_df, geometry=geometry, crs="EPSG:4326")
        countries_with_points = gpd.sjoin(world, points_gpd, how="inner", predicate="intersects")

        def country_color_logic(country_idx: int) -> list[int]:
            if country_idx in countries_with_points.index:
                return MAP_COUNTRY_VISITED_RGBA
            return MAP_COUNTRY_UNVISITED_RGBA

        world["fill_color"] = world.index.map(country_color_logic)
        return world, states_path if os.path.exists(states_path) else None

    world_gdf, states_geojson_path = get_highlighted_map(geo_data.to_json())

    layers = []
    if world_gdf is not None:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                world_gdf,
                stroked=True,
                filled=True,
                get_fill_color="fill_color",
                get_line_color=MAP_COUNTRY_BORDER_RGB,
                get_line_width=1,
            )
        )
    if states_geojson_path and os.path.exists(states_geojson_path):
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                states_geojson_path,
                stroked=True,
                filled=False,
                get_line_color=MAP_STATE_BORDER_RGBA,
                get_line_width=1,
            )
        )

    layers.extend(
        [
            pdk.Layer(
                "ScatterplotLayer",
                geo_data,
                get_position=["lng", "lat"],
                get_fill_color="color",
                radius=dynamic_radius * 1.2,
                pickable=True,
            ),
            pdk.Layer(
                "ColumnLayer",
                geo_data,
                get_position=["lng", "lat"],
                get_elevation="elevation",
                elevation_scale=10,
                radius=dynamic_radius,
                get_fill_color="color",
                pickable=True,
                auto_highlight=True,
            ),
        ]
    )

    r = pdk.Deck(
        layers=layers,
        initial_view_state=st.session_state.spatial_view_state,
        tooltip={"text": "{city}: {Plays} plays"},
        map_style="dark",
    )
    st.pydeck_chart(r, key="spatial_map")

    st.markdown("""
    **Map Navigation Gestures:**
    - **Pan**: Left-click and drag.
    - **Rotate/Tilt**: Right-click and drag (or use the sliders above).
    - **Zoom**: Mouse wheel or pinch gesture.
    """)

    st.dataframe(geo_data.sort_values("Plays", ascending=False), hide_index=True)


def render_checkin_insights() -> None:
    """Render the Places Insights page: country and city breakdown of Swarm check-ins.

    Reads ``st.session_state['swarm_df']``.  Shows an empty state when no
    Foursquare/Swarm data has been loaded.
    """
    swarm_df: DataFrame | None = st.session_state.get("swarm_df")

    st.header("Check-in Insights")

    if swarm_df is None or swarm_df.empty:
        st.info(
            "No Foursquare/Swarm data loaded yet. "
            "Configure the Swarm export directory in the sidebar."
        )
        return

    # ── Countries ─────────────────────────────────────────────────────────────
    st.subheader("By Country")
    country_counts = (
        swarm_df.groupby("country").size().reset_index(name="Check-ins")
        if "country" in swarm_df.columns
        else pd.DataFrame(columns=["country", "Check-ins"])
    )
    country_counts = country_counts.sort_values("Check-ins", ascending=False).reset_index(drop=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        fig = px.bar(
            country_counts,
            x="country",
            y="Check-ins",
            title=f"Check-ins across {len(country_counts)} countries",
        )
        apply_dark_theme(fig)
        st.plotly_chart(fig, width="stretch")
    with col2:
        st.dataframe(country_counts, hide_index=True, width="stretch")

    # ── Cities ────────────────────────────────────────────────────────────────
    st.subheader("Top Cities")
    if "city" in swarm_df.columns:
        city_counts = (
            swarm_df.groupby(["city", "country"]).size().reset_index(name="Check-ins")
            if "country" in swarm_df.columns
            else swarm_df.groupby("city").size().reset_index(name="Check-ins")
        )
        city_counts = city_counts.sort_values("Check-ins", ascending=False).reset_index(drop=True)
        limit = st.slider("Cities to show", 10, 50, 20)
        fig2 = px.bar(
            city_counts.head(limit),
            x="Check-ins",
            y="city",
            orientation="h",
            color="country" if "country" in city_counts.columns else None,
            title=f"Top {limit} cities",
        )
        fig2.update_layout(yaxis={"categoryorder": "total ascending"})
        apply_dark_theme(fig2)
        st.plotly_chart(fig2, width="stretch")


def render_places() -> None:
    """Render the Places page: 3D geographic listening history map.

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

    render_spatial_analysis(df)
