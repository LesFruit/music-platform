# Operations Runbook

## Environment Variables

- `MUSIC_PLATFORM_HOST` (default `0.0.0.0`)
- `MUSIC_PLATFORM_PORT` (default `8090`)
- `MUSIC_PLATFORM_DB_PATH` (default `./data/music_platform.sqlite3`)
- `MUSIC_PLATFORM_SUNO_DIR` (default `./media/audio/suno`)
- `MUSIC_PLATFORM_MUSICGEN_DIR` (default `./media/audio/music-gen`)
- `MUSICGEN_GENERATE_URL` (default `http://gpu-dev-3:8010/generate`)
- `SUNO_GENERATE_URL` (default `http://127.0.0.1:8091/generate`)

## Start Service

```bash
cd /home/codex/.codex/projects/music-platform
. .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8090
```

## Health Checks

- API health: `GET /api/health`
- Library stats: `GET /api/library/stats`
- MusicGen upstream: verify from app host: `curl $MUSICGEN_GENERATE_URL`

## Common Issues

### Suno jobs fail immediately
- Cause: Suno wrapper endpoint unavailable or unauthenticated (401 from Suno upstream).
- Fix:
  - Ensure Suno API adapter is running on the same host:
    - `cd ~/services/suno-wrapper`
    - `tmux new-session -d -s suno-api 'bash -lc "set -a; [ -f ~/.env.suno.runtime ] && source ~/.env.suno.runtime; set +a; source .venv/bin/activate; export SUNO_OUTPUT_DIR=/host/d/media/projects/suno-wrapper/audio/suno; uvicorn scripts.suno_api_server:app --host 0.0.0.0 --port 8091"'`
  - Verify adapter health:
    - `curl http://127.0.0.1:8091/health`
  - If health returns auth 401, refresh/login in `suno-wrapper` and retry.

## Suno Wrapper Auth Recovery (gpu-dev-3)

Run audit:

```bash
cd ~/services/suno-wrapper
source .venv/bin/activate
python scripts/audit_setup.py
```

Expected healthy state:
- `auth_check.ok=true`
- `jwt_refresh.ok=true` (or current JWT still valid)

If stale session (`401`) persists:
1. Complete Suno login in browser (SMS OTP).
2. Update runtime env with fresh `SUNO_COOKIE` + `SUNO_AUTH_TOKEN`.
3. Restart `suno-api` tmux session.
4. Re-run `python scripts/check_auth.py` and `curl http://127.0.0.1:8091/health`.

### Library empty
- Cause: wrong path mounts.
- Fix: verify `MUSIC_PLATFORM_SUNO_DIR` and `MUSIC_PLATFORM_MUSICGEN_DIR` exist and contain audio files.

### MusicGen jobs fail
- Cause: upstream service unavailable.
- Fix: ensure GPU service is running and returns valid JSON.

## Backup

- Backup DB: copy `data/music_platform.sqlite3`
- Audio is canonical in D drive folders.
