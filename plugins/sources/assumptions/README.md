# Location Assumptions

## What it is

Location assumptions are a user-authored JSON file that tells Autobiographer where you were during periods not captured by Swarm check-ins. This fills the gaps that GPS data inevitably leaves: years before you started using Swarm, trips you forgot to check in on, recurring visits to family, and the simple fact of where home is.

The assumptions file is applied when Autobiographer maps timezone offsets and locations onto your Last.fm listening history. Without it, every listen without a Swarm match falls back to a generic default location. With it, you get accurate local times and a richer map of where your life was actually happening.

## How the data is obtained

You create this file yourself. It is a structured JSON document with four sections:

| Section | Purpose |
|---------|---------|
| `defaults` | Your home city and timezone — used as the fallback when nothing else matches |
| `trips` | Explicit date-range travel entries (city, lat/lng, timezone, start, end) |
| `holidays` | Annually recurring events matched by month and day range (e.g. a family visit every December) |
| `residency` | Long-term home or work periods, with optional sub-rules for work-hours vs. home logic |

## Setup

### 1. Copy the example file

```bash
cp default_assumptions.json.example default_assumptions.json
```

This file is already gitignored — your personal location history stays on your machine.

### 2. Edit the file with your own data

Open `default_assumptions.json` in any text editor. Replace the example entries with your own. The format is:

```json
{
  "defaults": {
    "city": "London, GB",
    "lat": 51.5074,
    "lng": -0.1278,
    "timezone": "Europe/London"
  },
  "trips": [
    {
      "start": "2023-06-01",
      "end": "2023-06-07",
      "city": "Paris, FR",
      "lat": 48.8566,
      "lng": 2.3522,
      "timezone": "Europe/Paris"
    }
  ],
  "holidays": [
    {
      "name": "Christmas",
      "month": 12,
      "day_range": [24, 26],
      "city": "Edinburgh, GB",
      "lat": 55.9533,
      "lng": -3.1883,
      "timezone": "Europe/London"
    }
  ],
  "residency": []
}
```

Timezone strings must be valid IANA timezone identifiers (e.g. `"America/New_York"`, `"Asia/Tokyo"`). Lat/lng values are in WGS84 decimal degrees.

### 3. Point the plugin at your file

In the Autobiographer sidebar, expand **Location Assumptions** and click **…** next to **Location assumptions JSON**. Navigate to your `default_assumptions.json` and select it.

The sidebar will auto-expand this section if no file is configured yet.

## How it works with other plugins

The Location Assumptions plugin does not produce a data source on its own — it enriches the output of the **Last.fm** plugin. When Autobiographer processes your listening history, it looks up each listen's timestamp in this file (in priority order: holidays → trips → residency → defaults) to assign a city, coordinates, and UTC offset. This is what makes the timeline and map views show correct local times and locations for listens recorded long before you started checking in on Swarm.

## Data produced

| Column | Description |
|--------|-------------|
| `type` | Entry kind: `"default"`, `"trip"`, `"holiday"`, or `"residency"` |
| `city` | City name (used for display and geocoding fallback) |
| `lat` | Latitude (WGS84) |
| `lng` | Longitude (WGS84) |
| `timezone` | IANA timezone string (e.g. `"Europe/London"`) |
| `start` | Start date (`YYYY-MM-DD`) or recurring pattern for holidays |
| `end` | End date (`YYYY-MM-DD`); empty for defaults and holidays |
