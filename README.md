# music-platform

Production-style music web app with:
- Apple-Music-like library/player UX
- Unified library for `Music/suno` + `Music/music-gen`
- Song generation jobs for `musicgen` and `suno`
- Playlist management
- API-first backend (FastAPI + SQLite)

## Repository

This project is intentionally in its own repo:
- `/home/codex/.codex/projects/music-platform`

## Default Folder Layout

The app is designed to read/write Windows D drive media storage via the project symlink:
- `./media` -> `/host/d/media/projects/music-platform`
- Suno library: `./media/audio/suno`
- MusicGen library: `./media/audio/music-gen`

Override with env vars:
- `MUSIC_PLATFORM_SUNO_DIR`
- `MUSIC_PLATFORM_MUSICGEN_DIR`

## Quick Start

```bash
cd /home/codex/.codex/projects/music-platform
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

export MUSICGEN_GENERATE_URL="http://gpu-dev-3:8010/generate"
export SUNO_GENERATE_URL="http://127.0.0.1:8091/generate"

uvicorn app.main:app --host 0.0.0.0 --port 8090
```

Open:
- UI: `http://<host>:8090/`
- API docs: `http://<host>:8090/docs`

## Remote Deploy (gpu-dev-3)

```bash
cd /home/codex/.codex/projects/music-platform
rsync -az --delete ./ root@gpu-dev-3:/srv/music-platform/
tailscale ssh root@gpu-dev-3 'bash /srv/music-platform/scripts/run_remote.sh'
```

Then open:
- `http://gpu-dev-3:8090/`

### Player + Library Endpoints

- UI: `GET /`
- Tracks: `GET /api/library/tracks`
- Stream track: `GET /api/audio/{track_id}`
- Jobs: `GET /api/jobs`

## Generation Integrations

### MusicGen
Set:
- `MUSICGEN_GENERATE_URL` (example: `http://gpu-dev-3:8010/generate`)

Expected API contract:
- POST JSON: `{ "prompt", "max_new_tokens", "guidance_scale" }`
- Returns JSON (stored in job detail)

### Suno
Set:
- `SUNO_GENERATE_URL` to your Suno wrapper endpoint (default runtime target: `http://127.0.0.1:8091/generate`)

If Suno wrapper auth is stale, Suno jobs fail with 401 in Jobs view until auth is refreshed.

## Production Notes

- Run with process manager (`systemd`, `supervisord`, or container orchestrator).
- Put behind reverse proxy (`nginx`/`traefik`) with TLS.
- Add auth (OIDC/session middleware) before internet exposure.
- Move from SQLite to Postgres for multi-instance writes.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/OPERATIONS.md`
- `docs/API.md`
