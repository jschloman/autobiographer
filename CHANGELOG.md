# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2026.04.24] - 2026-04-24

### Added

- Multi-page Streamlit navigation using `st.navigation` with Material icons.
- Plugin model with `SourcePlugin` ABC, registry, and `DataBroker` for cross-source
  temporal joins and geographic enrichment.
- `record_flythrough.py`: cinematic 3D fly-through video generator using Playwright and
  MoviePy; supports artist/date filtering, configurable resolution and FPS.
- Static code review tooling: `ruff`, `mypy`, and `bandit` integrated via `pyproject.toml`.
- CI pipeline with conventional-commit PR title linting, lint/format/type/test quality gate,
  and timestamp-based GitHub releases on PR merge.

### Changed

- Fly-through map style updated to dark basemap with teal→amber column palette matching
  the application's dark-mode theme.
- `record_flythrough.py` CLI arguments expanded with full descriptions and a `--marker_zoom`
  flag (replacing the previously documented but non-existent `--marker_width`).

### Fixed

- `record_flythrough.py` silently exited when no Last.fm CSV was provided; the `csv`
  positional argument is now clearly documented as required.
