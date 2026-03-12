from __future__ import annotations

from pydantic import BaseModel
import os


class Settings(BaseModel):
    app_name: str = os.getenv("MUSIC_PLATFORM_APP_NAME", "Music Platform")
    host: str = os.getenv("MUSIC_PLATFORM_HOST", "0.0.0.0")
    port: int = int(os.getenv("MUSIC_PLATFORM_PORT", "8090"))

    db_path: str = os.getenv("MUSIC_PLATFORM_DB_PATH", "./data/music_platform.sqlite3")

    suno_dir: str = os.getenv("MUSIC_PLATFORM_SUNO_DIR", "/host/d/Music/suno")
    acestep_dir: str = os.getenv("MUSIC_PLATFORM_ACESTEP_DIR", "/host/d/Music/ace-step")
    diffrhythm_dir: str = os.getenv("MUSIC_PLATFORM_DIFFRHYTHM_DIR", "/host/d/Music/diffrhythm")
    heartmula_dir: str = os.getenv("MUSIC_PLATFORM_HEARTMULA_DIR", "/host/d/Music/heartmula")
    stable_audio_dir: str = os.getenv("MUSIC_PLATFORM_STABLE_AUDIO_DIR", "/host/d/Music/stable-audio")
    
    # Cover outputs from music-gen pipeline
    covers_dir: str = os.getenv("MUSIC_PLATFORM_COVERS_DIR", "/host/d/Music/covers")
    cover_piano_dir: str = os.getenv("MUSIC_PLATFORM_COVER_PIANO_DIR", "/host/d/Music/covers/cover_piano")
    cover_orchestra_dir: str = os.getenv("MUSIC_PLATFORM_COVER_ORCHESTRA_DIR", "/host/d/Music/covers/cover_orchestra")
    
    # Music-gen output directory for ingest
    musicgen_output_dir: str = os.getenv("MUSICGEN_OUTPUT_DIR", "../music-gen/data/out")

    suno_generate_url: str = os.getenv("SUNO_GENERATE_URL", "http://127.0.0.1:8091/generate")
    musicgen_generate_url: str = os.getenv("MUSICGEN_GENERATE_URL", "http://100.73.6.116:8010/generate")


settings = Settings()
