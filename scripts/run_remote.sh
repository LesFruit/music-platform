#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/music-platform}"
PORT="${PORT:-8090}"

cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 python3-venv python3-pip tmux rsync
fi
if ! command -v tmux >/dev/null 2>&1; then
  apt-get update
  apt-get install -y tmux rsync
fi

VENV_DIR=".venv"
if ! rm -rf "$VENV_DIR" 2>/dev/null; then
  VENV_DIR=".venv-codex"
  rm -rf "$VENV_DIR" || true
fi
python3 -m venv "$VENV_DIR"
. "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -e .

export MUSIC_PLATFORM_SUNO_DIR="${MUSIC_PLATFORM_SUNO_DIR:-$APP_DIR/media/audio/suno}"
export MUSIC_PLATFORM_MUSICGEN_DIR="${MUSIC_PLATFORM_MUSICGEN_DIR:-$APP_DIR/media/audio/music-gen}"
export MUSICGEN_GENERATE_URL="${MUSICGEN_GENERATE_URL:-http://127.0.0.1:8010/generate}"
export SUNO_GENERATE_URL="${SUNO_GENERATE_URL:-http://127.0.0.1:8091/generate}"
mkdir -p "$MUSIC_PLATFORM_SUNO_DIR" "$MUSIC_PLATFORM_MUSICGEN_DIR"

SUNO_SYNC_SRC="${SUNO_SYNC_SRC:-/host/d/media/projects/suno-wrapper/audio}"
MUSICGEN_SYNC_SRC="${MUSICGEN_SYNC_SRC:-/host/d/media/projects/music-gen/audio}"
if [ -d "$SUNO_SYNC_SRC" ]; then
  rsync -a "$SUNO_SYNC_SRC/" "$MUSIC_PLATFORM_SUNO_DIR/"
fi
if [ -d "$MUSICGEN_SYNC_SRC" ]; then
  rsync -a "$MUSICGEN_SYNC_SRC/" "$MUSIC_PLATFORM_MUSICGEN_DIR/"
fi

tmux kill-session -t music-platform 2>/dev/null || true
tmux new-session -d -s music-platform \
  ". $APP_DIR/$VENV_DIR/bin/activate && cd $APP_DIR && MUSIC_PLATFORM_SUNO_DIR='$MUSIC_PLATFORM_SUNO_DIR' MUSIC_PLATFORM_MUSICGEN_DIR='$MUSIC_PLATFORM_MUSICGEN_DIR' MUSICGEN_GENERATE_URL='$MUSICGEN_GENERATE_URL' SUNO_GENERATE_URL='$SUNO_GENERATE_URL' uvicorn app.main:app --host 0.0.0.0 --port $PORT >$APP_DIR/server.log 2>&1"

sleep 2
curl -sf "http://127.0.0.1:$PORT/api/health"
echo "music-platform started on :$PORT"
