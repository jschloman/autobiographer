# Autobiographer: Plugin Architecture Expansion Brief

## Vision

Transform Autobiographer from a two-source music/location explorer into an **extensible personal data platform** — a composable system where any number of geo-temporal data sources can be loaded as plugins, layered together, and rendered through interchangeable visualization views. The goal is a tool that lets anyone reconstruct the narrative arc of their life from the digital traces they leave behind.

---

## Background: Current Architecture

The current project is a Python/Streamlit application with two tightly coupled data sources and four hardcoded views:

**Data sources (hardcoded):**
- `autobiographer.py` — fetches Last.fm music listening history
- `analysis_utils.py` → `load_swarm_data()` / `apply_swarm_offsets()` — ingests Foursquare/Swarm location check-ins

**Views (hardcoded tabs in `visualize.py`):**
- **Overview** — top artists, albums, tracks
- **Timeline** — plays per day/week/month, cumulative growth
- **Spatial** — 3D pydeck globe with listening locations and fly-through
- **Insights & Narrative** — hourly patterns, streaks, milestones, forgotten favorites

The sidebar wires data to views directly with no abstraction layer between them. Expansion requires decoupling these two concerns into independent, registerable plugin systems.

---

## Core Concept: Two Dimensions of Personal Data

All personal life-data can be expressed along a temporal axis. What varies is what the second axis encodes:

| Plugin Type | Second Axis | Existing Example | Future Examples |
|---|---|---|---|
| **what-when** | Activity, content, or event | Last.fm (music + time) | Letterboxd (films), Goodreads (books), GitHub commits, podcast plays, workouts |
| **where-when** | Geography or place | Foursquare/Swarm (location + time) | Google Maps Timeline, Apple Health GPS, photo EXIF geodata, flight logs, Strava routes |

A **what-when** source answers: *"What were you experiencing at this moment?"*
A **where-when** source answers: *"Where were you at this moment?"*

Combined, they answer: *"What were you doing, and where were you when you did it?"* — the raw material of autobiography.

---

## Workstream 1: Data Source Plugin System

### 1.1 Plugin Interface

Each data source plugin is a Python class implementing a standard interface. Plugins live in `plugins/sources/`.

```
plugins/
  sources/
    __init__.py          # plugin registry and loader
    base.py              # abstract base class
    lastfm/
      __init__.py
      fetcher.py         # API fetching logic
      loader.py          # CSV/cache loading
    swarm/
      __init__.py
      loader.py
    letterboxd/          # example future plugin
      __init__.py
      loader.py
    strava/              # example future plugin
      __init__.py
      loader.py
```

**`base.py` — Abstract Source Plugin:**

```python
from abc import ABC, abstractmethod
import pandas as pd

class SourcePlugin(ABC):
    PLUGIN_TYPE: str   # "what-when" or "where-when"
    PLUGIN_ID: str     # e.g. "lastfm", "swarm"
    DISPLAY_NAME: str  # e.g. "Last.fm Music History"

    @abstractmethod
    def get_config_fields(self) -> list[dict]:
        """Return list of sidebar config fields (path inputs, API keys, etc.)"""

    @abstractmethod
    def load(self, config: dict) -> pd.DataFrame:
        """Load and return a normalized DataFrame."""

    def get_schema(self) -> dict:
        """Return column metadata for downstream view compatibility checks."""
```

**Normalized DataFrame Schema:**

All plugins emit a common `timestamp` column plus type-specific columns. The schema contract is enforced at load time.

| Column | Required | Type | Notes |
|---|---|---|---|
| `timestamp` | All | datetime | UTC-normalized |
| `label` | what-when | str | e.g. artist name, film title, repo name |
| `sublabel` | what-when | str | e.g. track name, director |
| `category` | what-when | str | plugin-defined grouping |
| `lat` | where-when | float | WGS84 |
| `lng` | where-when | float | WGS84 |
| `place_name` | where-when | str | venue, city, or region |
| `place_type` | where-when | str | e.g. "venue", "city", "country" |
| `source_id` | All | str | plugin identifier for provenance |

### 1.2 Plugin Registry

`plugins/sources/__init__.py` maintains a registry of all installed plugins. New plugins self-register via a decorator or entry-point mechanism (compatible with both local files and pip-installable packages).

```python
REGISTRY: dict[str, type[SourcePlugin]] = {}

def register(cls):
    REGISTRY[cls.PLUGIN_ID] = cls
    return cls
```

### 1.3 Plugin Configuration in the UI

Each plugin declares its own sidebar config fields (text inputs, file pickers, toggles). The sidebar renders these dynamically at runtime — no hard-coded `st.text_input("Swarm Data Directory")` calls in `visualize.py`.

Each loaded plugin is displayed as a card in the sidebar with:
- Plugin name and type badge (what-when / where-when)
- Load status and record count
- Toggle to enable/disable per view

### 1.4 Temporal Alignment and Merging

A core `DataBroker` class (`core/broker.py`) handles:
- Loading all enabled plugins
- Aligning timestamps to a common timezone (UTC + user-local offset)
- Merging where-when data onto what-when records by closest-in-time join (configurable window, e.g. ±12 hours)
- Caching merged results with a hash derived from all source configs

This replaces the current `apply_swarm_offsets()` function with a generalizable, plugin-aware version.

### 1.5 Reference Plugin Specifications

**`lastfm` (what-when)** — migration of current `autobiographer.py`
- Config: API key, secret, username, data directory
- Emits: `timestamp`, `label` (artist), `sublabel` (track), `category` (album)

**`swarm` (where-when)** — migration of current `load_swarm_data()`
- Config: Swarm JSON export directory, assumptions file path
- Emits: `timestamp`, `lat`, `lng`, `place_name`, `place_type`

**`letterboxd` (what-when)** — future reference implementation
- Config: Letterboxd CSV export path
- Emits: `timestamp`, `label` (film title), `sublabel` (director), `category` (genre)

**`strava` (where-when)** — future reference implementation
- Config: Strava GPX/JSON export directory
- Emits: `timestamp`, `lat`, `lng`, `place_name` (route name), `place_type` ("route")

**`goodreads` (what-when)** — future reference implementation
- Config: Goodreads CSV export
- Emits: `timestamp` (date finished), `label` (title), `sublabel` (author), `category` (genre/shelf)

---

## Workstream 2: View Plugin System

### 2.1 Plugin Interface

Each visualization is a Python class implementing a standard view interface. Views live in `plugins/views/`.

```
plugins/
  views/
    __init__.py          # view registry and loader
    base.py              # abstract base class
    spatial/             # existing spatial/3D globe view
    annual/              # existing timeline view
    overview/            # existing top-charts view
    narrative/           # existing insights view
    composition/         # new: multi-source overlay view
    chord/               # new: cross-source relationship view
```

**`base.py` — Abstract View Plugin:**

```python
from abc import ABC, abstractmethod
import pandas as pd

class ViewPlugin(ABC):
    VIEW_ID: str
    DISPLAY_NAME: str
    REQUIRED_TYPES: list[str]   # e.g. ["what-when"], or ["what-when", "where-when"]
    OPTIONAL_TYPES: list[str]

    @abstractmethod
    def render(self, sources: dict[str, pd.DataFrame], config: dict):
        """Render the view using enabled source DataFrames."""

    def get_controls(self) -> list[dict]:
        """Return view-specific control widgets (filters, toggles, etc.)"""

    def is_compatible(self, available_types: list[str]) -> bool:
        return all(t in available_types for t in self.REQUIRED_TYPES)
```

### 2.2 View Registry and Tab Builder

`visualize.py` is refactored so that tabs are assembled at runtime from registered, compatible views. If a view requires `["what-when", "where-when"]` but only what-when sources are loaded, that view tab is hidden with a tooltip explaining what's missing.

```python
active_views = [
    v for v in VIEW_REGISTRY.values()
    if v.is_compatible(broker.available_types)
]
tabs = st.tabs([v.DISPLAY_NAME for v in active_views])
for tab, view in zip(tabs, active_views):
    with tab:
        view.render(broker.get_frames(), view_config)
```

### 2.3 View Specifications

**Migrated views** (refactored from current hardcoded tabs):

- **`spatial`** — 3D pydeck globe with column/scatter layers. Gains the ability to render multiple source types simultaneously (e.g. music markers + location check-ins in different colors/shapes). Fly-through and HTML export retained.
- **`annual`** — Timeline/activity charts. Gains multi-source overlay: e.g. a single chart showing film watches, music listens, and check-ins on the same time axis.
- **`overview`** — Top charts. Gains a source selector so the same chart template works against any what-when plugin (top artists, top films, top books, top repos).
- **`narrative`** — Insights and milestones. Gains cross-source narrative: *"In the summer of 2019, you listened to 'OK Computer' 47 times, watched 12 films, and checked in at 8 cities."*

**New views:**

- **`composition`** — A canvas where users pick any combination of loaded sources and assemble a multi-panel layout. Panels are drag-reorderable. Each panel is itself a mini-view (chart, map, timeline strip). Exported as a shareable HTML snapshot.
- **`chord`** — A chord diagram or alluvial/Sankey visualization showing co-occurrence across sources: which artists were you listening to in which cities? Which films did you watch in which countries? Requires at least one what-when and one where-when source.
- **`density_calendar`** — A GitHub-style contribution grid showing activity heatmap per source, with configurable year range and source layering.
- **`story_reel`** — A chronological card-based narrative feed. Each card represents a moment in time and combines data from all sources: *"March 14, 2017 — Chicago, IL. You checked into The Empty Bottle. You listened to Japandroids 6 times. You finished 'The Power Broker'."* Cards are auto-generated and optionally hand-annotated.

---

## Workstream 3: Composition and Cross-Source Linking UI

### 3.1 Data Combination Controls

Each view that supports multiple sources renders a **source layer panel** — a compact sidebar section specific to that view showing:
- Which sources are loaded (with type badges)
- Per-source color/shape assignment
- Layer visibility toggles
- Blend mode for overlapping temporal windows (union, intersection, proximity join)

### 3.2 Composition Canvas (new `composition` view)

The Composition view is an open-ended workspace:

1. **Panel grid** — user adds panels from a menu; each panel is assigned a view type and one or more sources
2. **Shared time axis** — a global date range scrubber at the top of the canvas syncs all panels simultaneously
3. **Cross-panel linking** — clicking a point in one panel (e.g. a location) filters all other panels to the same time window
4. **Export** — the composition is exported as a self-contained HTML file (similar to current fly-through export), suitable for sharing or archiving

### 3.3 Link Grammar

Views can emit and receive **link events** — a lightweight pub/sub system allowing user interactions in one view to filter another. Link types:

| Event | Emitted by | Received by |
|---|---|---|
| `time_select` | Any timeline/chart | All panels |
| `place_select` | Spatial view | Timeline, Overview, Narrative |
| `label_select` | Overview (e.g. click artist) | Spatial, Timeline, Story Reel |
| `period_select` | Annual calendar | All panels |

This transforms the dashboard from parallel read-only views into an interactive linked exploration tool.

---

## Workstream 4: Developer Experience

### 4.1 Plugin Authoring Guide

A `PLUGIN_GUIDE.md` document specifying:
- How to implement `SourcePlugin` or `ViewPlugin`
- Required and optional schema columns
- How to declare config fields for automatic sidebar rendering
- How to write tests for a plugin (using the existing test suite pattern)
- Example minimal plugin (~50 lines) for a CSV-based what-when source

### 4.2 Plugin Discovery

Plugins in `plugins/sources/` and `plugins/views/` are auto-discovered at startup. Third-party plugins can be installed as Python packages declaring an `autobiographer.source_plugins` or `autobiographer.view_plugins` entry point.

### 4.3 Example Plugin Bundle

Ship a `plugins/sources/csv_generic/` plugin that accepts any CSV with configurable column mappings (`timestamp_col`, `label_col`, etc.). This acts as an escape hatch for any data source without a dedicated plugin, and as a reference implementation for plugin authors.

### 4.4 Configuration File

Replace ad-hoc environment variables with a structured `autobiographer.config.json` (or TOML) file:

```json
{
  "sources": [
    { "plugin": "lastfm", "enabled": true, "data_dir": "data/lastfm" },
    { "plugin": "swarm", "enabled": true, "data_dir": "data/swarm" },
    { "plugin": "letterboxd", "enabled": false, "data_dir": "data/letterboxd" }
  ],
  "views": {
    "enabled": ["spatial", "annual", "overview", "narrative", "composition"],
    "default": "composition"
  },
  "privacy": {
    "assumptions_file": "private/assumptions.json"
  }
}
```

Environment variables remain supported as overrides for CI/deployment contexts.

---

## Workstream 5: Export and Artifact Plugin System

The current project ships one export format — a cinematic fly-through HTML/MP4 via `record_flythrough.py`. This workstream generalizes that into a plugin-based **artifact export system** capable of producing a wide range of shareable outputs from any combination of data sources and views.

### 5.1 Export Plugin Interface

Export plugins live in `plugins/exports/` and implement a standard interface alongside a render context that packages the data, view config, and any user-supplied metadata.

```
plugins/
  exports/
    __init__.py
    base.py
    flythrough_video/       # refactored from record_flythrough.py
    flythrough_html/        # refactored inline HTML export
    year_in_review/         # new: annual summary graphic + video
    highlight_reel/         # new: auto-edited event montage video
    poster/                 # new: static print-quality poster
    data_zine/              # new: multi-page PDF zine
    timelapse_map/          # new: animated choropleth / dot-density map
    social_card/            # new: short-form social media graphic
    slideshow/              # new: PowerPoint / Google Slides export
```

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd

@dataclass
class ExportContext:
    sources: dict[str, pd.DataFrame]   # keyed by source_id
    view_id: str                        # which view triggered the export
    date_range: tuple                   # active filter
    config: dict                        # view + user config
    metadata: dict                      # title, author, annotations

class ExportPlugin(ABC):
    EXPORT_ID: str
    DISPLAY_NAME: str
    OUTPUT_FORMATS: list[str]           # e.g. ["mp4", "html"], ["pdf"], ["png"]
    REQUIRED_SOURCES: list[str]         # plugin types required, e.g. ["where-when"]

    @abstractmethod
    def export(self, ctx: ExportContext, output_path: str, fmt: str) -> str:
        """Generate artifact at output_path; return final path."""

    def get_options(self) -> list[dict]:
        """Declare configurable export options rendered in the export dialog."""
```

### 5.2 Export UI Surface

Each view gains an **Export** button in its header. Clicking it opens a slide-over panel with:

1. **Format picker** — lists all compatible export plugins given active data sources and current view, with format badges (MP4, HTML, PDF, PNG, PPTX)
2. **Options form** — dynamically rendered from `get_options()` (resolution, date range, title, color theme, audio track, privacy redactions)
3. **Preview thumbnail** — a low-resolution still or animated GIF preview generated before committing to full render
4. **Render + download** — progress bar during render; download link or file save dialog on completion

All exports are also triggerable from the CLI (`python export.py --plugin year_in_review --format mp4 --config autobiographer.config.json`) for use in scripts and scheduled runs.

### 5.3 Export Plugin Specifications

---

#### `flythrough_video` and `flythrough_html`
*Refactored from the current `record_flythrough.py` and inline export button in `visualize.py`.*

- **Inputs:** any where-when source; optionally overlays what-when activity as marker height/color
- **MP4 output:** frame-by-frame Playwright render with MoviePy assembly; configurable FPS, resolution, easing curve, marker scaling
- **HTML output:** self-contained pydeck animation with embedded JavaScript keyframe sequence
- **New capability:** multi-source fly-through — markers on the globe can be colored by source type (e.g. blue for check-ins, orange for GPS routes), and the tour can be driven by any where-when source, not just Swarm
- **New capability:** audio muxing is now a first-class export option in the UI rather than a separate `tools/add_audio_to_video.py` script; the user can pick an audio file or (if Last.fm is loaded) auto-select a top artist track

---

#### `year_in_review`
*Inspired by Spotify Wrapped / Apple Replay — a structured annual summary artifact.*

- **Inputs:** any mix of what-when and where-when sources
- **Output formats:** MP4 video (animated slide sequence), PNG poster, HTML interactive
- **Structure:** configurable slide sequence, each slide drawing from a different source or cross-source stat. Default sequence:
  1. Title card — year, user name, total data points
  2. Geography slide — choropleth world map of visited countries/cities
  3. Top content slides — one per what-when source (top artists, films, books)
  4. Peak moment slide — the single highest-density day across all sources
  5. Journey slide — globe fly-through of top 10 locations
  6. Cross-source moment — "Your year in one sentence" (generated from the most co-occurring data points)
- **Theming:** preset visual themes (dark globe, newspaper, polaroid, minimal); custom color palette override
- **Audio:** for MP4, auto-selects top artist from Last.fm if available; otherwise silent or user-supplied

---

#### `highlight_reel`
*An auto-edited short video montage, analogous to a social media recap reel.*

- **Inputs:** any sources; best with both what-when and where-when
- **Output formats:** MP4 (vertical 9:16 or horizontal 16:9), animated GIF
- **Logic:** identifies "highlight moments" — days or windows with unusually high cross-source activity density — and assembles them as a sequence of animated map zooms, chart reveals, and stat cards with transitions
- **Duration:** configurable (15s / 30s / 60s / custom)
- **Text overlays:** auto-generated captions from source data (e.g. "47 plays · The Empty Bottle · Chicago"); optionally user-edited before render
- **Music sync:** if Last.fm is loaded, beat-detects top track and syncs cut points to the beat grid (using `librosa`)

---

#### `poster`
*A single-page print-quality static infographic.*

- **Inputs:** any sources
- **Output formats:** PNG (72 / 150 / 300 dpi), SVG, PDF (A3/A2/24×36in)
- **Layout templates:**
  - *Star map style* — radial chart of listening/activity frequency by hour and day of year, overlaid on a dark background
  - *Travel map* — world map with arcs connecting visited locations, dot density proportional to activity
  - *Data portrait* — abstract generative art form derived from activity patterns (uses matplotlib or Pillow; output is deterministic from the data)
  - *Year grid* — 365-day contribution calendar style, one row per source
- **Typography:** configurable title, subtitle, and footer text; font size and weight
- **Print bleed:** optional crop marks and bleed margin for professional printing

---

#### `data_zine`
*A multi-page PDF booklet — a personal data zine, paginated like a small magazine.*

- **Inputs:** any sources
- **Output format:** PDF (A5 or letter, print-ready with facing pages)
- **Auto-generated sections:** one section per loaded source (introduction, top items, timeline, notable moments); one cross-source section (geography + activity overlay); appendix with raw summary tables
- **User control:** section order drag-reorder in export options; each section togglable; custom text annotations injected between sections
- **Rendering:** uses WeasyPrint or ReportLab; templated with Jinja2 HTML → PDF pipeline for flexible styling

---

#### `timelapse_map`
*An animated map showing activity density changing over time — months or years scrolling across a choropleth or dot-density globe.*

- **Inputs:** at least one where-when source
- **Output formats:** MP4, animated GIF, HTML (Plotly/pydeck animation)
- **Animation modes:**
  - *Accumulating* — dots or country fills appear and persist as time moves forward (shows total life footprint growing)
  - *Sliding window* — a time window (e.g. one month) scrolls forward, showing activity at each moment
  - *Pulse* — each event pulses at its location as its timestamp is reached
- **What-when overlay:** if a what-when source is loaded, marker color or size encodes activity intensity at that location during the window
- **Speed control:** configurable playback speed and time-per-frame; exported video includes a visible date counter

---

#### `social_card`
*Quick-share graphics optimized for social media and messaging platforms.*

- **Inputs:** any sources
- **Output formats:** PNG (1:1, 4:5, 16:9, 9:16), animated GIF
- **Card types:**
  - *Stat card* — single striking statistic with label (e.g. "12,847 songs this year")
  - *Mini map* — compact globe or flat map with location dots
  - *Top 5 card* — ranked list graphic (top artists, top cities, top films)
  - *Streak card* — longest streak or current streak visualization
- **Brand/theme:** user-supplied background image or color; logo/watermark overlay option
- **Batch mode:** generate one card per source automatically and download as a ZIP

---

#### `slideshow`
*A presentation-ready slide deck from your data.*

- **Inputs:** any sources
- **Output formats:** PPTX (PowerPoint), PDF (presentation mode), HTML reveal.js
- **Template:** one master template with configurable title slide, one section per source, cross-source comparison slides, and a closing summary slide
- **Charts embedded as images** — all Plotly/pydeck charts are rendered to PNG at slide dimensions and embedded natively
- **Speaker notes:** auto-generated from data (e.g. "In 2022 you listened to 3,200 tracks across 180 artists. Your most active month was August with 412 plays.")
- **PPTX output** uses the `python-pptx` library; HTML output uses reveal.js with a self-contained export

---

### 5.4 Shared Export Infrastructure

A set of shared utilities used across export plugins (`core/export_utils.py`):

- **`render_frame(view_id, ctx, timestamp)`** — renders a single frame of a view to a PNG buffer using Playwright headless; used by video export plugins to avoid duplicating screenshot logic
- **`build_video(frames, fps, output_path)`** — wraps MoviePy; handles frame assembly, codec selection, and optional audio muxing
- **`mux_audio(video_path, audio_path, output_path)`** — consolidates the current `tools/add_audio_to_video.py` into shared infrastructure
- **`detect_beats(audio_path)`** — returns beat timestamps using `librosa`; used by `highlight_reel` for music-sync editing
- **`render_html_snapshot(deck_or_fig, output_path)`** — produces a self-contained HTML file from a pydeck Deck or Plotly figure
- **`apply_theme(theme_name)`** — returns a color palette dict shared across export plugins for visual consistency

### 5.5 Configuration Addition

Export plugin config is added to `autobiographer.config.json`:

```json
{
  "exports": {
    "output_dir": "exports/",
    "default_resolution": "1920x1080",
    "default_fps": 30,
    "default_theme": "dark_globe",
    "audio": {
      "auto_select_from_lastfm": true,
      "fallback_audio_path": null
    },
    "privacy": {
      "redact_home_radius_km": 0.5,
      "suppress_venue_categories": ["Home"]
    }
  }
}
```

---

## Migration Path

The refactor is designed to be non-breaking. The existing `autobiographer.py`, `analysis_utils.py`, and hardcoded `visualize.py` tabs continue to work during migration. Each workstream is independently mergeable:

1. **Phase 1** — Extract source plugin interface; wrap Last.fm and Swarm as first-party plugins; introduce `DataBroker`; no UI changes.
2. **Phase 2** — Extract view plugin interface; refactor existing four tabs as registered view plugins; no functional changes, just structural.
3. **Phase 3** — Add new views (`composition`, `chord`, `density_calendar`, `story_reel`); add cross-panel linking.
4. **Phase 4** — Refactor `record_flythrough.py` and inline HTML export as the first export plugins (`flythrough_video`, `flythrough_html`); introduce `ExportPlugin` base class and export UI surface; consolidate `tools/add_audio_to_video.py` into shared export infrastructure.
5. **Phase 5** — Ship `year_in_review`, `poster`, and `social_card` export plugins.
6. **Phase 6** — Ship `highlight_reel`, `timelapse_map`, `data_zine`, and `slideshow` export plugins; publish plugin authoring guide covering all three plugin types (source, view, export).
7. **Phase 7** — Ship reference source plugins for Letterboxd, Strava, and Goodreads.

---

## Open Questions

- **Temporal join strategy** — when merging what-when and where-when records, the ±window join currently used for Swarm offsets may produce ambiguous results for sources with sparse location data (e.g. only a few check-ins per week). Should the default be "nearest in time", "interpolated route", or a user-configured assumption?
- **Privacy model** — the current `assumptions.json` pattern handles home location redaction. As more sources are added, a more systematic per-source privacy config may be needed (e.g. suppress certain venue categories, anonymize home radius). Export plugins that produce shareable artifacts need their own privacy pass before render.
- **Performance** — multi-source merges on large datasets (100k+ records per source) may require moving the `DataBroker` merge step to a background thread or pre-computed artifact rather than recalculating on every Streamlit interaction. Long video renders (especially `timelapse_map` and `year_in_review` at high resolution) will need background job infrastructure with a progress callback.
- **View portability** — the `composition` export produces a static HTML snapshot. Should it also be able to export a fully self-contained Streamlit app, or is static HTML sufficient?
- **Music licensing** — the `highlight_reel` and `year_in_review` export plugins can auto-select music from Last.fm history for background audio. This is appropriate for personal, non-distributed use. The UI should include a clear disclaimer that exported videos containing commercial music may not be suitable for public sharing on platforms that enforce content ID (YouTube, Instagram, TikTok).
- **`librosa` dependency weight** — beat detection for `highlight_reel` adds a significant optional dependency. This should be an optional install (`pip install autobiographer[audio]`) rather than a core requirement.
