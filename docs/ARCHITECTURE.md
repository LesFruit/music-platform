# Architecture

## Components

- Backend: FastAPI (`app/main.py`)
- Frontend: Server-hosted static SPA (`app/templates/index.html`, `app/static/*`)
- Data store: SQLite (`generation_jobs`, `playlists`, `playlist_tracks`)
- Storage: filesystem music folders (Suno + MusicGen)
- Providers:
  - MusicGen HTTP adapter
  - Suno HTTP adapter

## Request Flow

1. UI triggers API request
2. API validates request via Pydantic
3. Generation job row inserted in DB (`queued`)
4. Async worker executes provider call
5. Job transitions: `running` -> `succeeded|failed`
6. UI polls jobs and refreshes library

## Track Identity

Track IDs are deterministic SHA1 hashes of `source + relative_path`.
This avoids DB storage for file inventory and keeps library scanning stateless.

## Deployment Topology (Current)

- `music-platform` app: control machine or API node
- MusicGen generator: GPU node (`gpu-dev-3:8010`)
- Shared drive paths exposed under `/host/d/media/projects/*` (via per-project `./media` symlinks)

## Future Hardening

- Add authentication/authorization
- Add WebSocket job updates (remove polling)
- Add waveform previews and metadata indexing
- Add queue backend (Redis + worker pool)
- Replace filesystem scan with indexed media catalog service
