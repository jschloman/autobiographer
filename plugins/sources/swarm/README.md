# Foursquare / Swarm Check-ins

## What it is

[Swarm](https://www.swarmapp.com) is Foursquare's check-in app. Every time you tap **Check In** at a venue — a restaurant, bar, airport, museum, gym, or anywhere else — Swarm records the place name, category, GPS coordinates, and timestamp. Over years of use this becomes a rich location diary: where you travelled, how often you visited your favourite places, and how your habits shifted over time.

Autobiographer imports this history so you can map your check-ins, analyse travel patterns, and cross-reference locations against your music listening activity.

## How the data is obtained

Foursquare does not offer a public API for bulk check-in export, so **your data must be requested directly from Foursquare**. They provide a GDPR-compliant personal data export that includes your full check-in history as a set of JSON files.

This is a one-time manual step. Once you have the export you can keep it on disk and re-point the plugin at it whenever needed — no repeat request is necessary unless you want to add newer check-ins.

## Setup

### 1. Request your data export from Foursquare

1. Open the **Foursquare City Guide** app on your phone.
2. Go to **Settings → Privacy → Request My Data**.
3. Confirm the request. Foursquare will email you a download link within a few days.
4. Download the archive from the link in the email.
5. Unzip the archive to a location on your computer (e.g. `data/swarm_export/`).

> **Note**: The export email comes from Foursquare, not from the Swarm app directly. Check your spam folder if it doesn't arrive within 48 hours.

### 2. Point the plugin at the export directory

In the Autobiographer sidebar, expand **Foursquare / Swarm Check-ins** and click **…** next to **Swarm JSON export directory**. Navigate to the unzipped folder and select it. The plugin reads all `.json` files in that directory.

## Data produced

| Column | Description |
|--------|-------------|
| `timestamp` | Unix timestamp of the check-in (UTC) |
| `lat` | Latitude (WGS84) |
| `lng` | Longitude (WGS84) |
| `place_name` | Venue or location name |
| `place_type` | Location category (e.g. `"venue"`, `"city"`) |
| `source_id` | Always `"swarm"` |

Additional columns from the raw export (`city`, `country`, `source`) are preserved alongside the normalized schema columns.
