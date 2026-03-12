"""Tests for backfill service."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.services.backfill import _try_get_duration, backfill_duration, get_backfill_status


class TestTryGetDuration:
    """Tests for _try_get_duration function."""

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        """Should return None if file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.mp3"
        result = _try_get_duration(nonexistent)
        assert result is None

    def test_extracts_duration_from_mp3(self, tmp_path):
        """Should extract duration from MP3 files using mutagen."""
        # Create a mock MP3 file
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"fake mp3 data")
        
        # Mock mutagen to return a duration
        mock_info = MagicMock()
        mock_info.length = 123.456
        mock_file = MagicMock()
        mock_file.info = mock_info
        
        with patch("mutagen.File", return_value=mock_file):
            result = _try_get_duration(mp3_path)
            assert result == 123.46  # rounded to 2 decimal places

    def test_extracts_duration_from_wav_using_soundfile(self, tmp_path):
        """Should extract duration from WAV files using soundfile."""
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"fake wav data")
        
        # Mock mutagen to fail (returns None)
        with patch("mutagen.File", return_value=None):
            # Mock soundfile to return duration
            mock_info = MagicMock()
            mock_info.duration = 456.789
            
            with patch("soundfile.info", return_value=mock_info):
                result = _try_get_duration(wav_path)
                assert result == 456.79  # rounded to 2 decimal places

    def test_returns_none_when_both_libraries_fail(self, tmp_path):
        """Should return None when both mutagen and soundfile fail."""
        audio_path = tmp_path / "test.unknown"
        audio_path.write_bytes(b"unknown format")
        
        with patch("mutagen.File", side_effect=Exception("mutagen error")):
            with patch("soundfile.info", side_effect=Exception("soundfile error")):
                result = _try_get_duration(audio_path)
                assert result is None


class TestBackfillDuration:
    """Tests for backfill_duration function."""

    def test_dry_run_does_not_modify_database(self, db_conn, tmp_path):
        """Dry run should not make any changes to the database."""
        # Create a test track with missing duration
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"fake mp3 data")
        
        with db_conn as conn:
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test123", "suno", "test.mp3", str(mp3_path), "test.mp3", 100, 1234567890, None),
            )
            conn.commit()
        
        # Mock duration extraction
        with patch("app.services.backfill._try_get_duration", return_value=120.5):
            result = backfill_duration(dry_run=True)
        
        assert result["dry_run"] is True
        assert result["processed"] == 1
        assert result["updated"] == 1  # Would update
        
        # Verify database was NOT modified
        with db_conn as conn:
            row = conn.execute("SELECT duration_sec FROM tracks WHERE id = ?", ("test123",)).fetchone()
            assert row["duration_sec"] is None

    def test_actual_run_updates_database(self, db_conn, tmp_path):
        """Actual run should update the database."""
        # Create a test track with missing duration
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"fake mp3 data")
        
        with db_conn as conn:
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test123", "suno", "test.mp3", str(mp3_path), "test.mp3", 100, 1234567890, None),
            )
            conn.commit()
        
        # Mock duration extraction
        with patch("app.services.backfill._try_get_duration", return_value=120.5):
            result = backfill_duration(dry_run=False)
        
        assert result["dry_run"] is False
        assert result["processed"] == 1
        assert result["updated"] == 1
        
        # Verify database WAS modified
        with db_conn as conn:
            row = conn.execute("SELECT duration_sec FROM tracks WHERE id = ?", ("test123",)).fetchone()
            assert row["duration_sec"] == 120.5

    def test_skips_tracks_with_existing_duration(self, db_conn, tmp_path):
        """Should skip tracks that already have duration."""
        mp3_path = tmp_path / "test.mp3"
        mp3_path.write_bytes(b"fake mp3 data")
        
        with db_conn as conn:
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test123", "suno", "test.mp3", str(mp3_path), "test.mp3", 100, 1234567890, 60.0),
            )
            conn.commit()
        
        result = backfill_duration()
        
        assert result["processed"] == 0  # No tracks to process
        assert result["updated"] == 0

    def test_skips_missing_files(self, db_conn):
        """Should skip tracks whose files don't exist."""
        with db_conn as conn:
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test123", "suno", "test.mp3", "/nonexistent/path/test.mp3", "test.mp3", 100, 1234567890, None),
            )
            conn.commit()
        
        result = backfill_duration()
        
        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert result["updated"] == 0

    def test_respects_source_filter(self, db_conn, tmp_path):
        """Should only process tracks from specified source."""
        suno_path = tmp_path / "suno.mp3"
        suno_path.write_bytes(b"fake mp3 data")
        ace_path = tmp_path / "ace.mp3"
        ace_path.write_bytes(b"fake mp3 data")
        
        with db_conn as conn:
            # Track from suno
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("suno1", "suno", "suno.mp3", str(suno_path), "suno.mp3", 100, 1234567890, None),
            )
            # Track from ace-step
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("ace1", "ace-step", "ace.mp3", str(ace_path), "ace.mp3", 100, 1234567890, None),
            )
            conn.commit()
        
        with patch("app.services.backfill._try_get_duration", return_value=120.5):
            result = backfill_duration(source="suno")
        
        assert result["processed"] == 1
        assert result["updated"] == 1

    def test_respects_limit(self, db_conn, tmp_path):
        """Should respect the limit parameter."""
        with db_conn as conn:
            for i in range(5):
                mp3_path = tmp_path / f"test{i}.mp3"
                mp3_path.write_bytes(b"fake mp3 data")
                conn.execute(
                    """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f"test{i}", "suno", f"test{i}.mp3", str(mp3_path), f"test{i}.mp3", 100, 1234567890, None),
                )
            conn.commit()
        
        with patch("app.services.backfill._try_get_duration", return_value=120.5):
            result = backfill_duration(limit=3)
        
        assert result["processed"] == 3


class TestGetBackfillStatus:
    """Tests for get_backfill_status function."""

    def test_returns_correct_counts(self, db_conn, tmp_path):
        """Should return correct counts of tracks missing metadata."""
        with db_conn as conn:
            # 3 tracks with duration
            for i in range(3):
                mp3_path = tmp_path / f"with{i}.mp3"
                mp3_path.write_bytes(b"fake mp3 data")
                conn.execute(
                    """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f"with{i}", "suno", f"with{i}.mp3", str(mp3_path), f"with{i}.mp3", 100, 1234567890, 60.0),
                )
            # 2 tracks without duration
            for i in range(2):
                mp3_path = tmp_path / f"without{i}.mp3"
                mp3_path.write_bytes(b"fake mp3 data")
                conn.execute(
                    """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f"without{i}", "ace-step", f"without{i}.mp3", str(mp3_path), f"without{i}.mp3", 100, 1234567890, None),
                )
            conn.commit()
        
        status = get_backfill_status()
        
        assert status["total_tracks"] == 5
        assert status["missing_duration"] == 2
        assert status["missing_duration_ratio"] == 0.4
        assert "suno" in status["by_source"]
        assert "ace-step" in status["by_source"]
        assert status["by_source"]["suno"]["missing_duration"] == 0
        assert status["by_source"]["ace-step"]["missing_duration"] == 2

    def test_handles_empty_database(self, db_conn):
        """Should handle empty database gracefully."""
        status = get_backfill_status()
        
        assert status["total_tracks"] == 0
        assert status["missing_duration"] == 0
        assert status["missing_duration_ratio"] == 0
        assert status["by_source"] == {}
