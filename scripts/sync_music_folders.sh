#!/usr/bin/env bash
set -euo pipefail

SUNO_SRC_DEFAULT="/host/d/media/projects/suno-wrapper/audio"
SUNO_DST_DEFAULT="/host/d/media/projects/music-platform/audio/suno"
MUSICGEN_SRC_DEFAULT="/host/d/media/projects/music-gen/audio"
MUSICGEN_DST_DEFAULT="/host/d/media/projects/music-platform/audio/music-gen"

SUNO_SRC="${1:-$SUNO_SRC_DEFAULT}"
SUNO_DST="${2:-$SUNO_DST_DEFAULT}"
MUSICGEN_SRC="${3:-$MUSICGEN_SRC_DEFAULT}"
MUSICGEN_DST="${4:-$MUSICGEN_DST_DEFAULT}"

mkdir -p "$SUNO_DST" "$MUSICGEN_DST"

if [ -d "$SUNO_SRC" ]; then
  rsync -a "$SUNO_SRC/" "$SUNO_DST/"
fi
if [ -d "$MUSICGEN_SRC" ]; then
  rsync -a "$MUSICGEN_SRC/" "$MUSICGEN_DST/"
fi

echo "sync complete"
