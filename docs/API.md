# API

## Library

- `GET /api/library/tracks?query=&source=`
- `GET /api/library/stats`
- `GET /api/audio/{track_id}`

## Playlists

- `GET /api/playlists`
- `POST /api/playlists` body: `{ "name": "..." }`
- `GET /api/playlists/{playlist_id}`
- `POST /api/playlists/{playlist_id}/tracks` body: `{ "track_id": "..." }`
- `DELETE /api/playlists/{playlist_id}/tracks/{track_id}`

## Generation

- `POST /api/generate`
  - body: `{ "provider": "musicgen|suno", "prompt": "...", "max_new_tokens": 256, "guidance_scale": 3.0 }`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`

## Health

- `GET /api/health`
