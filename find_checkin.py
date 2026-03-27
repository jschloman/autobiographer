from __future__ import annotations

import argparse
import glob
import json
import os


def find_checkins(swarm_dir: str, pattern: str) -> list[tuple]:
    """Find check-ins matching a pattern in the given directory."""
    if not os.path.exists(swarm_dir):
        return []

    json_files = glob.glob(os.path.join(swarm_dir, "checkins*.json"))
    found = []

    for file_path in json_files:
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("items", [])
                for item in items:
                    venue_name = item.get("venue", {}).get("name", "")
                    if pattern.lower() in venue_name.lower():
                        created_at = item.get("createdAt")
                        found.append((created_at, venue_name))
        except Exception as e:
            print(f"Warning: failed to parse {file_path}: {e}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Find specific Swarm check-ins.")
    parser.add_argument(
        "--dir",
        default=r"G:\My Drive\Projects\Swarm Foursquare JFS 2026-02",
        help="Swarm data directory",
    )
    parser.add_argument(
        "--pattern", default="Holiday Inn Express Fremont", help="Venue name pattern to search for"
    )

    args = parser.parse_args()

    results = find_checkins(args.dir, args.pattern)

    if results:
        print(f"Found {len(results)} check-ins for '{args.pattern}':")
        for dt, name in sorted(results):
            print(f"  - {dt}: {name}")
    else:
        print(f"No check-ins found for '{args.pattern}'.")


if __name__ == "__main__":
    main()
