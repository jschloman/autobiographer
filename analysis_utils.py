import pandas as pd
import os
import json
import glob
import hashlib
import numpy as np
from typing import Optional, Dict, List, Any
from bisect import bisect_right
from datetime import datetime, timedelta

def get_cache_key(lastfm_file: str, swarm_dir: Optional[str] = None, assumptions_file: Optional[str] = None) -> str:
    """Generate a unique cache key based on input files and their modification times."""
    if not os.path.exists(lastfm_file):
        return "none"
        
    lastfm_mtime = os.path.getmtime(lastfm_file)
    key_parts = [lastfm_file, str(lastfm_mtime)]
    
    if swarm_dir and os.path.isdir(swarm_dir):
        # Sort files to ensure deterministic key
        swarm_files = sorted(glob.glob(os.path.join(swarm_dir, "checkins*.json")))
        for f in swarm_files:
            key_parts.append(f)
            key_parts.append(str(os.path.getmtime(f)))
            
    if assumptions_file and os.path.exists(assumptions_file):
        key_parts.append(assumptions_file)
        key_parts.append(str(os.path.getmtime(assumptions_file)))
            
    # Include version to invalidate cache if logic changes
    key_parts.append("v1.4") 
            
    return hashlib.md5("".join(key_parts).encode()).hexdigest()

def get_cached_data(cache_key: str, cache_dir: str = "data/cache") -> Optional[pd.DataFrame]:
    """Retrieve processed data from cache if it exists."""
    if cache_key == "none":
        return None
        
    cache_path = os.path.join(cache_dir, f"{cache_key}.csv.gz")
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, compression='gzip')
            if 'date_text' in df.columns:
                df['date_text'] = pd.to_datetime(df['date_text'])
            return df
        except Exception:
            pass
    return None

def save_to_cache(df: pd.DataFrame, cache_key: str, cache_dir: str = "data/cache"):
    """Save processed data to cache."""
    if cache_key == "none":
        return
        
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cache_key}.csv.gz")
    try:
        df.to_csv(cache_path, index=False, compression='gzip')
    except Exception as e:
        print(f"Error saving to cache: {e}")

def load_assumptions(assumptions_file: Optional[str]) -> Dict[str, Any]:
    """Load location assumptions from a JSON file."""
    default_data = {
        "defaults": {
            "city": "Reykjavik, IS",
            "state": "IS",
            "country": "Iceland",
            "lat": 64.1265,
            "lng": -21.8174,
            "timezone": "Atlantic/Reykjavik"
        },
        "holidays": [],
        "trips": [],
        "residency": []
    }
    
    if not assumptions_file or not os.path.exists(assumptions_file):
        return default_data
        
    try:
        with open(assumptions_file, 'r') as f:
            user_data = json.load(f)
            # Merge with defaults to ensure all keys exist
            for key in default_data:
                if key not in user_data:
                    user_data[key] = default_data[key]
            return user_data
    except Exception as e:
        print(f"Error loading assumptions: {e}")
        return default_data

def load_listening_data(file_path: str) -> Optional[pd.DataFrame]:
    """Load and preprocess listening history from CSV."""
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_csv(file_path)
        if 'date_text' in df.columns:
            df['date_text'] = pd.to_datetime(df['date_text'])
        
        # Ensure we have a unix timestamp for lookup (Last.fm 'uts')
        if 'timestamp' not in df.columns and 'date_text' in df.columns:
            df['timestamp'] = df['date_text'].astype('int64') // 10**9
            
        return df
    except Exception:
        return None

def load_swarm_data(swarm_dir: str) -> pd.DataFrame:
    """Load and parse Swarm checkin data from JSON files."""
    all_checkins = []
    if not swarm_dir or not os.path.exists(swarm_dir):
        return pd.DataFrame(columns=['timestamp', 'offset', 'city', 'state', 'country', 'venue', 'lat', 'lng'])

    json_files = glob.glob(os.path.join(swarm_dir, "checkins*.json"))
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                items = data.get('items', [])
                for item in items:
                    raw_created_at = item.get('createdAt')
                    if raw_created_at is None:
                        continue
                        
                    try:
                        if isinstance(raw_created_at, (int, float)):
                            created_at = pd.to_datetime(raw_created_at, unit='s', utc=True)
                        else:
                            created_at = pd.to_datetime(raw_created_at, utc=True)
                        ts = int(created_at.timestamp())
                    except (ValueError, TypeError):
                        continue
                        
                    offset = item.get('timeZoneOffset', 0)
                    venue = item.get('venue') or {}
                    location = venue.get('location') or {}
                    
                    city = location.get('city')
                    state = location.get('state')
                    country = location.get('country')
                    
                    if not city:
                        city = state or country or venue.get('name', 'Unknown')
                    if not state:
                        state = country or 'Unknown'
                    if not country:
                        country = 'Unknown'
                        
                    lat = item.get('lat') or location.get('lat')
                    lng = item.get('lng') or location.get('lng')

                    all_checkins.append({
                        'timestamp': ts,
                        'offset': offset,
                        'city': city,
                        'state': state,
                        'country': country,
                        'venue': venue.get('name', 'Unknown'),
                        'lat': lat,
                        'lng': lng
                    })
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            
    if not all_checkins:
        return pd.DataFrame(columns=['timestamp', 'offset', 'city', 'state', 'country', 'venue', 'lat', 'lng'])
        
    df = pd.DataFrame(all_checkins)
    df = df.sort_values('timestamp').drop_duplicates('timestamp')
    return df

def get_assumption_location(ts: int, assumptions: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Get location and offset based on runtime assumptions (Issue #39).
    This is a non-vectorized version mainly used for tests and single lookups.
    """
    dt_utc = pd.to_datetime([ts], unit='s', utc=True)
    
    # Simple recurring holiday check
    for holiday in assumptions.get("holidays", []):
        tz = holiday.get("timezone", "UTC")
        local_time = dt_utc.tz_convert(tz)[0]
        month = holiday.get("month")
        day_range = holiday.get("day_range", [])
        if local_time.month == month and day_range[0] <= local_time.day <= day_range[1]:
            return {
                "offset": int(local_time.utcoffset().total_seconds() / 60),
                "city": holiday.get("city"),
                "state": holiday.get("state", holiday.get("city")),
                "country": holiday.get("country", "Unknown"),
                "lat": holiday.get("lat"),
                "lng": holiday.get("lng")
            }

    # Trip check
    for trip in assumptions.get("trips", []):
        start = pd.to_datetime(trip.get("start")).date()
        end = pd.to_datetime(trip.get("end")).date()
        tz = trip.get("timezone", "UTC")
        local_time = dt_utc.tz_convert(tz)[0]
        if start <= local_time.date() <= end:
            return {
                "offset": int(local_time.utcoffset().total_seconds() / 60),
                "city": trip.get("city"),
                "state": trip.get("state", trip.get("city")),
                "country": trip.get("country", "Unknown"),
                "lat": trip.get("lat"),
                "lng": trip.get("lng")
            }

    # Residency check
    dt_naive = dt_utc[0].replace(tzinfo=None)
    for res in assumptions.get("residency", []):
        start = pd.to_datetime(res.get("start")).replace(tzinfo=None)
        end = pd.to_datetime(res.get("end")).replace(tzinfo=None)
        if start <= dt_naive <= end:
            for rule in res.get("sub_rules", []):
                tz = rule.get("timezone", "UTC")
                local_time = dt_utc.tz_convert(tz)[0]
                cond = rule.get("condition")
                if cond == "work_hours":
                    if local_time.weekday() < 5 and ((local_time.hour == 8 and local_time.minute >= 30) or (9 <= local_time.hour < 16) or (local_time.hour == 16 and local_time.minute <= 30)):
                        return {
                            "offset": int(local_time.utcoffset().total_seconds() / 60),
                            "city": rule.get("city"), 
                            "state": rule.get("state", rule.get("city")),
                            "country": rule.get("country", "Unknown"),
                            "lat": rule.get("lat"), "lng": rule.get("lng")
                        }
                elif cond == "home_logic":
                    home_1_end = pd.to_datetime(rule.get("home_1_end")).replace(tzinfo=None)
                    use_home_1 = dt_naive <= home_1_end
                    return {
                        "offset": int(local_time.utcoffset().total_seconds() / 60),
                        "city": rule.get("city_1") if use_home_1 else rule.get("city_2"),
                        "state": (rule.get("state_1") if use_home_1 else rule.get("state_2")) or (rule.get("city_1") if use_home_1 else rule.get("city_2")),
                        "country": rule.get("country", "Unknown"),
                        "lat": rule.get("lat_1") if use_home_1 else rule.get("lat_2"),
                        "lng": rule.get("lng_1") if use_home_1 else rule.get("lng_2")
                    }
            return {
                "offset": 0, 
                "city": res.get("city"), 
                "state": res.get("state", res.get("city")),
                "country": res.get("country", "Unknown"),
                "lat": res.get("lat"), "lng": res.get("lng")
            }
    return None

def apply_swarm_offsets(lastfm_df: pd.DataFrame, swarm_df: pd.DataFrame, assumptions: Dict[str, Any], max_age_days: int = 30) -> pd.DataFrame:
    """
    Adjust Last.fm track timestamps and locations based on Swarm checkins or runtime assumptions.
    Highly optimized vectorized implementation (Issue #39 optimization).
    """
    if lastfm_df.empty:
        return lastfm_df

    df = lastfm_df.copy()
    defaults = assumptions.get("defaults", {})
    DEFAULT_CITY = defaults.get("city", "Reykjavik")
    DEFAULT_STATE = defaults.get("state", "IS")
    DEFAULT_COUNTRY = defaults.get("country", "Iceland")
    DEFAULT_LAT = defaults.get("lat", 64.1265)
    DEFAULT_LNG = defaults.get("lng", -21.8174)
    DEFAULT_TZ = defaults.get("timezone", "Atlantic/Reykjavik")

    # 1. Pre-calculate UTC timestamps and local variants for checks
    dt_utc = pd.to_datetime(df['timestamp'], unit='s', utc=True)
    
    # Initialize result columns with defaults
    df['tz_offset_min'] = 0 
    df['city'] = DEFAULT_CITY
    df['state'] = DEFAULT_STATE
    df['country'] = DEFAULT_COUNTRY
    df['lat'] = DEFAULT_LAT
    df['lng'] = DEFAULT_LNG
    
    # Track which rows have been geocoded to avoid overwriting
    geocoded_mask = np.zeros(len(df), dtype=bool)

    # 2. Try Swarm Data (Fastest Lookup)
    if not swarm_df.empty:
        swarm_ts = swarm_df['timestamp'].values
        max_age_sec = max_age_days * 24 * 60 * 60
        
        # Use binary search to find the most recent checkin for every track
        indices = np.searchsorted(swarm_ts, df['timestamp'].values, side='right') - 1
        
        # Filter indices that are within range and not too old
        valid_indices_mask = (indices >= 0)
        if valid_indices_mask.any():
            checkin_ts = swarm_ts[indices[valid_indices_mask]]
            age_mask = (df['timestamp'].values[valid_indices_mask] - checkin_ts) <= max_age_sec
            
            final_swarm_mask = valid_indices_mask.copy()
            final_swarm_mask[valid_indices_mask] = age_mask
            
            if final_swarm_mask.any():
                match_indices = indices[final_swarm_mask]
                df.loc[final_swarm_mask, 'tz_offset_min'] = swarm_df['offset'].values[match_indices]
                df.loc[final_swarm_mask, 'city'] = swarm_df['city'].values[match_indices]
                df.loc[final_swarm_mask, 'state'] = swarm_df['state'].values[match_indices]
                df.loc[final_swarm_mask, 'country'] = swarm_df['country'].values[match_indices]
                df.loc[final_swarm_mask, 'lat'] = swarm_df['lat'].values[match_indices]
                df.loc[final_swarm_mask, 'lng'] = swarm_df['lng'].values[match_indices]
                geocoded_mask[final_swarm_mask] = True

    # 3. Apply Runtime Assumptions (Residency, Trips, Holidays)
    remaining_mask = ~geocoded_mask
    if remaining_mask.any():
        # Pre-process trips and residency into datetime objects
        processed_trips = []
        for t in assumptions.get("trips", []):
            t_copy = t.copy()
            t_copy['_start'] = pd.to_datetime(t.get('start')).date()
            t_copy['_end'] = pd.to_datetime(t.get('end')).date()
            processed_trips.append(t_copy)
            
        processed_residency = []
        for r in assumptions.get("residency", []):
            r_copy = r.copy()
            r_copy['_start'] = pd.to_datetime(r.get('start')).replace(tzinfo=None)
            r_copy['_end'] = pd.to_datetime(r.get('end')).replace(tzinfo=None)
            processed_residency.append(r_copy)

        # For efficiency, we'll only compute the local time once per unique timezone used in assumptions
        tz_to_local = {}
        
        # Apply Holidays (recurring)
        for holiday in assumptions.get("holidays", []):
            if not remaining_mask.any(): break
            tz = holiday.get("timezone", "UTC")
            if tz not in tz_to_local:
                tz_to_local[tz] = dt_utc.dt.tz_convert(tz)
            
            local_time = tz_to_local[tz]
            month = holiday.get("month")
            day_range = holiday.get("day_range", [])
            
            holiday_mask = remaining_mask & (local_time.dt.month == month) & \
                           (local_time.dt.day >= day_range[0]) & (local_time.dt.day <= day_range[1])
            
            if holiday_mask.any():
                holiday_offsets = (local_time[holiday_mask].dt.tz_localize(None) - dt_utc[holiday_mask].dt.tz_localize(None)).dt.total_seconds() / 60
                df.loc[holiday_mask, 'tz_offset_min'] = holiday_offsets
                df.loc[holiday_mask, 'city'] = holiday.get("city")
                df.loc[holiday_mask, 'state'] = holiday.get("state", holiday.get("city"))
                df.loc[holiday_mask, 'country'] = holiday.get("country", "Unknown")
                df.loc[holiday_mask, 'lat'] = holiday.get("lat")
                df.loc[holiday_mask, 'lng'] = holiday.get("lng")
                geocoded_mask[holiday_mask] = True
                remaining_mask = ~geocoded_mask

        # Apply Trips
        for trip in processed_trips:
            if not remaining_mask.any(): break
            tz = trip.get("timezone", "UTC")
            if tz not in tz_to_local:
                tz_to_local[tz] = dt_utc.dt.tz_convert(tz)
            
            local_time = tz_to_local[tz]
            local_date = local_time.dt.date
            trip_mask = remaining_mask & (local_date >= trip['_start']) & (local_date <= trip['_end'])
            
            if trip_mask.any():
                trip_offsets = (local_time[trip_mask].dt.tz_localize(None) - dt_utc[trip_mask].dt.tz_localize(None)).dt.total_seconds() / 60
                df.loc[trip_mask, 'tz_offset_min'] = trip_offsets
                df.loc[trip_mask, 'city'] = trip.get("city")
                df.loc[trip_mask, 'state'] = trip.get("state", trip.get("city"))
                df.loc[trip_mask, 'country'] = trip.get("country", "Unknown")
                df.loc[trip_mask, 'lat'] = trip.get("lat")
                df.loc[trip_mask, 'lng'] = trip.get("lng")
                geocoded_mask[trip_mask] = True
                remaining_mask = ~geocoded_mask

        # Apply Residency (with sub-rules)
        dt_naive = dt_utc.dt.tz_localize(None)
        for res in processed_residency:
            if not remaining_mask.any(): break
            res_mask = remaining_mask & (dt_naive >= res['_start']) & (dt_naive <= res['_end'])
            
            if res_mask.any():
                # Apply sub-rules within this residency period
                res_remaining = res_mask.copy()
                for rule in res.get("sub_rules", []):
                    if not res_remaining.any(): break
                    tz = rule.get("timezone", "UTC")
                    if tz not in tz_to_local:
                        tz_to_local[tz] = dt_utc.dt.tz_convert(tz)
                    
                    local_time = tz_to_local[tz]
                    cond = rule.get("condition")
                    
                    if cond == "work_hours":
                        # Mon-Fri, 8:30 - 16:30
                        work_mask = res_remaining & (local_time.dt.weekday < 5) & (
                            ((local_time.dt.hour == 8) & (local_time.dt.minute >= 30)) |
                            ((local_time.dt.hour >= 9) & (local_time.dt.hour < 16)) |
                            ((local_time.dt.hour == 16) & (local_time.dt.minute <= 30))
                        )
                        if work_mask.any():
                            work_offsets = (local_time[work_mask].dt.tz_localize(None) - dt_utc[work_mask].dt.tz_localize(None)).dt.total_seconds() / 60
                            df.loc[work_mask, 'tz_offset_min'] = work_offsets
                            df.loc[work_mask, 'city'] = rule.get("city")
                            df.loc[work_mask, 'state'] = rule.get("state", rule.get("city"))
                            df.loc[work_mask, 'country'] = rule.get("country", "Unknown")
                            df.loc[work_mask, 'lat'] = rule.get("lat")
                            df.loc[work_mask, 'lng'] = rule.get("lng")
                            geocoded_mask[work_mask] = True
                            res_remaining &= ~work_mask
                    
                    elif cond == "home_logic":
                        home_1_end = pd.to_datetime(rule.get("home_1_end")).replace(tzinfo=None)
                        h1_mask = res_remaining & (dt_naive <= home_1_end)
                        h2_mask = res_remaining & (dt_naive > home_1_end)
                        
                        if h1_mask.any():
                            h1_offsets = (local_time[h1_mask].dt.tz_localize(None) - dt_utc[h1_mask].dt.tz_localize(None)).dt.total_seconds() / 60
                            df.loc[h1_mask, 'tz_offset_min'] = h1_offsets
                            df.loc[h1_mask, 'city'] = rule.get("city_1")
                            df.loc[h1_mask, 'state'] = rule.get("state_1", rule.get("city_1"))
                            df.loc[h1_mask, 'country'] = rule.get("country", "Unknown")
                            df.loc[h1_mask, 'lat'] = rule.get("lat_1")
                            df.loc[h1_mask, 'lng'] = rule.get("lng_1")
                            geocoded_mask[h1_mask] = True
                        if h2_mask.any():
                            h2_offsets = (local_time[h2_mask].dt.tz_localize(None) - dt_utc[h2_mask].dt.tz_localize(None)).dt.total_seconds() / 60
                            df.loc[h2_mask, 'tz_offset_min'] = h2_offsets
                            df.loc[h2_mask, 'city'] = rule.get("city_2")
                            df.loc[h2_mask, 'state'] = rule.get("state_2", rule.get("city_2"))
                            df.loc[h2_mask, 'country'] = rule.get("country", "Unknown")
                            df.loc[h2_mask, 'lat'] = rule.get("lat_2")
                            df.loc[h2_mask, 'lng'] = rule.get("lng_2")
                            geocoded_mask[h2_mask] = True
                        res_remaining &= ~(h1_mask | h2_mask)

                # Final fallback for residency if no sub-rules matched
                if res_remaining.any():
                    df.loc[res_remaining, 'tz_offset_min'] = 0 # Default offset
                    df.loc[res_remaining, 'city'] = res.get("city")
                    df.loc[res_remaining, 'state'] = res.get("state", res.get("city"))
                    df.loc[res_remaining, 'country'] = res.get("country", "Unknown")
                    df.loc[res_remaining, 'lat'] = res.get("lat")
                    df.loc[res_remaining, 'lng'] = res.get("lng")
                    geocoded_mask[res_remaining] = True
                
                remaining_mask = ~geocoded_mask

    # 4. Final Default (remaining tracks)
    remaining_mask = ~geocoded_mask
    if remaining_mask.any():
        # Compute default timezone once for all remaining
        default_local = dt_utc[remaining_mask].dt.tz_convert(DEFAULT_TZ)
        default_offsets = (default_local.dt.tz_localize(None) - dt_utc[remaining_mask].dt.tz_localize(None)).dt.total_seconds() / 60
        df.loc[remaining_mask, 'tz_offset_min'] = default_offsets
        df.loc[remaining_mask, 'city'] = DEFAULT_CITY
        df.loc[remaining_mask, 'state'] = DEFAULT_STATE
        df.loc[remaining_mask, 'country'] = DEFAULT_COUNTRY
        df.loc[remaining_mask, 'lat'] = DEFAULT_LAT
        df.loc[remaining_mask, 'lng'] = DEFAULT_LNG

    # Apply the computed offsets to date_text
    df['local_date'] = pd.to_datetime(df['timestamp'], unit='s') + pd.to_timedelta(df['tz_offset_min'], unit='m')
    df['original_date_text'] = df['date_text']
    df['date_text'] = df['local_date']
    
    return df

def get_top_entities(df: pd.DataFrame, entity: str = 'artist', limit: int = 10) -> pd.DataFrame:
    """Get the top n most played entities (artist, album, track)."""
    if entity not in df.columns:
        return pd.DataFrame()
    top = df[entity].value_counts().head(limit).reset_index()
    top.columns = [entity, 'Plays']
    return top

def get_unique_entities(subset_df: pd.DataFrame, full_df: pd.DataFrame, entity: str = 'artist', limit: int = 10) -> pd.DataFrame:
    """
    Identify entities that are uniquely prominent in the subset compared to the full dataset.
    Uses a simple 'Over-representation' score: (Subset Frequency / Total Frequency).
    """
    if subset_df.empty or full_df.empty or entity not in full_df.columns:
        return pd.DataFrame()
        
    subset_counts = subset_df[entity].value_counts()
    full_counts = full_df[entity].value_counts()
    
    # Filter to only entities present in subset
    relevant_full = full_counts[subset_counts.index]
    
    # Score = (subset count) / (total count)
    # This favors entities that appear ONLY in this subset
    scores = subset_counts / relevant_full
    
    unique_data = pd.DataFrame({
        entity: scores.index,
        'Uniqueness': scores.values,
        'Plays': subset_counts.values
    }).sort_values('Uniqueness', ascending=False).head(limit)
    
    return unique_data

def get_listening_intensity(df: pd.DataFrame, freq: str = 'D') -> pd.DataFrame:
    """Calculate play counts per specified frequency ('D' for day, 'W' for week, 'ME' for month)."""
    if 'date_text' not in df.columns or df.empty:
        return pd.DataFrame()
    df_copy = df.copy()
    df_copy['date_group'] = df_copy['date_text'].dt.to_period(freq).dt.to_timestamp()
    intensity = df_copy.groupby('date_group').size().reset_index(name='Plays')
    intensity.rename(columns={'date_group': 'date'}, inplace=True)
    return intensity

def get_milestones(df: pd.DataFrame, intervals: List[int] = [1000, 5000, 10000, 50000]) -> pd.DataFrame:
    """Find tracks that hit specific volume milestones."""
    if df.empty:
        return pd.DataFrame()
    df_sorted = df.sort_values('date_text').reset_index(drop=True)
    milestones = []
    for interval in intervals:
        if len(df_sorted) >= interval:
            track = df_sorted.iloc[interval - 1]
            milestones.append({
                'Milestone': f"{interval:,} Tracks",
                'Artist': track['artist'],
                'Track': track['track'],
                'Date': track['date_text']
            })
    return pd.DataFrame(milestones)

def get_listening_streaks(df: pd.DataFrame) -> Dict:
    """Find the longest streak of consecutive days with at least one play."""
    if df.empty:
        return {'longest_streak': 0, 'current_streak': 0}
    
    dates = pd.to_datetime(df['date_text']).dt.date.unique()
    dates = sorted(dates)
    
    if not dates:
        return {'longest_streak': 0, 'current_streak': 0}
        
    longest = 1
    current = 1
    
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            current += 1
        else:
            longest = max(longest, current)
            current = 1
    
    longest = max(longest, current)
    today = pd.Timestamp.now().date()
    is_active = (today - dates[-1]).days <= 1
    
    return {
        'longest_streak': longest,
        'current_streak': current if is_active else 0,
        'last_active': dates[-1]
    }

def get_forgotten_favorites(df: pd.DataFrame, top_n: int = 10, months_threshold: int = 6) -> pd.DataFrame:
    """Identify artists that were once favorites but haven't been heard recently."""
    if df.empty:
        return pd.DataFrame()
        
    latest_date = df['date_text'].max()
    threshold_date = latest_date - pd.DateOffset(months=months_threshold)
    
    past_df = df[df['date_text'] < threshold_date]
    recent_df = df[df['date_text'] >= threshold_date]
    
    if past_df.empty:
        return pd.DataFrame()
        
    past_top = past_df['artist'].value_counts().head(top_n * 2)
    recent_artists = set(recent_df['artist'].unique())
    
    forgotten = []
    for artist, count in past_top.items():
        if artist not in recent_artists:
            forgotten.append({'Artist': artist, 'Past Plays': count})
            if len(forgotten) >= top_n:
                break
                
    return pd.DataFrame(forgotten)

def get_cumulative_plays(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate cumulative plays over time."""
    if 'date_text' not in df.columns or df.empty:
        return pd.DataFrame()
    df_copy = df.sort_values('date_text')
    df_copy['date'] = df_copy['date_text'].dt.date
    daily = df_copy.groupby('date').size().reset_index(name='DailyPlays')
    daily['CumulativePlays'] = daily['DailyPlays'].cumsum()
    return daily

def get_hourly_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate the distribution of plays throughout the hours of the day."""
    if 'date_text' not in df.columns:
        return pd.DataFrame()
    df_copy = df.copy()
    df_copy['hour'] = df_copy['date_text'].dt.hour
    hourly = df_copy.groupby('hour').size().reset_index(name='Plays')
    return hourly
