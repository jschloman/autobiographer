import argparse
import os
import time
from typing import Optional

import pandas as pd
import requests


class Autobiographer:
    BASE_URL = "http://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: str, api_secret: str, username: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.username = username

    def _fetch_page(self, method: str, params: dict) -> dict:
        """Helper to fetch a single page from Last.fm API."""
        params.update(
            {"method": method, "api_key": self.api_key, "format": "json", "user": self.username}
        )
        response = requests.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def fetch_recent_tracks(
        self,
        limit: int = 200,
        pages: Optional[int] = None,
        from_ts: Optional[int] = None,
        to_ts: Optional[int] = None,
    ) -> list[dict]:
        """Fetch recent tracks for the user."""
        all_tracks = []
        current_page = 1

        while True:
            print(f"Fetching page {current_page}...")
            params = {"limit": limit, "page": current_page}
            if from_ts:
                params["from"] = from_ts
            if to_ts:
                params["to"] = to_ts

            data = self._fetch_page("user.getrecenttracks", params)

            tracks = data.get("recenttracks", {}).get("track", [])
            if not tracks:
                break

            # Filter out currently playing track if any
            tracks = [t for t in tracks if not t.get("@attr", {}).get("nowplaying") == "true"]
            all_tracks.extend(tracks)

            total_pages = int(data.get("recenttracks", {}).get("@attr", {}).get("totalPages", 1))
            if pages and current_page >= pages:
                break
            if current_page >= total_pages:
                break

            current_page += 1
            time.sleep(0.25)  # Rate limiting

        return all_tracks

    def save_tracks_to_csv(self, tracks: list[dict], filename: Optional[str] = None) -> None:
        """Clean and save tracks to a CSV file."""
        if not filename:
            filename = f"data/lastfm_{self.username}_tracks.csv"

        flat_data = []
        for track in tracks:
            flat_data.append(
                {
                    "artist": track.get("artist", {}).get("#text"),
                    "album": track.get("album", {}).get("#text"),
                    "track": track.get("name"),
                    "timestamp": track.get("date", {}).get("uts"),
                    "date_text": track.get("date", {}).get("#text"),
                }
            )

        df = pd.DataFrame(flat_data)
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        df.to_csv(filename, index=False)
        print(f"Saved {len(df)} tracks to {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Last.fm listening history.")
    parser.add_argument(
        "--user", help="Last.fm username (defaults to AUTOBIO_LASTFM_USERNAME env var)"
    )
    parser.add_argument("--pages", type=int, help="Limit number of pages to fetch")
    parser.add_argument("--from_date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to_date", help="End date (YYYY-MM-DD)")

    args = parser.parse_args()

    api_key = os.getenv("AUTOBIO_LASTFM_API_KEY")
    api_secret = os.getenv("AUTOBIO_LASTFM_API_SECRET")
    username = args.user or os.getenv("AUTOBIO_LASTFM_USERNAME")

    if not all([api_key, api_secret, username]):
        print(
            "Error: AUTOBIO_LASTFM_API_KEY, AUTOBIO_LASTFM_API_SECRET, and "
            "AUTOBIO_LASTFM_USERNAME must be set."
        )
        return

    from_ts = None
    if args.from_date:
        try:
            # Beginning of the day
            from_ts = int(time.mktime(time.strptime(args.from_date, "%Y-%m-%d")))
        except ValueError:
            print(f"Error: Invalid from_date format '{args.from_date}'. Use YYYY-MM-DD.")
            return

    to_ts = None
    if args.to_date:
        try:
            # End of the day (23:59:59)
            to_struct = time.strptime(args.to_date, "%Y-%m-%d")
            to_ts = int(time.mktime(to_struct)) + 86399
        except ValueError:
            print(f"Error: Invalid to_date format '{args.to_date}'. Use YYYY-MM-DD.")
            return

    if not api_key or not api_secret or not username:
        return
    visualizer = Autobiographer(api_key, api_secret, username)
    tracks = visualizer.fetch_recent_tracks(pages=args.pages, from_ts=from_ts, to_ts=to_ts)
    visualizer.save_tracks_to_csv(tracks)


if __name__ == "__main__":
    main()
