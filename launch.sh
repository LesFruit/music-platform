#!/usr/bin/env bash
set -euo pipefail

# Music Platform - Apple Music-like library and player for AI-generated music
# Usage:
#   ./launch.sh api           - Start FastAPI server (port 8090)
#   ./launch.sh dev           - Start API with auto-reload
#   ./launch.sh test          - Run test suite
#   ./launch.sh tmux          - Start API in tmux session
#   ./launch.sh container     - Build and run container
#   ./launch.sh ingest        - Ingest music-gen outputs into catalog
#   ./launch.sh reindex       - Reindex the music library

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables
for env in "$SCRIPT_DIR/.env" ~/.env; do
    if [ -f "$env" ]; then
        set -a
        source "$env"
        set +a
        break
    fi
done

# Activate virtual environment if it exists
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

case "${1:-api}" in
    api)
        echo "Starting Music Platform API server on port 8090..."
        uvicorn app.main:app --host 0.0.0.0 --port 8090
        ;;

    dev)
        echo "Starting Music Platform API server in development mode..."
        uvicorn app.main:app --host 0.0.0.0 --port 8090 --reload
        ;;

    test)
        echo "Running test suite..."
        pytest tests/ -v
        ;;

    tmux)
        echo "Starting Music Platform API in tmux session..."
        tmux new-session -d -s music-platform "cd $SCRIPT_DIR && ./launch.sh api"
        echo "Started tmux session 'music-platform'"
        echo "Attach: tmux attach -t music-platform"
        echo "API available at: http://localhost:8090"
        ;;

    container)
        echo "Building and running Music Platform container..."
        podman build -t music-platform:latest -f Containerfile .
        podman run -d --name music-platform -p 8090:8090 \
            -v music-platform-data:/app/data \
            -v music-platform-media:/app/media \
            --env-file .env \
            music-platform:latest
        echo "Container running on port 8090"
        ;;

    container-compose)
        echo "Starting Music Platform with docker-compose..."
        docker-compose up -d --build
        echo "Services starting..."
        echo "API available at: http://localhost:8090"
        ;;

    ingest)
        echo "Ingesting music-gen outputs into catalog..."
        python3 scripts/ingest.py "$@"
        ;;

    reindex)
        echo "Reindexing music library..."
        curl -s -X POST "http://localhost:8090/api/library/reindex" | python3 -m json.tool
        ;;

    health)
        echo "Checking API health..."
        curl -s http://localhost:8090/api/health | python3 -m json.tool
        ;;

    status)
        echo "Opening status dashboard..."
        curl -s http://localhost:8090/status | head -20
        echo "..."
        echo "Full status page: http://localhost:8090/status"
        ;;

    stop)
        echo "Stopping Music Platform..."
        tmux kill-session -t music-platform 2>/dev/null || echo "No tmux session found"
        podman stop music-platform 2>/dev/null || true
        podman rm music-platform 2>/dev/null || true
        docker-compose down 2>/dev/null || true
        ;;

    help|*)
        echo "Music Platform - Apple Music-like library and player for AI-generated music"
        echo ""
        echo "Usage: ./launch.sh <command>"
        echo ""
        echo "Commands:"
        echo "  api              Start FastAPI server (port 8090)"
        echo "  dev              Start API with auto-reload"
        echo "  test             Run test suite"
        echo "  tmux             Start API in tmux session 'music-platform'"
        echo "  container        Build and run container with podman"
        echo "  container-compose Start with docker-compose"
        echo "  ingest           Ingest music-gen outputs into catalog"
        echo "  reindex          Reindex the music library"
        echo "  health           Check API health endpoint"
        echo "  status           Show status dashboard"
        echo "  stop             Stop tmux session and containers"
        echo ""
        echo "Environment variables:"
        echo "  MUSIC_PLATFORM_PORT         - Server port (default: 8090)"
        echo "  MUSIC_PLATFORM_DB_PATH      - Database file path"
        echo "  MUSIC_PLATFORM_SUNO_DIR     - Suno audio directory"
        echo "  SUNO_GENERATE_URL           - Suno generation service URL"
        echo "  MUSICGEN_GENERATE_URL       - MusicGen generation service URL"
        ;;
esac
