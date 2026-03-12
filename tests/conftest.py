"""Pytest fixtures for music-platform tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from contextlib import contextmanager

import pytest

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


def _get_test_conn(db_path: Path) -> sqlite3.Connection:
    """Get a connection to a test database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class _DbConnContextManager:
    """A reusable context manager for test database connections."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
    
    def __enter__(self):
        self._conn = _get_test_conn(self.db_path)
        return self._conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._conn.close()
        return False


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Provide a temporary database connection context manager for tests.
    
    This fixture creates a temporary database, initializes it with the schema,
    and patches the app's database path to use it. Use as:
        with db_conn as conn:
            ...
    """
    test_db_path = tmp_path / "test.db"
    
    # Initialize the test database
    conn = _get_test_conn(test_db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    
    # Patch settings to use the test database
    monkeypatch.setattr(settings, "db_path", str(test_db_path))
    
    # Return a reusable context manager
    return _DbConnContextManager(test_db_path)
