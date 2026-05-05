"""Tests for core.fetch_utils: FetchCheckpoint and retry_with_backoff."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import requests

from core.fetch_utils import (
    CHECKPOINT_MAX_AGE_HOURS,
    FetchCheckpoint,
    _flatten_track,
    _unflatten_track,
    retry_with_backoff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_TRACK = {
    "artist": {"#text": "Radiohead"},
    "album": {"#text": "OK Computer"},
    "name": "Karma Police",
    "date": {"uts": "1610000000", "#text": "07 Jan 2021, 10:00"},
}


def _make_checkpoint(tmp_dir: str, **kwargs: object) -> FetchCheckpoint:
    """Return a FetchCheckpoint rooted at tmp_dir with sensible defaults."""
    return FetchCheckpoint(
        checkpoint_dir=tmp_dir,
        plugin_id=str(kwargs.get("plugin_id", "lastfm")),
        identity=str(kwargs.get("identity", "@testuser")),
        from_ts=kwargs.get("from_ts", None),  # type: ignore[arg-type]
        to_ts=kwargs.get("to_ts", None),  # type: ignore[arg-type]
        pages_limit=kwargs.get("pages_limit", None),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# FetchCheckpoint — basic round-trip
# ---------------------------------------------------------------------------


class TestFetchCheckpointRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_load_returns_none_when_no_file(self) -> None:
        cp = _make_checkpoint(self.tmp)
        self.assertIsNone(cp.load())

    def test_save_then_load_returns_page_and_tracks(self) -> None:
        cp = _make_checkpoint(self.tmp)
        cp.save(1, 10, [_SAMPLE_TRACK])

        result = cp.load()
        self.assertIsNotNone(result)
        assert result is not None
        last_page, tracks = result
        self.assertEqual(last_page, 1)
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["name"], "Karma Police")
        self.assertEqual(tracks[0]["artist"]["#text"], "Radiohead")

    def test_save_multiple_pages_accumulates_tracks(self) -> None:
        cp = _make_checkpoint(self.tmp)
        cp.save(1, 3, [_SAMPLE_TRACK])
        cp.save(2, 3, [_SAMPLE_TRACK, _SAMPLE_TRACK])
        cp.save(3, 3, [_SAMPLE_TRACK])

        result = cp.load()
        assert result is not None
        last_page, tracks = result
        self.assertEqual(last_page, 3)
        self.assertEqual(len(tracks), 4)

    def test_tracks_fetched_property_reflects_accumulated_count(self) -> None:
        cp = _make_checkpoint(self.tmp)
        cp.save(1, 5, [_SAMPLE_TRACK, _SAMPLE_TRACK])
        cp.save(2, 5, [_SAMPLE_TRACK])
        self.assertEqual(cp.tracks_fetched, 3)

    def test_tracks_fetched_updated_after_load(self) -> None:
        cp_writer = _make_checkpoint(self.tmp)
        cp_writer.save(1, 5, [_SAMPLE_TRACK, _SAMPLE_TRACK])

        cp_reader = _make_checkpoint(self.tmp)
        cp_reader.load()
        self.assertEqual(cp_reader.tracks_fetched, 2)

    def test_clear_removes_checkpoint_files(self) -> None:
        cp = _make_checkpoint(self.tmp)
        cp.save(1, 5, [_SAMPLE_TRACK])
        cp.clear()

        self.assertIsNone(cp.load())

    def test_load_after_corrupt_json_returns_none(self) -> None:
        cp = _make_checkpoint(self.tmp)
        cp.save(1, 2, [_SAMPLE_TRACK])

        # Corrupt the state file.
        with open(cp._state_path, "w") as fh:
            fh.write("not valid json{{{")

        self.assertIsNone(cp.load())


# ---------------------------------------------------------------------------
# FetchCheckpoint — stale detection
# ---------------------------------------------------------------------------


class TestFetchCheckpointStale(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def _write_state(self, cp: FetchCheckpoint, created_at: datetime) -> None:
        """Write a minimal state file with a given creation timestamp."""
        os.makedirs(self.tmp, exist_ok=True)
        state = {
            "created_at": created_at.isoformat(),
            "last_completed_page": 5,
            "total_pages": 10,
            "tracks_fetched": 1000,
            "updated_at": created_at.isoformat(),
        }
        with open(cp._state_path, "w") as fh:
            json.dump(state, fh)

    def test_fresh_checkpoint_loads_without_error(self) -> None:
        cp = _make_checkpoint(self.tmp)
        self._write_state(cp, datetime.now(tz=timezone.utc) - timedelta(hours=1))
        result = cp.load()
        self.assertIsNotNone(result)

    def test_stale_checkpoint_raises_value_error(self) -> None:
        cp = _make_checkpoint(self.tmp)
        old_ts = datetime.now(tz=timezone.utc) - timedelta(hours=CHECKPOINT_MAX_AGE_HOURS + 1)
        self._write_state(cp, old_ts)

        with self.assertRaises(ValueError) as ctx:
            cp.load()
        self.assertIn("stale", str(ctx.exception).lower())

    def test_boundary_at_max_age_is_not_stale(self) -> None:
        cp = _make_checkpoint(self.tmp)
        # Exactly at the limit (minus a small buffer) — should NOT be stale.
        borderline = datetime.now(tz=timezone.utc) - timedelta(hours=CHECKPOINT_MAX_AGE_HOURS - 1)
        self._write_state(cp, borderline)
        self.assertIsNotNone(cp.load())


# ---------------------------------------------------------------------------
# FetchCheckpoint — key isolation (mismatched params = different checkpoint)
# ---------------------------------------------------------------------------


class TestFetchCheckpointKeyIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def test_different_from_ts_produces_different_checkpoint(self) -> None:
        cp1 = _make_checkpoint(self.tmp, from_ts=1000)
        cp2 = _make_checkpoint(self.tmp, from_ts=2000)

        cp1.save(1, 5, [_SAMPLE_TRACK])

        # cp2 has a different key so it should not see cp1's checkpoint.
        self.assertIsNone(cp2.load())

    def test_different_identity_produces_different_checkpoint(self) -> None:
        cp_alice = _make_checkpoint(self.tmp, identity="@alice")
        cp_bob = _make_checkpoint(self.tmp, identity="@bob")

        cp_alice.save(1, 5, [_SAMPLE_TRACK])
        self.assertIsNone(cp_bob.load())

    def test_no_resume_does_not_read_existing_checkpoint(self) -> None:
        """A checkpoint from a previous run is simply ignored when not resumed."""
        cp_prev = _make_checkpoint(self.tmp)
        cp_prev.save(3, 10, [_SAMPLE_TRACK])

        # A fresh FetchCheckpoint instance for the same params still finds the file,
        # but callers using --resume=False simply never call .load() on it.
        cp_new = _make_checkpoint(self.tmp)
        # Calling load() would return data, but _run_fetch skips this when resume=False.
        result = cp_new.load()
        # Confirm the data IS there (the checkpoint itself is not cleared on fresh runs
        # until the new run completes and calls clear()).
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# Flatten / unflatten helpers
# ---------------------------------------------------------------------------


class TestFlattenUnflatten(unittest.TestCase):
    def test_roundtrip_preserves_all_fields(self) -> None:
        flat = _flatten_track(_SAMPLE_TRACK)
        restored = _unflatten_track(flat)
        self.assertEqual(restored["name"], "Karma Police")
        self.assertEqual(restored["artist"]["#text"], "Radiohead")
        self.assertEqual(restored["album"]["#text"], "OK Computer")
        self.assertEqual(restored["date"]["uts"], "1610000000")

    def test_flatten_handles_missing_nested_keys(self) -> None:
        track: dict = {"name": "No Meta"}
        flat = _flatten_track(track)
        self.assertEqual(flat["artist__text"], "")
        self.assertEqual(flat["date__uts"], "")


# ---------------------------------------------------------------------------
# retry_with_backoff
# ---------------------------------------------------------------------------


class TestRetryWithBackoff(unittest.TestCase):
    def test_success_on_first_try(self) -> None:
        fn = MagicMock(return_value="ok")
        result = retry_with_backoff(fn, base_delay=0)
        self.assertEqual(result, "ok")
        fn.assert_called_once()

    def test_retries_and_succeeds_on_second_attempt(self) -> None:
        exc = requests.exceptions.ConnectionError("timeout")
        fn = MagicMock(side_effect=[exc, "ok"])
        result = retry_with_backoff(fn, max_retries=3, base_delay=0)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.call_count, 2)

    def test_raises_after_max_retries_exhausted(self) -> None:
        exc = requests.exceptions.ConnectionError("timeout")
        fn = MagicMock(side_effect=exc)
        with self.assertRaises(requests.exceptions.RequestException):
            retry_with_backoff(fn, max_retries=2, base_delay=0)
        self.assertEqual(fn.call_count, 3)  # initial + 2 retries

    def test_on_retry_callback_invoked_for_each_retry(self) -> None:
        exc = requests.exceptions.ConnectionError("timeout")
        fn = MagicMock(side_effect=[exc, exc, "ok"])
        on_retry = MagicMock()

        retry_with_backoff(fn, max_retries=3, base_delay=0, on_retry=on_retry)

        self.assertEqual(on_retry.call_count, 2)
        on_retry.assert_any_call(1, exc)
        on_retry.assert_any_call(2, exc)

    def test_non_request_exception_propagates_immediately(self) -> None:
        fn = MagicMock(side_effect=ValueError("unrelated"))
        with self.assertRaises(ValueError):
            retry_with_backoff(fn, max_retries=3, base_delay=0)
        fn.assert_called_once()

    def test_http_error_is_retried(self) -> None:
        exc = requests.exceptions.HTTPError("429")
        fn = MagicMock(side_effect=[exc, "ok"])
        result = retry_with_backoff(fn, max_retries=3, base_delay=0)
        self.assertEqual(result, "ok")

    @patch("core.fetch_utils.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep: MagicMock) -> None:
        exc = requests.exceptions.ConnectionError("timeout")
        fn = MagicMock(side_effect=[exc, exc, "ok"])
        retry_with_backoff(fn, max_retries=3, base_delay=1.0)
        # First retry: 1.0s, second retry: 2.0s
        mock_sleep.assert_has_calls([call(1.0), call(2.0)])


if __name__ == "__main__":
    unittest.main()
