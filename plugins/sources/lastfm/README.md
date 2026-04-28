# Last.fm Music History

## What it is

[Last.fm](https://www.last.fm) is a music tracking service that logs every song you play — a practice called *scrobbling*. Whenever you listen to a track through a connected player (Spotify, Apple Music, YouTube Music, Winamp, and dozens more), Last.fm records the artist, album, track name, and timestamp. Over time this builds a complete, timestamped diary of everything you've ever listened to.

Autobiographer imports this history so you can visualize listening patterns, milestones, streaks, and top artists across your entire music life.

## How the data is fetched

Autobiographer fetches your scrobble history directly from the Last.fm API and saves it as a CSV file at `data/lastfm_<username>_tracks.csv`. No manual export step is required.

You can trigger a fetch in two ways:

- **In the app**: click **Fetch Latest Data** in the Last.fm sidebar panel.
- **On the command line**: `python autobiographer.py fetch lastfm`

Both methods accept date-range flags (`--from-date`, `--to-date`) and a page limit (`--pages`) if you only want a partial history.

## Setup

### 1. Create a Last.fm API application

Go to <https://www.last.fm/api/account/create> and register a new application (the name and description can be anything). You will receive an **API Key** and a **Shared Secret**.

### 2. Set your credentials

Create a `.env` file in the project root (copy `.env.example` as a starting point) and fill in your values:

```env
AUTOBIO_LASTFM_API_KEY=your_api_key_here
AUTOBIO_LASTFM_API_SECRET=your_shared_secret_here
AUTOBIO_LASTFM_USERNAME=your_lastfm_username
```

The app and CLI both load `.env` automatically on startup — you do not need to `export` these manually.

### 3. Fetch your history

Click **Fetch Latest Data** in the sidebar, or run:

```bash
python autobiographer.py fetch lastfm
```

A full history fetch can take several minutes depending on how many scrobbles you have. The progress bar in the sidebar shows which page is being downloaded.

### 4. Point the plugin at the CSV

After a fetch the **Last.fm CSV file** field is populated automatically. If you already have a CSV (e.g. from a previous fetch or a third-party export tool), click **…** to browse for it manually.

## Data produced

| Column | Description |
|--------|-------------|
| `timestamp` | Unix timestamp of the listen (UTC) |
| `label` | Artist name |
| `sublabel` | Track name |
| `category` | Album name |
| `source_id` | Always `"lastfm"` |

Original columns (`artist`, `track`, `album`, `date_text`) are also preserved for backward compatibility.
