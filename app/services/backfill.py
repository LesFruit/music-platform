"""Backfill operations for catalog maintenance.

This module provides operations to backfill missing metadata
for existing tracks in the catalog.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Literal

from app.db import get_conn

log = logging.getLogger(__name__)


def _try_get_duration(path: Path) -> float | None:
    """Best-effort duration extraction via mutagen or soundfile.
    
    Tries mutagen first (for mp3, flac, etc.), then falls back to soundfile
    for WAV and other formats.
    
    Returns None if:
    - File doesn't exist
    - No supported library can read the file
    - Any error occurs during parsing
    """
    # Try mutagen first (handles mp3, flac, etc.)
    try:
        from mutagen import File as MutagenFile
        m = MutagenFile(str(path))
        if m and m.info:
            return round(m.info.length, 2)
    except Exception:
        pass
    
    # Fall back to soundfile for WAV and other formats
    try:
        import soundfile as sf
        info = sf.info(str(path))
        if info and info.duration:
            return round(info.duration, 2)
    except Exception:
        pass
    
    return None


def backfill_duration(
    *,
    source: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Backfill duration metadata for tracks missing it.
    
    Args:
        source: If provided, only backfill tracks from this source
        dry_run: If True, only report what would be done without making changes
        limit: Maximum number of tracks to process (None for all)
        
    Returns:
        Stats dict with:
        - processed: number of tracks checked
        - updated: number of tracks with duration added
        - failed: number of tracks that couldn't be read
        - skipped: number of tracks skipped (file not found or no duration info)
        - elapsed_sec: time taken
    """
    t0 = time.monotonic()
    
    with get_conn() as conn:
        # Build query
        query = "SELECT id, path, duration_sec FROM tracks WHERE duration_sec IS NULL"
        params: list = []
        
        if source:
            query += " AND source = ?"
            params.append(source)
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
    
    processed = 0
    updated = 0
    failed = 0
    skipped = 0
    
    for row in rows:
        processed += 1
        track_id = row["id"]
        path = Path(row["path"])
        
        if not path.exists():
            log.warning("Track file not found: %s (%s)", track_id, path)
            skipped += 1
            continue
        
        duration = _try_get_duration(path)
        
        if duration is None:
            log.debug("Could not extract duration for: %s (%s)", track_id, path)
            skipped += 1
            continue
        
        if dry_run:
            log.info("[DRY RUN] Would update %s with duration %.2fs", track_id, duration)
            updated += 1
            continue
        
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE tracks SET duration_sec = ? WHERE id = ?",
                    (duration, track_id),
                )
                conn.commit()
            log.info("Updated %s with duration %.2fs", track_id, duration)
            updated += 1
        except Exception as e:
            log.error("Failed to update %s: %s", track_id, e)
            failed += 1
    
    elapsed = round(time.monotonic() - t0, 2)
    
    result = {
        "processed": processed,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
        "elapsed_sec": elapsed,
        "dry_run": dry_run,
    }
    
    log.info(
        "Duration backfill complete: processed=%d updated=%d skipped=%d failed=%d elapsed=%.2fs",
        processed, updated, skipped, failed, elapsed
    )
    
    return result


def get_backfill_status() -> dict:
    """Get current status of metadata backfill needs.
    
    Returns:
        Dict with counts of tracks missing various metadata fields
    """
    with get_conn() as conn:
        # Overall counts
        total_row = conn.execute("SELECT COUNT(*) as cnt FROM tracks").fetchone()
        total = total_row["cnt"] if total_row else 0
        
        missing_duration_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM tracks WHERE duration_sec IS NULL"
        ).fetchone()
        missing_duration = missing_duration_row["cnt"] if missing_duration_row else 0
        
        # By source breakdown
        rows = conn.execute(
            """SELECT 
                source,
                COUNT(*) as total,
                SUM(CASE WHEN duration_sec IS NULL THEN 1 ELSE 0 END) as missing_duration
               FROM tracks
               GROUP BY source"""
        ).fetchall()
        
        by_source = {
            r["source"]: {
                "total": r["total"],
                "missing_duration": r["missing_duration"],
            }
            for r in rows
        }
    
    return {
        "total_tracks": total,
        "missing_duration": missing_duration,
        "missing_duration_ratio": round(missing_duration / total, 4) if total > 0 else 0,
        "by_source": by_source,
    }
