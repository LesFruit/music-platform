from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
import httpx

from app.config import settings
from app.db import get_conn
from app.models import GenerateRequest


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(req: GenerateRequest) -> str:
    job_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO generation_jobs (id, provider, prompt, status, detail, created_at, updated_at) VALUES (?, ?, ?, 'queued', NULL, ?, ?)",
            (job_id, req.provider, req.prompt, now_iso(), now_iso()),
        )
        conn.commit()
    return job_id


def update_job(job_id: str, status: str, detail: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE generation_jobs SET status = ?, detail = ?, updated_at = ? WHERE id = ?",
            (status, detail, now_iso(), job_id),
        )
        conn.commit()


async def _check_service_health(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Check if a generation service is reachable.
    
    Returns (is_healthy, error_message)
    """
    if not url:
        return False, "Service URL not configured"
    
    # Extract base URL for health check (remove /generate path if present)
    base_url = url.rsplit("/", 1)[0] if "/generate" in url else url
    health_url = f"{base_url}/health" if not base_url.endswith("/health") else base_url
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(health_url)
            if res.status_code == 200:
                return True, ""
            return False, f"Health check failed with status {res.status_code}"
    except httpx.ConnectError:
        return False, f"Service not reachable at {url} - ensure the service is running"
    except httpx.TimeoutException:
        return False, f"Health check timed out - service may be overloaded"
    except Exception as e:
        return False, f"Health check error: {type(e).__name__}: {e}"


async def _run_suno(req: GenerateRequest) -> str:
    if not settings.suno_generate_url:
        raise RuntimeError("SUNO_GENERATE_URL is not configured")
    
    # Check service health before attempting generation
    is_healthy, error_msg = await _check_service_health(settings.suno_generate_url)
    if not is_healthy:
        raise RuntimeError(f"Suno service unavailable: {error_msg}")
    
    payload = {
        "prompt": req.prompt,
        "max_new_tokens": req.max_new_tokens,
        "guidance_scale": req.guidance_scale,
    }
    async with httpx.AsyncClient(timeout=1800) as client:
        res = await client.post(settings.suno_generate_url, json=payload)
        res.raise_for_status()
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
    return f"suno: {data}"


async def _run_musicgen(req: GenerateRequest) -> str:
    if not settings.musicgen_generate_url:
        raise RuntimeError("MUSICGEN_GENERATE_URL is not configured")
    
    # Check service health before attempting generation
    is_healthy, error_msg = await _check_service_health(settings.musicgen_generate_url)
    if not is_healthy:
        raise RuntimeError(f"MusicGen service unavailable: {error_msg}")
    
    payload = {
        "prompt": req.prompt,
        "max_new_tokens": req.max_new_tokens,
        "guidance_scale": req.guidance_scale,
    }
    async with httpx.AsyncClient(timeout=1800) as client:
        res = await client.post(settings.musicgen_generate_url, json=payload)
        res.raise_for_status()
        data = res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
    return f"musicgen: {data}"


async def run_job(job_id: str, req: GenerateRequest) -> None:
    update_job(job_id, "running")
    try:
        if req.provider == "suno":
            detail = await _run_suno(req)
        elif req.provider == "musicgen":
            detail = await _run_musicgen(req)
        else:
            raise RuntimeError(f"Unknown provider: {req.provider}")
        update_job(job_id, "succeeded", detail)
    except Exception as exc:
        update_job(job_id, "failed", str(exc))


def launch_job(job_id: str, req: GenerateRequest) -> None:
    asyncio.create_task(run_job(job_id, req))
