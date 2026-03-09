from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


Source = Literal["suno", "ace-step", "diffrhythm", "heartmula", "stable-audio"]
Provider = Literal["suno"]


class Track(BaseModel):
    id: str
    source: Source
    name: str
    path: str
    rel_path: str
    size_bytes: int


class CreatePlaylistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PlaylistTrackRequest(BaseModel):
    track_id: str


class GenerateRequest(BaseModel):
    provider: Provider
    prompt: str = Field(min_length=3, max_length=500)
    max_new_tokens: int = Field(default=256, ge=64, le=2048)
    guidance_scale: float = Field(default=3.0, ge=1.0, le=10.0)


class TrackMetadataUpdate(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    bpm: float | None = None
    key: str | None = None
    mood: str | None = None
    energy: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: str | None = None
    description: str | None = None


class GenerationJob(BaseModel):
    id: str
    provider: Provider
    prompt: str
    status: Literal["queued", "running", "succeeded", "failed"]
    detail: str | None = None
    created_at: str
    updated_at: str
