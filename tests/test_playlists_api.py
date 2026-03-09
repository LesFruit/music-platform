from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.main import app


def _configure_paths(tmp_path: Path) -> None:
    base = tmp_path / "media"
    suno = base / "suno"
    musicgen = base / "music-gen"
    acestep = base / "ace-step"
    diffrhythm = base / "diffrhythm"
    heartmula = base / "heartmula"
    stable_audio = base / "stable-audio"

    for directory in [suno, musicgen, acestep, diffrhythm, heartmula, stable_audio]:
        directory.mkdir(parents=True, exist_ok=True)

    (suno / "sample.wav").write_bytes(b"RIFFsample")

    settings.db_path = str(tmp_path / "test.sqlite3")
    settings.suno_dir = str(suno)
    settings.musicgen_dir = str(musicgen)
    settings.acestep_dir = str(acestep)
    settings.diffrhythm_dir = str(diffrhythm)
    settings.heartmula_dir = str(heartmula)
    settings.stable_audio_dir = str(stable_audio)

    init_db()


def test_add_track_requires_existing_playlist(tmp_path: Path) -> None:
    _configure_paths(tmp_path)

    client = TestClient(app)
    tracks_res = client.get("/api/library/tracks")
    assert tracks_res.status_code == 200
    track_id = tracks_res.json()["tracks"][0]["id"]

    add_res = client.post("/api/playlists/999/tracks", json={"track_id": track_id})
    assert add_res.status_code == 404
    assert add_res.json()["detail"] == "playlist not found"


def test_add_track_to_playlist_succeeds(tmp_path: Path) -> None:
    _configure_paths(tmp_path)

    client = TestClient(app)
    create_res = client.post("/api/playlists", json={"name": "Focus"})
    assert create_res.status_code == 200
    playlist_id = create_res.json()["id"]

    tracks_res = client.get("/api/library/tracks")
    assert tracks_res.status_code == 200
    track_id = tracks_res.json()["tracks"][0]["id"]

    add_res = client.post(f"/api/playlists/{playlist_id}/tracks", json={"track_id": track_id})
    assert add_res.status_code == 200
    assert add_res.json()["ok"] is True

    detail_res = client.get(f"/api/playlists/{playlist_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["tracks"][0]["id"] == track_id
