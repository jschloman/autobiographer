# Autobiographer: Engineering Standards & Mandates

This document serves as the foundational mandate for all development work performed by AI agents on this codebase. This is a high-quality Python project; every contribution must uphold the following standards of simplicity, clarity, reliability, and performance.

## 1. Core Philosophy

*   **Simplicity over Cleverness**: Write code that is easy to reason about. Avoid complex abstractions or "magic" patterns unless they provide significant performance gains.
*   **Clarity is Paramount**: Variable names should be descriptive. Logic should be self-documenting. Complex blocks must have concise, meaningful comments.
*   **Test-Backed Integrity**: A feature is not complete, and a bug is not fixed, until it is verified by automated tests. We aim for high coverage and regression-proof logic.
*   **Performance by Design**: We handle large datasets (Last.fm listening histories and Foursquare/Swarm check-ins). Use vectorized `pandas` operations over loops and leverage caching systems to avoid redundant calculations.

## 2. Python Standards

*   **Type Safety**: Use Python 3.10+ type hints for all function signatures and complex variables.
*   **Style**: Adhere strictly to PEP 8. Use `ruff` or `black` for formatting.
*   **Documentation**: Every function must have a docstring (Google or NumPy style) explaining its purpose, parameters, and return values.
*   **Environment**: Always use the virtual environment (`venv/`) and keep `requirements.txt` updated.

## 3. Data & Privacy (Mandatory)

*   **Anonymity**: Never hardcode personal data (locations, usernames, credentials) into the codebase. 
*   **Externalize Assumptions**: Any personal identifying data or location assumptions must reside in external JSON files (e.g., `default_assumptions.json.example`) or environment variables.
*   **Credential Protection**: Use the `AUTOBIO_` environment variable prefix for all configuration. Never log or print API keys or secrets.

## 4. Testing & Validation

*   **Framework**: Use `pytest` for all tests.
*   **Granularity**: Prefer unit tests for utility logic (`analysis_utils.py`) and integration tests for UI/CLI flows (`visualize.py`, `record_flythrough.py`).
*   **Mocks**: Properly mock external dependencies (Last.fm API, Streamlit UI components) to ensure tests are fast, deterministic, and can run in CI.
*   **Validation Step**: AI agents MUST run the full test suite (`.\venv\Scripts\python -m pytest tests/`) before proposing any change.

## 5. Caching & Efficiency

*   **Computation**: Expensive geocoding or data processing must be cached locally in `data/cache/` using the established `get_cache_key` logic.
*   **UI Performance**: Use Streamlit's `@st.cache_data` for repeatable UI-level computations to ensure a snappy user experience.

## 6. Development Workflow

1.  **Research**: Map dependencies and identify the minimal path to implementation.
2.  **Strategy**: Formulate a plan that prioritizes the least disruptive, most maintainable change.
3.  **Act**: Apply surgical edits. Use `replace` for targeted updates to large files.
4.  **Validate**: Run tests, check linting, and verify manual use cases.

