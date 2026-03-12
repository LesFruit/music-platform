from __future__ import annotations

import sqlite3
from pathlib import Path
from contextlib import contextmanager

from app.config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  cover_image TEXT,
  share_code TEXT UNIQUE,
  is_public INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
  playlist_id INTEGER NOT NULL,
  track_id TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (playlist_id, track_id),
  FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generation_jobs (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  prompt TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracks (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  name TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  rel_path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  mtime_ns INTEGER NOT NULL DEFAULT 0,
  duration_sec REAL,
  indexed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tracks_source ON tracks(source);
CREATE INDEX IF NOT EXISTS idx_tracks_name ON tracks(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS track_metadata (
  track_id TEXT PRIMARY KEY,
  title TEXT,
  artist TEXT,
  album TEXT,
  genre TEXT,
  bpm REAL,
  key TEXT,
  mood TEXT,
  energy REAL,
  tags TEXT,
  description TEXT,
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);
"""


def _ensure_db_parent() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    _ensure_db_parent()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migrate existing playlists table if needed
        try:
            conn.execute("ALTER TABLE playlists ADD COLUMN cover_image TEXT")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE playlists ADD COLUMN share_code TEXT UNIQUE")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE playlists ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE playlists ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now'))")
        except Exception:
            pass
        # Migrate playlist_tracks to add position if needed
        try:
            conn.execute("ALTER TABLE playlist_tracks ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        conn.commit()
