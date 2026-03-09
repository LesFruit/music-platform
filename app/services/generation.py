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


async def _run_suno(req: GenerateRequest) -> str:
    if not settings.suno_generate_url:
        raise RuntimeError("SUNO_GENERATE_URL is not configured")
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


async def run_job(job_id: str, req: GenerateRequest) -> None:
    update_job(job_id, "running")
    try:
        detail = await _run_suno(req)
        update_job(job_id, "succeeded", detail)
    except Exception as exc:
        update_job(job_id, "failed", str(exc))


def launch_job(job_id: str, req: GenerateRequest) -> None:
    asyncio.create_task(run_job(job_id, req))
