from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from app.config import settings
from app.db import get_conn

log = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}

SOURCES: list[tuple[str, str]] = [
    (settings.suno_dir, "suno"),
    (settings.acestep_dir, "ace-step"),
    (settings.diffrhythm_dir, "diffrhythm"),
    (settings.heartmula_dir, "heartmula"),
    (settings.stable_audio_dir, "stable-audio"),
    (settings.cover_piano_dir, "cover-piano"),
    (settings.cover_orchestra_dir, "cover-orchestra"),
]


def _track_id(source: str, rel: str) -> str:
    return hashlib.sha1(f"{source}:{rel}".encode("utf-8")).hexdigest()[:16]


def _try_duration(path: Path) -> float | None:
    """Best-effort duration extraction via mutagen or soundfile.
    
    Tries mutagen first (for mp3, flac, etc.), then falls back to soundfile
    for WAV and other formats.
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


def reindex(*, with_duration: bool = False) -> dict:
    """Scan all source dirs and upsert into the tracks table.

    Returns stats dict with counts.
    """
    t0 = time.monotonic()
    found_ids: list[str] = []
    upserted = 0
    removed = 0

    with get_conn() as conn:
        for dir_path, source_name in SOURCES:
            base = Path(dir_path)
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
                    continue
                rel = p.relative_to(base).as_posix()
                tid = _track_id(source_name, rel)
                stat = p.stat()
                found_ids.append(tid)

                existing = conn.execute(
                    "SELECT mtime_ns FROM tracks WHERE id = ?", (tid,)
                ).fetchone()

                if existing and existing["mtime_ns"] == stat.st_mtime_ns:
                    continue

                dur = _try_duration(p) if with_duration else None

                conn.execute(
                    """INSERT INTO tracks (id, source, name, path, rel_path, size_bytes, mtime_ns, duration_sec)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         name=excluded.name, path=excluded.path, rel_path=excluded.rel_path,
                         size_bytes=excluded.size_bytes, mtime_ns=excluded.mtime_ns,
                         duration_sec=COALESCE(excluded.duration_sec, tracks.duration_sec),
                         indexed_at=datetime('now')""",
                    (tid, source_name, p.name, str(p), rel, stat.st_size, stat.st_mtime_ns, dur),
                )
                upserted += 1

        # Remove tracks whose files no longer exist on disk
        if found_ids:
            placeholders = ",".join("?" for _ in found_ids)
            cur = conn.execute(
                f"DELETE FROM tracks WHERE id NOT IN ({placeholders})", found_ids
            )
            removed = cur.rowcount
        else:
            cur = conn.execute("DELETE FROM tracks")
            removed = cur.rowcount

        conn.commit()

    elapsed = round(time.monotonic() - t0, 2)
    log.info("reindex done: upserted=%d removed=%d elapsed=%.2fs", upserted, removed, elapsed)
    return {"upserted": upserted, "removed": removed, "total": len(found_ids), "elapsed_sec": elapsed}
