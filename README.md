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

- `autobiographer.py`: Core script for API interaction and data fetching.
- `visualize.py`: Streamlit dashboard implementation.
- `analysis_utils.py`: Shared data processing and analysis logic.
- `notebooks/`: Ready-to-use Jupyter notebooks.
- `tools/`: Utility scripts for video generation and post-processing.
- `data/`: Default local storage for your listening history CSVs.
- `tests/`: Comprehensive test suite (90%+ coverage).

## Contributing

Contributions are welcome! Please follow the Gemini Workflow documented in `GEMINI.md`:
1. Create a descriptive feature branch.
2. Implement your changes with test coverage.
3. Submit a Pull Request.

## License

GNU General Public License v3.0





