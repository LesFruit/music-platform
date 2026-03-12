"""Tests for the ingest service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# Ensure app is importable
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ingest import _track_id, ingest_job, scan_and_ingest


def test_track_id_generation():
    """Track IDs should be deterministic based on source and path."""
    id1 = _track_id("cover-piano", "cover-piano/test.wav")
    id2 = _track_id("cover-piano", "cover-piano/test.wav")
    id3 = _track_id("cover-orchestra", "cover-piano/test.wav")
    
    assert id1 == id2, "Same source+path should produce same ID"
    assert id1 != id3, "Different source should produce different ID"
    assert len(id1) == 16, "Track ID should be 16 chars"


def test_ingest_job_dry_run():
    """Dry run should not modify anything."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock manifest
        job_dir = Path(tmpdir) / "test-job-123"
        job_dir.mkdir()
        
        # Create a dummy audio file
        audio_file = job_dir / "cover_piano.wav"
        audio_file.write_bytes(b"dummy wav data")
        
        # Create manifest
        manifest = {
            "job_id": "test-job-123",
            "input": {"path": "/input/test.mp3", "duration_s": 120.5, "sr": 44100},
            "artifacts": {
                "cover_piano_wav": str(audio_file),
                "normalized_audio": str(job_dir / "normalized.wav"),
            },
            "metrics": {"duration_s": 120.5},
        }
        manifest_file = job_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest))
        
        # Run dry-run ingest
        results = ingest_job(manifest_file, dry_run=True)
        
        assert len(results) == 1
        assert results[0].status == "skipped"
        assert results[0].job_id == "test-job-123"
        assert "DRY RUN" in results[0].message


def test_scan_and_ingest_empty_dir():
    """Scanning an empty directory should return empty stats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        stats = scan_and_ingest(tmpdir)
        assert stats["ingested"] == 0
        assert stats["skipped"] == 0
        assert stats["failed"] == 0


def test_scan_and_ingest_missing_dir():
    """Scanning a non-existent directory should report error."""
    stats = scan_and_ingest("/nonexistent/path/12345")
    assert stats["failed"] == 0  # No manifests processed
    assert stats["errors"] is not None
    assert "Directory not found" in stats["errors"][0]


def test_ingest_job_missing_artifact():
    """Ingest should handle missing artifact files gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_dir = Path(tmpdir) / "test-job-456"
        job_dir.mkdir()
        
        # Create manifest pointing to non-existent file
        manifest = {
            "job_id": "test-job-456",
            "input": {"path": "/input/test.mp3", "duration_s": 60.0, "sr": 44100},
            "artifacts": {
                "cover_piano_wav": str(job_dir / "missing.wav"),
            },
        }
        manifest_file = job_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest))
        
        results = ingest_job(manifest_file, dry_run=True)
        
        assert len(results) == 1
        assert results[0].status == "failed"
        assert "missing" in results[0].message.lower()


def test_ingest_job_invalid_manifest():
    """Ingest should handle invalid manifest files gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_file = Path(tmpdir) / "manifest.json"
        manifest_file.write_text("not valid json")
        
        results = ingest_job(manifest_file)
        
        assert len(results) == 1
        assert results[0].status == "failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
