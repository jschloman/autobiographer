# Autobiographer: Interactive Autobiographical Data Explorer

![Example Output](assets/example%20screenshot.png)

Autobiographer is a Python-based toolkit that allows you to fetch, store, and explore your personal music listening history (Last.fm) and location history (Foursquare/Swarm). It transforms your data into an interactive autobiographical experience, highlighting your top artists, listening patterns, milestones, and travel history.

## Features

- **Data Fetching**: Securely fetch your entire listening history using the Last.fm API.
- **Interactive Dashboard**: A multi-tab Streamlit dashboard with:
    - **Overview**: Top Artists, Albums, and Tracks.
    - **Timeline**: Daily, Weekly, and Monthly listening activity with cumulative growth.
    - **Patterns**: Hourly listening distribution and day-vs-hour activity heatmaps.
    - **Narrative**: Autobiographical insights including milestones (1k, 5k, 10k tracks), longest streaks, and "forgotten favorites."
- **Data Exploration**: Includes a Jupyter Notebook for custom data deep-dives.
- **Secure Handling**: Credentials managed via environment variables.

## Getting Started

### 1. Prerequisites

- Python 3.8 or higher
- A Last.fm API Key and Secret ([Obtain them here](https://www.last.fm/api/account/create))

### 2. Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/jschloman/autobiographer.git
   cd autobiographer
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configuration

Set your Last.fm credentials in your environment:
```bash
export AUTOBIO_LASTFM_API_KEY="your_api_key"
export AUTOBIO_LASTFM_API_SECRET="your_api_secret"
export AUTOBIO_LASTFM_USERNAME="your_username"
```

### 4. Usage

#### Fetch Your Data
Download your listening history to a local CSV file:
```bash
python autobiographer.py --user your_username
```

#### Launch the Dashboard
Start the interactive Streamlit application:
```bash
streamlit run visualize.py
```

**Advanced Usage with Environment Variables:**
You can pre-configure data paths and privacy settings using environment variables.

*Windows (PowerShell):*
```powershell
$env:AUTOBIO_LASTFM_DATA_DIR="C:\MyData\LastFM"; 
$env:AUTOBIO_SWARM_DIR="C:\MyData\Swarm";
$env:AUTOBIO_ASSUMPTIONS_FILE="C:\MyData\private_assumptions.json";
.\venv\Scripts\streamlit run visualize.py
```

*Linux/macOS:*
```bash
export AUTOBIO_LASTFM_DATA_DIR="/home/user/music_data"
export AUTOBIO_SWARM_DIR="/home/user/checkins"
export AUTOBIO_ASSUMPTIONS_FILE="/home/user/my_assumptions.json"
streamlit run visualize.py
```

#### Location Assumptions
To maintain privacy when sharing the codebase, identifying data like home residency and holiday trips are stored in a separate JSON file.
- **Template**: See `default_assumptions.json.example` for the structure.
- **Default**: If no file or Swarm data is provided, the app defaults to **Reykjavik, IS**.
- **Usage**: The app automatically looks for `default_assumptions.json` in the root, or you can specify a custom path via the `AUTOBIO_ASSUMPTIONS_FILE` environment variable.

#### Fly-through Recording
Generate a cinematic 3D fly-through video or HTML animation of your top listening locations.

  ![Fly-through Animation](assets/flythrough.gif)
- **Script**: `record_flythrough.py`
- **Features**: 
    - Smooth frame-by-frame interpolation using custom easing.
    - High-quality MP4 export using Playwright and MoviePy.
    - Automatically geocodes data if missing (using Swarm/Assumptions).
    - Configurable resolution, FPS, and filtering (artist, dates).
- **Video Generation (.mp4)**:
   ```bash
   python record_flythrough.py --output my_tour.mp4 --artist "Radiohead" --marker_width 2.0 --fps 30
   ```
- **HTML Animation**:
   ```bash
   python record_flythrough.py --output tour.html --start_date 2023-01-01 --end_date 2023-12-31
   ```


**Available Arguments:**
- `--artist`: Filter by artist name.
- `--start_date` / `--end_date`: Filter by timeframe (YYYY-MM-DD).
- `--marker_width`: Scale the width/height of map markers (0.5 to 10.0).
- `--output`: Saves as `.mp4` (video) or `.html` (interactive animation).
- `--fps`: Set video frame rate (default: 30).

*Note: Video generation requires `playwright` and `ffmpeg` (installed automatically during setup).*

#### Exploratory Notebook
Open the Jupyter notebook for custom analysis:
```bash
jupyter notebook notebooks/autobiographer_analysis.ipynb
```

## Tools

Additional utility scripts are available in the `tools/` directory:

- **`add_audio_to_video.py`**: A helper script to mux an audio track (e.g., a top artist's song) with a fly-through video using MoviePy.

## Project Structure

```
autobiographer.py       # Last.fm API fetch + data save CLI
visualize.py            # Streamlit dashboard (assembles views from plugins)
analysis_utils.py       # Shared data processing and caching logic
core/
  broker.py             # DataBroker: loads plugins, merges what-when + where-when
plugins/
  sources/
    base.py             # SourcePlugin ABC + validate_schema()
    __init__.py         # REGISTRY + @register decorator + load_builtin_plugins()
    lastfm/loader.py    # Last.fm source plugin
    swarm/loader.py     # Foursquare/Swarm source plugin
notebooks/              # Jupyter notebooks for custom analysis
tools/                  # Utility scripts (audio muxing, etc.)
data/                   # Local data storage (CSVs, cache, Swarm JSON exports)
tests/                  # Pytest suite (80%+ coverage)
```

## Plugin Architecture

Autobiographer is built on two non-negotiable design principles that apply to every source plugin without exception.

### 1. Data Sovereignty

Each `SourcePlugin` is the sole authority over its own data. A plugin **knows**:

- Its own raw data format and where to read it from.
- How to normalise that data into the canonical schema.

A plugin **does not know**:

- That any other source exists.
- How its output will be filtered, joined, or merged with other sources.
- Any foreign column names, keys, or schemas.

All cross-source logic — temporal joins, geographic enrichment, correlation — lives exclusively in `DataBroker`. This makes every plugin independently testable, replaceable, and comprehensible in isolation.

```
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  LastFmPlugin        │   │  SwarmPlugin          │   │  LetterboxdPlugin    │
│  load() → DataFrame  │   │  load() → DataFrame   │   │  load() → DataFrame  │
│                      │   │                       │   │                      │
│  No knowledge of     │   │  No knowledge of      │   │  No knowledge of     │
│  other sources       │   │  other sources        │   │  other sources       │
└──────────┬───────────┘   └──────────┬────────────┘   └──────────┬───────────┘
           └──────────────────────────┼────────────────────────────┘
                                      ▼
                               ┌─────────────┐
                               │  DataBroker │  ← all joining & merging here
                               └─────────────┘
```

### 2. Download-then-Display

Every plugin operates in two strictly separate phases. **They must never be mixed.**

#### Phase 1 — Collection (download script)

A standalone CLI script fetches data from the external source and writes it to a local file under `data/`. This is the **only** place credentials, API keys, and HTTP calls exist in the codebase.

```bash
# Example: save your Letterboxd diary export locally
python -m autobiographer.sync letterboxd --export-path ~/Downloads/letterboxd.zip
```

The script runs once (or whenever the user wants to refresh their data) and produces a file the plugin can read indefinitely without a network connection.

#### Phase 2 — Display (plugin `load()`)

`SourcePlugin.load()` reads **only** from the previously downloaded local file. It makes **zero** outbound network calls, opens **no** sockets, and requires **no** credentials at runtime. If the local file is absent it raises `FileNotFoundError` with a clear message directing the user to run the download script — it never falls back to a live fetch.

```
┌─────────────────────────────────┐     ┌──────────────────────────────────┐
│  COLLECTION  (run once offline) │     │  DISPLAY  (Streamlit runtime)    │
│                                 │     │                                   │
│  python -m autobiographer.sync  │────▶│  LetterboxdPlugin.load()         │
│    letterboxd                   │     │    reads data/letterboxd.csv      │
│                                 │     │    — zero network calls           │
│  credentials live here only     │     │                                   │
└─────────────────────────────────┘     └──────────────────────────────────┘
```

### Adding a source plugin

Follow these four steps. The contract above applies to every plugin — no exceptions.

**1. Create the download script**, e.g. `autobiographer/sync/letterboxd.py`:

```python
"""Letterboxd: save diary export to data/letterboxd.csv (run once offline)."""
import argparse, zipfile, pathlib

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-path", required=True, help="Path to the Letterboxd ZIP")
    args = parser.parse_args()
    with zipfile.ZipFile(args.export_path) as zf:
        zf.extract("diary.csv", "data/")
    pathlib.Path("data/letterboxd.csv").rename(pathlib.Path("data/letterboxd_diary.csv"))
    print("Saved → data/letterboxd_diary.csv")

if __name__ == "__main__":
    main()
```

**2. Create the plugin file**, e.g. `plugins/sources/letterboxd/loader.py`:

```python
from __future__ import annotations
from typing import Any
import pandas as pd
from plugins.sources import register
from plugins.sources.base import SourcePlugin, validate_schema

@register
class LetterboxdPlugin(SourcePlugin):
    PLUGIN_TYPE = "what-when"
    PLUGIN_ID = "letterboxd"
    DISPLAY_NAME = "Letterboxd Film Diary"
    ICON = ":material/movie:"

    def get_config_fields(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "data_path",
                "label": "Letterboxd diary CSV",
                "type": "file_path",
                "file_types": [("CSV files", "*.csv"), ("All files", "*.*")],
            }
        ]

    def load(self, config: dict[str, Any]) -> pd.DataFrame:
        """Load previously downloaded Letterboxd diary from a local CSV.

        Zero network calls are made here. Raises FileNotFoundError if the
        export file has not been downloaded yet.
        """
        data_path: str = config["data_path"]
        if not data_path:
            return pd.DataFrame()
        # load() reads local data only — no REST calls, no credentials
        df = pd.read_csv(data_path)
        df = df.assign(
            label=df["Name"],
            sublabel=df["Name"],
            category=df["Year"].astype(str),
            source_id=self.PLUGIN_ID,
        )
        validate_schema(df, self.PLUGIN_TYPE)
        return df
```

**3. Register it** in `plugins/sources/__init__.py`:

```python
def load_builtin_plugins() -> None:
    import plugins.sources.lastfm.loader      # noqa: F401
    import plugins.sources.swarm.loader       # noqa: F401
    import plugins.sources.letterboxd.loader  # noqa: F401  ← add this
```

**4. Add tests** in `tests/test_source_plugins.py` following the `TestLastFmPlugin` pattern. Always mock the file-read call — tests must never touch the network or require local data files.

### Config field types

`get_config_fields()` returns field descriptors rendered as path selectors in the sidebar. Each plugin's selectors are grouped in their own collapsible section.

| `type` | Widget | Use for |
|---|---|---|
| `"file_path"` | Text input + file picker | Single export files (CSV, JSON, ZIP) |
| `"dir_path"` | Text input + folder picker | Export directories with multiple files |
| `"text"` | Plain text input | Non-path settings |
| `"toggle"` | Checkbox | Boolean options |

Add `"file_types": [("CSV files", "*.csv")]` to any `file_path` field to pre-filter the picker dialog.

Selected paths are persisted to `data/config.json` so they survive application restarts.

### Plugin schema

| `PLUGIN_TYPE` | Required columns |
|---|---|
| `what-when` | `timestamp`, `label`, `sublabel`, `category`, `source_id` |
| `where-when` | `timestamp`, `lat`, `lng`, `place_name`, `place_type`, `source_id` |

`validate_schema()` raises `ValueError` at load time if any required column is absent.

### Using the DataBroker directly

```python
from plugins.sources import load_builtin_plugins, REGISTRY
from core.broker import DataBroker

load_builtin_plugins()
broker = DataBroker()
broker.load(REGISTRY["lastfm"](), {"data_path": "data/tracks.csv"})
broker.load(REGISTRY["swarm"](), {"swarm_dir": "data/swarm"})

df = broker.get_merged_frame(assumptions=my_assumptions)  # temporally joined
broker.is_type_available("where-when")  # → True
```

## Contributing

Contributions are welcome! Please follow the engineering standards in `CLAUDE.md`:
1. Create a descriptive feature branch using [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `perf:`, etc.).
2. Implement your changes with test coverage (80% minimum).
3. Run the local quality gate before pushing: `ruff check . && ruff format --check . && mypy && pytest --cov=. --cov-fail-under=80 tests/`
4. Submit a Pull Request — the PR title must also follow Conventional Commits format.

## License

GNU General Public License v3.0





