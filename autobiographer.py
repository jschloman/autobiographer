import argparse
import os
import time
from typing import Callable, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


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
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """Fetch recent tracks for the user.

        Args:
            limit: Tracks per API page (max 200).
            pages: Stop after this many pages; None fetches all.
            from_ts: Unix timestamp lower bound (inclusive).
            to_ts: Unix timestamp upper bound (inclusive).
            progress_callback: Optional callable invoked after each page with
                ``(current_page, total_pages)`` so callers can report progress.
                Also receives ``(0, total_pages)`` before the first page fetch
                once the total is known.

        Returns:
            List of raw track dicts from the Last.fm API.
        """
        all_tracks = []
        current_page = 1
        total_pages = 1

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
            if progress_callback:
                progress_callback(current_page, total_pages)

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


def _parse_date(date_str: str, label: str) -> Optional[int]:
    """Parse a YYYY-MM-DD date string and return a Unix timestamp.

    Args:
        date_str: Date string in YYYY-MM-DD format.
        label: Human-readable label used in error messages (e.g. "from_date").

    Returns:
        Unix timestamp as int, or None if date_str is empty.

    Raises:
        SystemExit: If the date string is not in the expected format.
    """
    if not date_str:
        return None
    try:
        return int(time.mktime(time.strptime(date_str, "%Y-%m-%d")))
    except ValueError as exc:
        print(f"Error: Invalid {label} format '{date_str}'. Use YYYY-MM-DD.")
        raise SystemExit(1) from exc


def _run_list() -> None:
    """Execute the ``list`` subcommand.

    Prints every registered plugin with its display name, type, fetchability,
    and the configuration it requires so users can discover what is available
    and what they need to set up before running ``fetch``.
    """
    from plugins.sources import REGISTRY, load_builtin_plugins

    load_builtin_plugins()

    if not REGISTRY:
        print("No plugins registered.")
        return

    for plugin_id in sorted(REGISTRY):
        plugin = REGISTRY[plugin_id]()
        fetch_label = "auto-fetch" if plugin.FETCHABLE else "manual export"
        print(f"\n{plugin.DISPLAY_NAME} ({plugin_id})  [{plugin.PLUGIN_TYPE} · {fetch_label}]")

        if plugin.FETCHABLE:
            env_vars = plugin.get_fetch_env_vars()
            if env_vars:
                print("  Required environment variables:")
                for v in env_vars:
                    status = "✓" if os.getenv(v["var"]) else "✗ missing"
                    print(f"    {v['var']}  —  {v['description']}  [{status}]")
            print(f"  Fetch command:  python autobiographer.py fetch {plugin_id}")
        else:
            print("  " + plugin.get_manual_download_instructions().replace("\n", "\n  "))


def _run_fetch(args: argparse.Namespace) -> None:
    """Execute the ``fetch`` subcommand.

    Routes to the named plugin's fetch() method if it supports programmatic
    retrieval, or prints manual download instructions if it does not.

    Args:
        args: Parsed CLI arguments including ``plugin``, ``output``, ``pages``,
            ``from_date``, and ``to_date``.
    """
    from plugins.sources import REGISTRY, load_builtin_plugins

    load_builtin_plugins()

    plugin_id: str = args.plugin
    if plugin_id not in REGISTRY:
        available = ", ".join(sorted(REGISTRY))
        print(f"Error: Unknown plugin '{plugin_id}'. Available plugins: {available}")
        raise SystemExit(1)

    plugin = REGISTRY[plugin_id]()

    if not plugin.FETCHABLE:
        print(f"{plugin.DISPLAY_NAME} does not support automatic fetching.\n")
        print(plugin.get_manual_download_instructions())
        return

    # Validate env vars before attempting the fetch.
    env_vars = plugin.get_fetch_env_vars()
    missing = [v for v in env_vars if not os.getenv(v["var"])]
    if missing:
        print("Error: Missing required configuration for fetching. Set the following:\n")
        for v in missing:
            print(f"  {v['var']}: {v['description']}")
        print(
            f"\nThen re-run: python autobiographer.py fetch {plugin_id}\n"
            "See README.md for full configuration instructions."
        )
        raise SystemExit(1)

    from_ts = _parse_date(args.from_date or "", "from_date")
    to_ts_raw = _parse_date(args.to_date or "", "to_date")
    # Shift to-date to end of day so the full day is included.
    to_ts = to_ts_raw + 86399 if to_ts_raw is not None else None

    print(f"Fetching {plugin.DISPLAY_NAME} data...")
    plugin.fetch(
        output_path=args.output or None,
        pages=args.pages,
        from_ts=from_ts,
        to_ts=to_ts,
    )


def main() -> None:
    """Entry point for the Autobiographer data-fetching CLI.

    Subcommands
    -----------
    list
        Print all registered plugins with their fetchability, required
        environment variables, and configuration instructions.
    fetch <plugin>
        Fetch data for the named plugin. For plugins that support programmatic
        retrieval (e.g. ``lastfm``) this downloads and saves data locally.
        For manual-export plugins (e.g. ``swarm``) this prints step-by-step
        instructions for obtaining the data from the provider.

    Examples
    --------
    ::

        python autobiographer.py list
        python autobiographer.py fetch lastfm
        python autobiographer.py fetch lastfm --pages 5
        python autobiographer.py fetch lastfm --from-date 2024-01-01
        python autobiographer.py fetch swarm
    """
    parser = argparse.ArgumentParser(
        description="Autobiographer data-fetching CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    subparsers.add_parser(
        "list",
        help="List all registered plugins with their configuration requirements.",
        description=(
            "Print every registered source plugin with its display name, type, "
            "fetchability, and required environment variables or manual export instructions."
        ),
    )

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch or get instructions for a plugin's data.",
        description=(
            "Fetch data for a registered source plugin. "
            "Plugins that support automatic retrieval will download and save data. "
            "Plugins that require a manual export will print step-by-step instructions."
        ),
    )
    fetch_parser.add_argument(
        "plugin",
        metavar="PLUGIN",
        help="Plugin ID to target (e.g. lastfm, swarm).",
    )
    fetch_parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output file or directory path (overrides the plugin's default location).",
    )
    fetch_parser.add_argument(
        "--pages",
        type=int,
        metavar="N",
        help="Limit to N pages of results (Last.fm only).",
    )
    fetch_parser.add_argument(
        "--from-date",
        dest="from_date",
        metavar="YYYY-MM-DD",
        help="Only fetch records on or after this date.",
    )
    fetch_parser.add_argument(
        "--to-date",
        dest="to_date",
        metavar="YYYY-MM-DD",
        help="Only fetch records on or before this date.",
    )

    args = parser.parse_args()

    if args.command == "fetch":
        _run_fetch(args)
    elif args.command == "list":
        _run_list()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
