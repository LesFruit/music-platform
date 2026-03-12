from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from app.config import settings
from app.db import get_conn, init_db
from app.models import CreatePlaylistRequest, GenerateRequest, PlaylistTrackRequest, TrackMetadataUpdate
from app.services.generation import create_job, launch_job, _check_service_health
from app.services.health import generate_health_report, health_report_to_dict
from app.services.indexer import reindex
from app.services.ingest import scan_and_ingest
from app.services.library import load_library, track_by_id

app = FastAPI(title=settings.app_name, version="1.0.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


ALL_SOURCES = {"suno", "ace-step", "diffrhythm", "heartmula", "stable-audio", "cover-piano", "cover-orchestra"}


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    for d in [settings.suno_dir, settings.acestep_dir,
              settings.diffrhythm_dir, settings.heartmula_dir, settings.stable_audio_dir,
              settings.cover_piano_dir, settings.cover_orchestra_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)
    reindex()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "app_name": settings.app_name})


@app.get("/status", response_class=HTMLResponse)
def status_page(request: Request):
    """Operator-facing status dashboard for health and catalog metrics."""
    return templates.TemplateResponse("status.html", {"request": request, "app_name": settings.app_name})


@app.get("/api/health")
async def health() -> dict:
    """Health endpoint with dependency and catalog quality metrics.
    
    Returns comprehensive health status including:
    - Upstream generation provider reachability (suno, musicgen)
    - Catalog quality metrics (missing files, missing duration)
    - Overall service health status (healthy/degraded/unhealthy)
    
    Status thresholds:
    - unhealthy: Any provider unreachable OR >10% tracks with missing files
    - degraded: Any provider slow/non-200 OR any tracks missing files OR >20% missing duration
    - healthy: All providers healthy and catalog quality acceptable
    """
    report = await generate_health_report()
    return health_report_to_dict(report)


@app.get("/api/library/tracks")
def tracks(query: str = "", source: str = "") -> dict:
    src = source if source in ALL_SOURCES else ""
    items = load_library(query=query, source=src)
    return {"count": len(items), "tracks": [t.model_dump() for t in items]}


@app.get("/api/library/stats")
def stats() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT source, COUNT(*) as cnt, SUM(size_bytes) as sz FROM tracks GROUP BY source"
        ).fetchall()
    by_source = {r["source"]: r["cnt"] for r in rows}
    total = sum(r["cnt"] for r in rows)
    size = sum(r["sz"] for r in rows)
    return {"count": total, "size_bytes": size, "by_source": by_source}


@app.post("/api/library/reindex")
def do_reindex(with_duration: bool = False) -> dict:
    return reindex(with_duration=with_duration)


@app.get("/api/audio/{track_id}")
def audio(track_id: str):
    t = track_by_id(track_id)
    if not t:
        raise HTTPException(status_code=404, detail="track not found")
    path = Path(t.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="file missing")
    return FileResponse(path, filename=t.name)


@app.get("/api/playlists")
def playlists() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, created_at FROM playlists ORDER BY name").fetchall()
    return {"playlists": [dict(r) for r in rows]}


@app.post("/api/playlists")
def create_playlist(req: CreatePlaylistRequest) -> dict:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO playlists (name) VALUES (?)", (req.name,))
        conn.commit()
        pid = cur.lastrowid
    return {"id": pid, "name": req.name}


@app.get("/api/playlists/{playlist_id}")
def playlist_detail(playlist_id: int) -> dict:
    with get_conn() as conn:
        p = conn.execute("SELECT id, name, created_at FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if not p:
            raise HTTPException(status_code=404, detail="playlist not found")
        rows = conn.execute(
            "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY created_at",
            (playlist_id,),
        ).fetchall()
    tracks = []
    for r in rows:
        t = track_by_id(r["track_id"])
        if t:
            tracks.append(t.model_dump())
    return {"playlist": dict(p), "tracks": tracks}


@app.post("/api/playlists/{playlist_id}/tracks")
def playlist_add_track(playlist_id: int, req: PlaylistTrackRequest) -> dict:
    if not track_by_id(req.track_id):
        raise HTTPException(status_code=404, detail="track not found")
    with get_conn() as conn:
        playlist = conn.execute(
            "SELECT id FROM playlists WHERE id = ?",
            (playlist_id,),
        ).fetchone()
        if not playlist:
            raise HTTPException(status_code=404, detail="playlist not found")
        conn.execute(
            "INSERT OR IGNORE INTO playlist_tracks (playlist_id, track_id) VALUES (?, ?)",
            (playlist_id, req.track_id),
        )
        conn.commit()
    return {"ok": True}


@app.delete("/api/playlists/{playlist_id}/tracks/{track_id}")
def playlist_remove_track(playlist_id: int, track_id: str) -> dict:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        conn.commit()
    return {"ok": True}


@app.get("/api/tracks/{track_id}/metadata")
def get_metadata(track_id: str) -> dict:
    if not track_by_id(track_id):
        raise HTTPException(status_code=404, detail="track not found")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM track_metadata WHERE track_id = ?", (track_id,)).fetchone()
    return dict(row) if row else {"track_id": track_id}


@app.put("/api/tracks/{track_id}/metadata")
def set_metadata(track_id: str, req: TrackMetadataUpdate) -> dict:
    if not track_by_id(track_id):
        raise HTTPException(status_code=404, detail="track not found")
    data = req.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    with get_conn() as conn:
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        updates = ", ".join(f"{k}=excluded.{k}" for k in data)
        conn.execute(
            f"INSERT INTO track_metadata (track_id, {cols}) VALUES (?, {placeholders}) "
            f"ON CONFLICT(track_id) DO UPDATE SET {updates}, updated_at=datetime('now')",
            [track_id, *data.values()],
        )
        conn.commit()
    return {"ok": True, "track_id": track_id}


@app.post("/api/generate")
async def generate(req: GenerateRequest) -> dict:
    job_id = create_job(req)
    launch_job(job_id, req)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs")
def jobs() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, provider, prompt, status, detail, created_at, updated_at FROM generation_jobs ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    return {"jobs": [dict(r) for r in rows]}


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, provider, prompt, status, detail, created_at, updated_at FROM generation_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return dict(row)


@app.post("/api/ingest")
def ingest(output_dir: str = "", dry_run: bool = False) -> dict:
    """Ingest music-gen outputs into the catalog.
    
    Args:
        output_dir: Path to music-gen output directory (defaults to settings.musicgen_output_dir)
        dry_run: If True, only report what would be done
    """
    import os
    target_dir = output_dir or settings.musicgen_output_dir
    
    # Resolve relative paths from project root
    if not os.path.isabs(target_dir):
        target_dir = str(Path(__file__).parent.parent / target_dir)
    
    stats = scan_and_ingest(target_dir, dry_run=dry_run)
    return {"ok": stats["failed"] == 0, "dry_run": dry_run, "stats": stats}
