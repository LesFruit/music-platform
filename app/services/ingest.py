"""Ingest flow for music-gen pipeline outputs into the published catalog.

This module handles:
- Scanning music-gen output directories for completed jobs
- Reading manifest.json files for metadata
- Copying publishable assets to canonical D-drive-backed storage
- Registering tracks in the music-platform catalog
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import settings
from app.db import get_conn

log = logging.getLogger(__name__)

SourceType = Literal["cover-piano", "cover-orchestra"]

PUBLISHABLE_ARTIFACTS = {
    "cover_piano_wav": "cover-piano",
    "cover_orchestra_wav": "cover-orchestra",
}


@dataclass(frozen=True, slots=True)
class IngestResult:
    job_id: str
    source_type: SourceType
    track_id: str | None
    dest_path: Path | None
    status: Literal["ingested", "skipped", "failed"]
    message: str


def _track_id(source: str, rel_path: str) -> str:
    """Generate a consistent track ID from source and relative path."""
    return hashlib.sha1(f"{source}:{rel_path}".encode("utf-8")).hexdigest()[:16]


def _read_manifest(manifest_path: Path) -> dict | None:
    """Read and parse a manifest.json file."""
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        log.warning("Failed to read manifest %s: %s", manifest_path, e)
        return None


def _get_canonical_dir(source_type: SourceType) -> Path:
    """Get the canonical storage directory for a source type.
    
    Uses the ace-step directory as the base for cover outputs.
    """
    base_dir = Path(settings.acestep_dir).parent if hasattr(settings, 'acestep_dir') else Path("/host/d/Music")
    canonical_dir = base_dir / "covers" / source_type.replace("-", "_")
    canonical_dir.mkdir(parents=True, exist_ok=True)
    return canonical_dir


def _copy_artifact(src_path: Path, dest_dir: Path, job_id: str) -> Path | None:
    """Copy an artifact to canonical storage with a stable filename.
    
    Returns the destination path on success, None on failure.
    """
    if not src_path.exists():
        log.warning("Source artifact does not exist: %s", src_path)
        return None
    
    # Use job_id as the base name for stability
    dest_name = f"{job_id}{src_path.suffix}"
    dest_path = dest_dir / dest_name
    
    try:
        # Copy with metadata preservation
        shutil.copy2(src_path, dest_path)
        log.info("Copied %s -> %s", src_path, dest_path)
        return dest_path
    except (shutil.Error, OSError) as e:
        log.error("Failed to copy %s to %s: %s", src_path, dest_path, e)
        return None


def _register_track(
    track_id: str,
    source: str,
    name: str,
    path: str,
    rel_path: str,
    size_bytes: int,
    mtime_ns: int,
    duration_sec: float | None = None,
    metadata: dict | None = None,
) -> bool:
    """Register a track in the catalog database.
    
    Upserts the track record and optionally metadata.
    """
    try:
        with get_conn() as conn:
            # Upsert track
            conn.execute(
                """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, path=excluded.path, rel_path=excluded.rel_path,
                     size_bytes=excluded.size_bytes, mtime_ns=excluded.mtime_ns,
                     duration_sec=COALESCE(excluded.duration_sec, tracks.duration_sec),
                     indexed_at=datetime('now')""",
                (track_id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec),
            )
            
            # Upsert metadata if provided
            if metadata:
                meta_fields = {
                    k: v for k, v in metadata.items()
                    if k in ("title", "artist", "album", "genre", "bpm", "key", "mood", "energy", "tags", "description")
                }
                if meta_fields:
                    cols = ", ".join(meta_fields.keys())
                    placeholders = ", ".join("?" for _ in meta_fields)
                    updates = ", ".join(f"{k}=excluded.{k}" for k in meta_fields)
                    conn.execute(
                        f"INSERT INTO track_metadata (track_id, {cols}) VALUES (?, {placeholders}) "
                        f"ON CONFLICT(track_id) DO UPDATE SET {updates}, updated_at=datetime('now')",
                        [track_id, *meta_fields.values()],
                    )
            
            conn.commit()
        return True
    except Exception as e:
        log.error("Failed to register track %s: %s", track_id, e)
        return False


def ingest_job(manifest_path: Path, dry_run: bool = False) -> list[IngestResult]:
    """Ingest a single music-gen job from its manifest.
    
    Args:
        manifest_path: Path to the manifest.json file
        dry_run: If True, only report what would be done without making changes
        
    Returns:
        List of IngestResult, one per publishable artifact found
    """
    results: list[IngestResult] = []
    manifest = _read_manifest(manifest_path)
    
    if not manifest:
        return [IngestResult(
            job_id="unknown",
            source_type="cover-piano",
            track_id=None,
            dest_path=None,
            status="failed",
            message=f"Could not read manifest: {manifest_path}",
        )]
    
    job_id = manifest.get("job_id", manifest_path.parent.name)
    artifacts = manifest.get("artifacts", {})
    input_info = manifest.get("input", {})
    metrics = manifest.get("metrics", {})
    
    for artifact_key, source_type in PUBLISHABLE_ARTIFACTS.items():
        artifact_path_str = artifacts.get(artifact_key)
        if not artifact_path_str:
            continue
        
        artifact_path = Path(artifact_path_str)
        if not artifact_path.exists():
            results.append(IngestResult(
                job_id=job_id,
                source_type=source_type,
                track_id=None,
                dest_path=None,
                status="failed",
                message=f"Artifact file missing: {artifact_path}",
            ))
            continue
        
        # Determine canonical destination
        canonical_dir = _get_canonical_dir(source_type)
        
        # Generate track ID
        rel_path = f"{source_type}/{job_id}{artifact_path.suffix}"
        track_id = _track_id(source_type, rel_path)
        dest_path = canonical_dir / f"{job_id}{artifact_path.suffix}"
        
        # Check if already ingested
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM tracks WHERE id = ?", (track_id,)
            ).fetchone()
        
        if existing and not dry_run:
            results.append(IngestResult(
                job_id=job_id,
                source_type=source_type,
                track_id=track_id,
                dest_path=dest_path,
                status="skipped",
                message="Track already in catalog",
            ))
            continue
        
        if dry_run:
            results.append(IngestResult(
                job_id=job_id,
                source_type=source_type,
                track_id=track_id,
                dest_path=dest_path,
                status="skipped",
                message=f"[DRY RUN] Would ingest {artifact_path} -> {dest_path}",
            ))
            continue
        
        # Copy artifact to canonical storage
        copied_path = _copy_artifact(artifact_path, canonical_dir, job_id)
        if not copied_path:
            results.append(IngestResult(
                job_id=job_id,
                source_type=source_type,
                track_id=track_id,
                dest_path=None,
                status="failed",
                message=f"Failed to copy artifact: {artifact_path}",
            ))
            continue
        
        # Get file stats
        stat = copied_path.stat()
        
        # Build metadata from manifest
        metadata: dict[str, str | float] = {
            "title": f"Cover ({source_type.replace('-', ' ').title()})",
            "artist": "AI Cover",
            "description": f"Generated cover from {input_info.get('path', 'unknown input')}",
        }
        if metrics.get("duration_s"):
            metadata["duration_sec"] = metrics["duration_s"]
        
        # Register in catalog
        success = _register_track(
            track_id=track_id,
            source=source_type,
            name=copied_path.name,
            path=str(copied_path),
            rel_path=rel_path,
            size_bytes=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            duration_sec=metrics.get("duration_s"),
            metadata=metadata,
        )
        
        if success:
            results.append(IngestResult(
                job_id=job_id,
                source_type=source_type,
                track_id=track_id,
                dest_path=copied_path,
                status="ingested",
                message=f"Successfully ingested to {copied_path}",
            ))
        else:
            results.append(IngestResult(
                job_id=job_id,
                source_type=source_type,
                track_id=track_id,
                dest_path=copied_path,
                status="failed",
                message="Failed to register in catalog",
            ))
    
    return results


def scan_and_ingest(
    output_dir: Path | str,
    *,
    dry_run: bool = False,
    job_id_filter: str | None = None,
) -> dict:
    """Scan a music-gen output directory and ingest all completed jobs.
    
    Args:
        output_dir: Directory containing job subdirectories with manifest.json files
        dry_run: If True, only report what would be done
        job_id_filter: If provided, only process this specific job ID
        
    Returns:
        Stats dict with counts of ingested, skipped, failed
    """
    output_path = Path(output_dir)
    if not output_path.exists():
        log.error("Output directory does not exist: %s", output_path)
        return {"ingested": 0, "skipped": 0, "failed": 0, "errors": [f"Directory not found: {output_path}"]}
    
    ingested = 0
    skipped = 0
    failed = 0
    errors: list[str] = []
    
    # Find all manifest.json files
    if job_id_filter:
        # Single job mode
        manifest_paths = [output_path / job_id_filter / "manifest.json"]
    else:
        # Scan all subdirectories
        manifest_paths = list(output_path.rglob("*/manifest.json"))
    
    log.info("Found %d manifest(s) to process in %s", len(manifest_paths), output_path)
    
    for manifest_path in manifest_paths:
        if not manifest_path.exists():
            errors.append(f"Manifest not found: {manifest_path}")
            failed += 1
            continue
        
        results = ingest_job(manifest_path, dry_run=dry_run)
        
        for result in results:
            if result.status == "ingested":
                ingested += 1
            elif result.status == "skipped":
                skipped += 1
            else:
                failed += 1
                errors.append(f"{result.job_id}/{result.source_type}: {result.message}")
    
    stats = {
        "ingested": ingested,
        "skipped": skipped,
        "failed": failed,
        "manifests_processed": len(manifest_paths),
        "errors": errors if errors else None,
    }
    
    log.info("Ingest complete: %d ingested, %d skipped, %d failed", ingested, skipped, failed)
    return stats
