from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Literal
import httpx

from app.config import settings
from app.db import get_conn
from app.models import GenerateRequest


ProviderStatus = Literal["available", "unavailable", "not_configured"]


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
        return False, "Health check timed out - service may be overloaded"
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


async def check_provider_availability(provider: str) -> tuple[ProviderStatus, str | None]:
    """Check if a generation provider is available.
    
    Returns:
        Tuple of (status, error_message)
        - status: "available", "unavailable", or "not_configured"
        - error_message: Description of the issue if unavailable
    """
    if provider == "suno":
        url = settings.suno_generate_url
    elif provider == "musicgen":
        url = settings.musicgen_generate_url
    else:
        return "unavailable", f"Unknown provider: {provider}"
    
    if not url:
        return "not_configured", f"{provider.upper()}_GENERATE_URL not configured"
    
    is_healthy, error_msg = await _check_service_health(url)
    if is_healthy:
        return "available", None
    return "unavailable", error_msg


async def get_available_providers() -> list[dict]:
    """Get list of available providers with their status."""
    providers = []
    for name in ["suno", "musicgen"]:
        status, error = await check_provider_availability(name)
        providers.append({
            "name": name,
            "status": status,
            "error": error,
            "available": status == "available"
        })
    return providers


async def auto_fallback_generation(req: GenerateRequest) -> dict:
    """Attempt generation with automatic fallback between providers.
    
    Logic:
    1. Check if requested provider is available
    2. If available, use it
    3. If unavailable, try the other provider if available
    4. If neither available, return error
    
    Returns:
        dict with job_id, status, and fallback info
    """
    # Check requested provider availability
    requested_status, requested_error = await check_provider_availability(req.provider)
    
    if requested_status == "available":
        # Requested provider is available, use it
        job_id = create_job(req)
        launch_job(job_id, req)
        return {
            "job_id": job_id,
            "status": "queued",
            "provider": req.provider,
            "fallback": False,
        }
    
    # Requested provider not available, try fallback
    fallback_provider = "musicgen" if req.provider == "suno" else "suno"
    fallback_status, fallback_error = await check_provider_availability(fallback_provider)
    
    if fallback_status == "available":
        # Use fallback provider
        fallback_req = GenerateRequest(
            provider=fallback_provider,
            prompt=req.prompt,
            max_new_tokens=req.max_new_tokens,
            guidance_scale=req.guidance_scale,
        )
        job_id = create_job(fallback_req)
        launch_job(job_id, fallback_req)
        return {
            "job_id": job_id,
            "status": "queued",
            "provider": fallback_provider,
            "fallback": True,
            "original_provider": req.provider,
            "original_error": requested_error,
        }
    
    # Neither provider available
    return {
        "job_id": None,
        "status": "failed",
        "error": f"Requested provider '{req.provider}' unavailable: {requested_error}. "
                 f"Fallback provider '{fallback_provider}' also unavailable: {fallback_error}",
    }
