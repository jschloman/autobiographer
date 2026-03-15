import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import os
import io
import geopandas as gpd
from shapely.geometry import Point
from analysis_utils import (
    load_listening_data, 
    get_top_entities, 
    get_unique_entities,
    get_listening_intensity, 
    get_cumulative_plays,
    get_hourly_distribution,
    get_milestones,
    get_listening_streaks,
    get_forgotten_favorites,
    get_cache_key,
    get_cached_data,
    save_to_cache,
    load_assumptions,
    load_swarm_data,
    apply_swarm_offsets
)

def render_spatial_analysis(df: pd.DataFrame):
    """Render 3D geographical visualization of listening history."""
    st.header("Spatial Music Explorer")
    
    if 'lat' not in df.columns or df['lat'].isna().all():
        st.warning("No geographic data found. Please provide a Swarm data directory to enable this view.")
        return

    # Sidebar-like filters within the tab for artist and timeframe
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        artists = ["All"] + sorted(df['artist'].dropna().unique().tolist())
        selected_artist = st.selectbox("Filter by Artist", artists)
    with col_f2:
        min_date = df['date_text'].min().date()
        max_date = df['date_text'].max().date()
        date_range = st.date_input("Filter by Date Range", [min_date, max_date], key="spatial_date_range")

    # Filter data
    map_df = df.copy()
    if selected_artist != "All":
        map_df = map_df[map_df['artist'] == selected_artist]
    
    if len(date_range) == 2:
        map_df = map_df[(map_df['date_text'].dt.date >= date_range[0]) & 
                        (map_df['date_text'].dt.date <= date_range[1])]

    if map_df.empty:
        st.info("No data matches the selected filters.")
        return

    # Aggregate by location
    geo_data = map_df.groupby(['lat', 'lng', 'city']).size().reset_index(name='Plays')
    
    # Initialize view state in session state if not present
    if "spatial_view_state" not in st.session_state:
        st.session_state.spatial_view_state = pdk.ViewState(
            latitude=geo_data['lat'].mean(),
            longitude=geo_data['lng'].mean(),
            zoom=3,
            pitch=45,
            bearing=0
        )

    # Map control sliders
    col_a, col_b, col_c = st.columns(3)
    
    # Robustly get current values from view state
    def get_view_val(attr, default):
        val = getattr(st.session_state.spatial_view_state, attr, default)
        return float(val) if val is not None else float(default)

    with col_a:
        zoom_level = st.slider(
            "Map Zoom", 
            min_value=1.0, 
            max_value=15.0, 
            value=get_view_val('zoom', 3.0),
            step=0.5,
            key="zoom_slider"
        )
    with col_b:
        bearing = st.slider(
            "Rotation",
            min_value=-180.0,
            max_value=180.0,
            value=get_view_val('bearing', 0.0),
            step=5.0,
            key="bearing_slider"
        )
    with col_c:
        pitch = st.slider(
            "Tilt",
            min_value=0.0,
            max_value=90.0,
            value=get_view_val('pitch', 45.0),
            step=5.0,
            key="pitch_slider"
        )
        
    # Update the session state
    st.session_state.spatial_view_state.zoom = zoom_level
    st.session_state.spatial_view_state.bearing = bearing
    st.session_state.spatial_view_state.pitch = pitch

    # Cinematic Fly-through
    st.subheader("Cinematic Fly-through")
    fly_col1, fly_col2 = st.columns([1, 3])
    with fly_col1:
        if st.button("🎬 Play Fly-through"):
            # Get top 5 cities for the tour
            top_cities = geo_data.sort_values('Plays', ascending=False).head(5)
            # Add a "World View" at the end
            keyframes = []
            for _, row in top_cities.iterrows():
                keyframes.append({
                    "lat": row['lat'], "lng": row['lng'], 
                    "zoom": 12, "pitch": 60, "bearing": 30
                })
            # Add global view
            keyframes.append({
                "lat": geo_data['lat'].mean(), "lng": geo_data['lng'].mean(),
                "zoom": 2, "pitch": 0, "bearing": 0
            })
            
            st.session_state.fly_keyframes = keyframes
            st.session_state.fly_index = 0
            st.rerun()

    with fly_col2:
        # Issue: Export Recording HTML directly from UI
        if st.button("💾 Export Recording HTML"):
            import json
            # Use top 8 for export
            top_cities = geo_data.sort_values('Plays', ascending=False).head(8)
            export_keyframes = []
            # Start wide
            export_keyframes.append({
                "latitude": geo_data['lat'].mean(), "longitude": geo_data['lng'].mean(),
                "zoom": 2, "pitch": 0, "bearing": 0, "duration": 2000
            })
            for _, row in top_cities.iterrows():
                export_keyframes.append({
                    "latitude": row['lat'], "longitude": row['lng'], 
                    "zoom": 11, "pitch": 60, "bearing": 45, "duration": 4000
                })
            # End wide
            export_keyframes.append({
                "latitude": geo_data['lat'].mean(), "longitude": geo_data['lng'].mean(),
                "zoom": 3, "pitch": 45, "bearing": 0, "duration": 4000
            })

            # Create the deck for export
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
                    latitude=export_keyframes[0]['latitude'],
                    longitude=export_keyframes[0]['longitude'],
                    zoom=export_keyframes[0]['zoom']
                ),
                map_style="light"
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
                label="📥 Download Fly-through HTML",
                data=html_content,
                file_name="music_flythrough.html",
                mime="text/html"
            )

    if "fly_keyframes" in st.session_state and st.session_state.fly_index < len(st.session_state.fly_keyframes):
        kf = st.session_state.fly_keyframes[st.session_state.fly_index]
        # Set transition on the view state
        st.session_state.spatial_view_state = pdk.ViewState(
            latitude=kf['lat'],
            longitude=kf['lng'],
            zoom=kf['zoom'],
            pitch=kf['pitch'],
            bearing=kf['bearing'],
            transition_duration=3000,
            transition_interp='FLY_TO'
        )
        st.session_state.fly_index += 1
        import time
        time.sleep(3.2)
        st.rerun()
    elif "fly_keyframes" in st.session_state:
        # Cleanup
        del st.session_state.fly_keyframes
        del st.session_state.fly_index
        st.success("Fly-through complete!")

    # Color Spectrum Implementation
    def get_spectrum_color(val, max_val):
        if max_val == 0: return [236, 226, 240, 200]
        ratio = val / max_val
        if ratio < 0.5:
            r = 236 + (166 - 236) * (ratio * 2)
            g = 226 + (189 - 226) * (ratio * 2)
            b = 240 + (219 - 240) * (ratio * 2)
        else:
            r = 166 + (28 - 166) * ((ratio - 0.5) * 2)
            g = 189 + (144 - 189) * ((ratio - 0.5) * 2)
            b = 219 + (153 - 219) * ((ratio - 0.5) * 2)
        return [int(r), int(g), int(b), 220]

    # Calculate radius based on zoom (balanced to maintain visual size)
    dynamic_radius = (50000 / (2 ** (zoom_level - 1)))

    import numpy as np
    geo_data['elevation_log'] = np.log1p(geo_data['Plays'])
    max_log = geo_data['elevation_log'].max()
    
    # Scale log elevation to maintain a 7:1 height-to-width ratio for the tallest marker.
    geo_data['elevation'] = (geo_data['elevation_log'] / max_log) * (1.4 * dynamic_radius) if max_log > 0 else 0
    geo_data['color'] = geo_data['elevation_log'].apply(lambda x: get_spectrum_color(x, max_log))

    # Process Map Highlights
    @st.cache_data
    def get_highlighted_map(geo_points_json):
        countries_path = os.path.join("assets", "countries.geojson")
        states_path = os.path.join("assets", "states.geojson")
        if not os.path.exists(countries_path):
            return None, None
        world = gpd.read_file(countries_path)
        points_df = pd.read_json(io.StringIO(geo_points_json))
        geometry = [Point(xy) for xy in zip(points_df.lng, points_df.lat)]
        points_gpd = gpd.GeoDataFrame(points_df, geometry=geometry, crs="EPSG:4326")
        countries_with_points = gpd.sjoin(world, points_gpd, how="inner", predicate="intersects")
        def country_color_logic(country_idx):
            if country_idx in countries_with_points.index:
                return [166, 189, 219, 130] 
            return [240, 240, 240, 30]
        world['fill_color'] = world.index.map(country_color_logic)
        return world, states_path

    world_gdf, states_geojson_path = get_highlighted_map(geo_data.to_json())

    layers = []
    if world_gdf is not None:
        layers.append(pdk.Layer("GeoJsonLayer", world_gdf, stroked=True, filled=True, get_fill_color="fill_color", get_line_color=[100, 100, 100], get_line_width=1))
    if states_geojson_path and os.path.exists(states_geojson_path):
        layers.append(pdk.Layer("GeoJsonLayer", states_geojson_path, stroked=True, filled=False, get_line_color=[150, 150, 150, 100], get_line_width=1))

    layers.extend([
        pdk.Layer("ScatterplotLayer", geo_data, get_position=["lng", "lat"], get_fill_color="color", radius=dynamic_radius * 1.2, pickable=True),
        pdk.Layer("ColumnLayer", geo_data, get_position=["lng", "lat"], get_elevation="elevation", elevation_scale=10, radius=dynamic_radius, get_fill_color="color", pickable=True, auto_highlight=True)
    ])

    r = pdk.Deck(layers=layers, initial_view_state=st.session_state.spatial_view_state, tooltip={"text": "{city}: {Plays} plays"}, map_style="light")
    st.pydeck_chart(r, key="spatial_map")
    
    st.markdown("""
    **Map Navigation Gestures:**
    - **Pan**: Left-click and drag.
    - **Rotate/Tilt**: Right-click and drag (or use the sliders above).
    - **Zoom**: Mouse wheel or pinch gesture.
    """)
    
    st.dataframe(geo_data.sort_values('Plays', ascending=False), hide_index=True)

def render_top_charts(df: pd.DataFrame):
    """Render top entity charts with toggle."""
    st.header("Top Charts")
    entity_type = st.radio("Select chart type", ["artist", "album", "track"], horizontal=True)
    limit = st.slider(f"Top {entity_type.capitalize()}s to show", 5, 50, 10)
    top_data = get_top_entities(df, entity_type, limit=limit)
    col1, col2 = st.columns([2, 1])
    with col1:
        fig_bar = px.bar(top_data, x='Plays', y=entity_type, orientation='h', title=f"Top {limit} {entity_type.capitalize()}s")
        fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_bar, width='stretch')
    with col2:
        fig_pie = px.pie(top_data.head(10), values='Plays', names=entity_type, title=f"Market Share (Top 10)")
        st.plotly_chart(fig_pie, width='stretch')

def render_timeline_analysis(df: pd.DataFrame):
    """Render various timeline and activity charts."""
    st.header("Activity Over Time")
    freq_map = {"Daily": "D", "Weekly": "W", "Monthly": "ME"}
    freq_label = st.selectbox("Select grouping frequency", list(freq_map.keys()))
    intensity = get_listening_intensity(df, freq_map[freq_label])
    fig_intensity = px.line(intensity, x='date', y='Plays', title=f"Plays per {freq_label}")
    st.plotly_chart(fig_intensity, width='stretch')
    st.subheader("Cumulative Growth")
    cumulative = get_cumulative_plays(df)
    fig_cumulative = px.area(cumulative, x='date', y='CumulativePlays', title="Total Plays Growth")
    st.plotly_chart(fig_cumulative, width='stretch')

def render_insights_and_narrative(df: pd.DataFrame):
    """Merged tab for Patterns, Narrative, and granular filtering."""
    st.header("Insights & Narrative")
    
    # Granular Filters (Issue #41)
    st.subheader("Explore Patterns by Time & Location")
    
    # Prepare filter options
    years = ["All"] + sorted(df['date_text'].dt.year.unique().astype(str).tolist(), reverse=True)
    months = ["All"] + list(range(1, 13))
    countries = ["All"] + sorted(df['country'].unique().tolist())
    states = ["All"] + sorted(df['state'].unique().tolist())
    
    col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)
    with col_filter1:
        selected_year = st.selectbox("Year", years)
    with col_filter2:
        selected_month = st.selectbox("Month", months)
    with col_filter3:
        selected_country = st.selectbox("Country", countries)
    with col_filter4:
        selected_state = st.selectbox("State", states)
        
    # Apply filters to a local copy for analysis
    filtered_df = df.copy()
    if selected_year != "All":
        filtered_df = filtered_df[filtered_df['date_text'].dt.year == int(selected_year)]
    if selected_month != "All":
        filtered_df = filtered_df[filtered_df['date_text'].dt.month == int(selected_month)]
    if selected_country != "All":
        filtered_df = filtered_df[filtered_df['country'] == selected_country]
    if selected_state != "All":
        filtered_df = filtered_df[filtered_df['state'] == selected_state]
        
    if filtered_df.empty:
        st.warning("No data found for the selected granular filters.")
    else:
        # 1. Top & Unique Analysis (Issue #41)
        col_top1, col_top2 = st.columns(2)
        
        with col_top1:
            st.markdown(f"### Top Artists & Tracks")
            tabs_top = st.tabs(["Artists", "Tracks", "Albums"])
            with tabs_top[0]:
                st.dataframe(get_top_entities(filtered_df, 'artist'), hide_index=True, width='stretch')
            with tabs_top[1]:
                st.dataframe(get_top_entities(filtered_df, 'track'), hide_index=True, width='stretch')
            with tabs_top[2]:
                st.dataframe(get_top_entities(filtered_df, 'album'), hide_index=True, width='stretch')
                
        with col_top2:
            st.markdown(f"### Most Unique to this Selection")
            st.caption("Entities that are more characteristic of this filter compared to your overall history.")
            tabs_unique = st.tabs(["Artists", "Tracks"])
            with tabs_unique[0]:
                unique_artists = get_unique_entities(filtered_df, df, 'artist')
                if not unique_artists.empty:
                    st.dataframe(unique_artists, hide_index=True, width='stretch')
                else:
                    st.info("Not enough data for uniqueness score.")
            with tabs_unique[1]:
                unique_tracks = get_unique_entities(filtered_df, df, 'track')
                if not unique_tracks.empty:
                    st.dataframe(unique_tracks, hide_index=True, width='stretch')
                else:
                    st.info("Not enough data for uniqueness score.")

        # 2. Listening Patterns (Original Patterns tab)
        st.markdown("---")
        st.subheader("Time-based Patterns")
        col_pat1, col_pat2 = st.columns(2)
        with col_pat1:
            hourly = get_hourly_distribution(filtered_df)
            fig_hourly = px.bar(hourly, x='hour', y='Plays', title="Listening by Hour of Day")
            st.plotly_chart(fig_hourly, width='stretch')
        with col_pat2:
            df_copy = filtered_df.copy()
            df_copy['day_of_week'] = df_copy['date_text'].dt.day_name()
            df_copy['hour'] = df_copy['date_text'].dt.hour
            heatmap_data = df_copy.groupby(['day_of_week', 'hour']).size().reset_index(name='Plays')
            days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            heatmap_data['day_of_week'] = pd.Categorical(heatmap_data['day_of_week'], categories=days_order, ordered=True)
            heatmap_pivot = heatmap_data.pivot(index='day_of_week', columns='hour', values='Plays').fillna(0)
            fig_heatmap = px.imshow(heatmap_pivot, labels=dict(x="Hour of Day", y="Day of Week", color="Plays"), title="Listening Intensity (Day vs Hour)", aspect="auto")
            st.plotly_chart(fig_heatmap, width='stretch')

    # 3. Narrative Elements (Original Narrative tab)
    st.markdown("---")
    st.subheader("Autobiographical Narrative")
    col_nar1, col_nar2 = st.columns(2)
    with col_nar1:
        st.markdown("#### Milestones")
        milestones = get_milestones(filtered_df)
        if not milestones.empty:
            st.dataframe(milestones, hide_index=True, width='stretch')
        else:
            st.info("No major milestones in this selection.")
    with col_nar2:
        st.markdown("#### Listening Streaks")
        streaks = get_listening_streaks(filtered_df)
        st.metric("Longest Streak", f"{streaks['longest_streak']} days")
        st.metric("Current Streak", f"{streaks['current_streak']} days")
        
    st.markdown("#### Forgotten Favorites")
    st.write("Artists you loved overall but haven't heard in this period (or recently):")
    forgotten = get_forgotten_favorites(filtered_df) if not filtered_df.empty else pd.DataFrame()
    if not forgotten.empty:
        st.dataframe(forgotten, hide_index=True)
    else:
        st.info("No forgotten favorites identified.")

def main():
    st.set_page_config(page_title="Autobiographer", layout="wide")
    st.title("Autobiographer: Interactive Data Explorer")
    
    # Issue 21: Support custom data directory
    default_data_dir = os.getenv("AUTOBIO_LASTFM_DATA_DIR", "data")
    
    st.sidebar.header("Data Sources")
    data_dir = st.sidebar.text_input("Last.fm Data Directory", default_data_dir)
    
    if not os.path.exists(data_dir):
        st.error(f"Data directory '{data_dir}' not found.")
        return
        
    files = [f for f in os.listdir(data_dir) if f.endswith("_tracks.csv")]
    if not files:
        st.warning(f"No tracking data found in {data_dir}.")
        return
        
    selected_file = st.sidebar.selectbox("Select a data file", files)
    file_path = os.path.join(data_dir, selected_file)
    
    # Issue 20: Support Swarm data directory
    default_swarm_dir = os.getenv("AUTOBIO_SWARM_DIR", "")
    swarm_dir = st.sidebar.text_input("Swarm Data Directory (Optional)", default_swarm_dir)
    
    # Issue 39: Runtime Assumptions
    default_assumptions_path = os.getenv("AUTOBIO_ASSUMPTIONS_FILE", "default_assumptions.json")
    assumptions_path = st.sidebar.text_input("Location Assumptions File (JSON)", default_assumptions_path)
    assumptions = load_assumptions(assumptions_path)
    
    # Issue 37: Data Caching
    st.sidebar.header("Cache Management")
    cache_key = get_cache_key(file_path, swarm_dir, assumptions_path)
    df = get_cached_data(cache_key)
    
    if df is None:
        df = load_listening_data(file_path)
        if df is not None:
            # Apply Swarm offsets and assumptions
            with st.spinner("Adjusting timezones and geocoding..."):
                swarm_df = load_swarm_data(swarm_dir) if swarm_dir and os.path.exists(swarm_dir) else pd.DataFrame()
                df = apply_swarm_offsets(df, swarm_df, assumptions)
                
                if not swarm_df.empty:
                    st.sidebar.success(f"Applied offsets from {len(swarm_df)} checkins.")
                elif os.path.exists(assumptions_path):
                    st.sidebar.info("Applied location assumptions from file.")
                else:
                    st.sidebar.warning("No Swarm or assumptions found; using Reykjavik default.")
            
            # Save to cache
            save_to_cache(df, cache_key)
            st.sidebar.info("Data processed and cached locally.")
    else:
        st.sidebar.success("Loaded from local cache.")

    if st.sidebar.button("🗑️ Clear Local Cache"):
        cache_dir = "data/cache"
        if os.path.exists(cache_dir):
            import shutil
            shutil.rmtree(cache_dir)
            st.sidebar.success("Cache cleared!")
            st.rerun()
    
    if df is not None:
        # Global Filters
        st.sidebar.header("Global Filters")
        min_date = df['date_text'].min().date()
        max_date = df['date_text'].max().date()
        date_range = st.sidebar.date_input("Filter by Date Range", [min_date, max_date])

        if len(date_range) == 2:
            df = df[(df['date_text'].dt.date >= date_range[0]) & 
                    (df['date_text'].dt.date <= date_range[1])]

        if df.empty:
            st.warning("No data found for the selected date range.")
            return

        tabs = st.tabs(["Overview", "Timeline", "Spatial", "Insights & Narrative"])
        
        with tabs[0]:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Tracks", len(df))
            col2.metric("Unique Artists", df['artist'].nunique())
            col3.metric("Unique Albums", df['album'].nunique())
            render_top_charts(df)
            
        with tabs[1]:
            render_timeline_analysis(df)
            
        with tabs[2]:
            render_spatial_analysis(df)
            
        with tabs[3]:
            render_insights_and_narrative(df)
    else:
        st.error("Failed to load data.")

if __name__ == "__main__":
    main()


