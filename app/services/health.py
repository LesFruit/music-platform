"""Health monitoring service for dependency and catalog quality metrics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from app.config import settings
from app.db import get_conn


@dataclass
class ProviderHealth:
    """Health status for an upstream generation provider."""
    name: str
    url: str
    status: Literal["healthy", "degraded", "unhealthy", "not_configured"]
    response_time_ms: float | None = None
    error: str | None = None


@dataclass
class CatalogQuality:
    """Catalog quality metrics."""
    total_tracks: int
    tracks_with_missing_files: int
    tracks_missing_duration: int
    tracks_with_duration: int


@dataclass
class HealthReport:
    """Complete health report for the music-platform service."""
    overall_status: Literal["healthy", "degraded", "unhealthy"]
    providers: list[ProviderHealth]
    catalog: CatalogQuality
    version: str = "1.0.0"


def _get_health_url(generate_url: str | None) -> str | None:
    """Convert a generate URL to a health check URL.
    
    If the URL ends with /generate, replace it with /health.
    Otherwise, append /health to the base URL.
    """
    if not generate_url:
        return None
    if generate_url.endswith("/generate"):
        return generate_url[:-9] + "/health"
    # For URLs without /generate path, try to check the root or append /health
    return generate_url.rstrip("/") + "/health"


async def check_provider_health(name: str, url: str | None, timeout: float = 5.0) -> ProviderHealth:
    """Check health of an upstream generation provider.
    
    Returns:
        ProviderHealth with status: healthy (200 OK), degraded (slow/non-200),
        unhealthy (connection error), or not_configured (no URL set).
    """
    if not url:
        return ProviderHealth(name=name, url="", status="not_configured")
    
    # Use health endpoint instead of generate endpoint
    health_url = _get_health_url(url)
    if not health_url:
        return ProviderHealth(name=name, url=url, status="not_configured")
    
    start = asyncio.get_event_loop().time()
    
    async def _do_check(client: httpx.AsyncClient) -> ProviderHealth:
        """Perform the actual health check."""
        res = await client.get(health_url, follow_redirects=False)
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        
        if res.status_code == 200:
            return ProviderHealth(
                name=name, 
                url=url, 
                status="healthy",
                response_time_ms=round(elapsed_ms, 2)
            )
        elif res.status_code < 500:
            # 2xx/3xx/4xx means service is up but may have issues
            return ProviderHealth(
                name=name, 
                url=url, 
                status="degraded",
                response_time_ms=round(elapsed_ms, 2),
                error=f"HTTP {res.status_code}"
            )
        else:
            return ProviderHealth(
                name=name, 
                url=url, 
                status="unhealthy",
                response_time_ms=round(elapsed_ms, 2),
                error=f"HTTP {res.status_code}"
            )
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await _do_check(client)
    except httpx.TimeoutException:
        return ProviderHealth(
            name=name, 
            url=url, 
            status="degraded",
            error="Timeout"
        )
    except httpx.ConnectError as e:
        return ProviderHealth(
            name=name, 
            url=url, 
            status="unhealthy",
            error=f"Connection failed: {str(e)[:50]}"
        )
    except Exception as e:
        return ProviderHealth(
            name=name, 
            url=url, 
            status="unhealthy",
            error=str(e)[:50]
        )


def get_catalog_quality() -> CatalogQuality:
    """Analyze catalog for quality issues.
    
    Checks:
    - Tracks with missing files (path doesn't exist on disk)
    - Tracks missing duration metadata
    """
    with get_conn() as conn:
        # Get all tracks
        rows = conn.execute(
            "SELECT id, path, duration_sec FROM tracks"
        ).fetchall()
    
    total = len(rows)
    missing_files = 0
    missing_duration = 0
    with_duration = 0
    
    for row in rows:
        # Check if file exists
        if not Path(row["path"]).exists():
            missing_files += 1
        
        # Check duration
        if row["duration_sec"] is None:
            missing_duration += 1
        else:
            with_duration += 1
    
    return CatalogQuality(
        total_tracks=total,
        tracks_with_missing_files=missing_files,
        tracks_missing_duration=missing_duration,
        tracks_with_duration=with_duration
    )


async def generate_health_report() -> HealthReport:
    """Generate a complete health report."""
    # Check providers in parallel
    provider_checks = [
        check_provider_health("suno", settings.suno_generate_url),
        check_provider_health("musicgen", settings.musicgen_generate_url),
    ]
    providers = await asyncio.gather(*provider_checks)
    
    # Get catalog quality
    catalog = get_catalog_quality()
    
    # Determine overall status
    # unhealthy: any provider unhealthy OR >10% tracks with missing files
    # degraded: any provider degraded OR any tracks with missing files OR >20% missing duration
    # healthy: otherwise
    
    unhealthy_providers = [p for p in providers if p.status == "unhealthy"]
    degraded_providers = [p for p in providers if p.status == "degraded"]
    
    missing_file_ratio = catalog.tracks_with_missing_files / catalog.total_tracks if catalog.total_tracks > 0 else 0
    missing_duration_ratio = catalog.tracks_missing_duration / catalog.total_tracks if catalog.total_tracks > 0 else 0
    
    if unhealthy_providers or missing_file_ratio > 0.1:
        overall = "unhealthy"
    elif degraded_providers or missing_file_ratio > 0 or missing_duration_ratio > 0.2:
        overall = "degraded"
    else:
        overall = "healthy"
    
    return HealthReport(
        overall_status=overall,
        providers=list(providers),
        catalog=catalog
    )


def health_report_to_dict(report: HealthReport) -> dict:
    """Convert HealthReport to a JSON-serializable dict."""
    return {
        "status": report.overall_status,
        "version": report.version,
        "providers": [
            {
                "name": p.name,
                "url": p.url,
                "status": p.status,
                "response_time_ms": p.response_time_ms,
                "error": p.error
            }
            for p in report.providers
        ],
        "catalog": {
            "total_tracks": report.catalog.total_tracks,
            "tracks_with_missing_files": report.catalog.tracks_with_missing_files,
            "tracks_missing_duration": report.catalog.tracks_missing_duration,
            "tracks_with_duration": report.catalog.tracks_with_duration,
            "missing_file_ratio": round(report.catalog.tracks_with_missing_files / report.catalog.total_tracks, 4) 
                if report.catalog.total_tracks > 0 else 0,
            "missing_duration_ratio": round(report.catalog.tracks_missing_duration / report.catalog.total_tracks, 4)
                if report.catalog.total_tracks > 0 else 0
        }
    }
