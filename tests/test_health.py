"""Tests for the health monitoring service."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.health import (
    check_provider_health,
    get_catalog_quality,
    generate_health_report,
    health_report_to_dict,
    ProviderHealth,
    CatalogQuality,
    HealthReport,
)


# Provider health tests

@pytest.mark.asyncio
async def test_check_provider_health_not_configured():
    """Provider with no URL should return not_configured."""
    result = await check_provider_health("test", None)
    assert result.status == "not_configured"
    assert result.url == ""


@pytest.mark.asyncio
async def test_check_provider_health_healthy():
    """Provider returning 200 should be healthy."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await check_provider_health("test", "http://example.com")
        assert result.status == "healthy"
        assert result.response_time_ms is not None


@pytest.mark.asyncio
async def test_check_provider_health_degraded_4xx():
    """Provider returning 4xx should be degraded (service up but issue)."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await check_provider_health("test", "http://example.com")
        assert result.status == "degraded"
        assert "404" in result.error


@pytest.mark.asyncio
async def test_check_provider_health_unhealthy_5xx():
    """Provider returning 5xx should be unhealthy."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        result = await check_provider_health("test", "http://example.com")
        assert result.status == "unhealthy"
        assert "500" in result.error


@pytest.mark.asyncio
async def test_check_provider_health_timeout():
    """Provider timing out should be degraded."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Connection timed out")
        result = await check_provider_health("test", "http://example.com")
        assert result.status == "degraded"
        assert "Timeout" in result.error


@pytest.mark.asyncio
async def test_check_provider_health_connection_error():
    """Provider with connection error should be unhealthy."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await check_provider_health("test", "http://example.com")
        assert result.status == "unhealthy"
        assert "Connection failed" in result.error


# Catalog quality tests

def test_get_catalog_quality_empty():
    """Empty catalog should return zeros."""
    with patch("app.services.health.get_conn") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.return_value.__enter__.return_value.execute.return_value = mock_cursor
        
        result = get_catalog_quality()
        assert result.total_tracks == 0
        assert result.tracks_with_missing_files == 0
        assert result.tracks_missing_duration == 0


def test_get_catalog_quality_with_missing_files():
    """Tracks with non-existent files should be counted."""
    with patch("app.services.health.get_conn") as mock_conn, \
         patch("app.services.health.Path.exists") as mock_exists:
        
        mock_exists.return_value = False  # All files missing
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": "track1", "path": "/fake/path1.mp3", "duration_sec": 120.0},
            {"id": "track2", "path": "/fake/path2.mp3", "duration_sec": None},
        ]
        mock_conn.return_value.__enter__.return_value.execute.return_value = mock_cursor
        
        result = get_catalog_quality()
        assert result.total_tracks == 2
        assert result.tracks_with_missing_files == 2
        assert result.tracks_missing_duration == 1
        assert result.tracks_with_duration == 1


def test_get_catalog_quality_healthy():
    """All tracks present with duration should be healthy."""
    with patch("app.services.health.get_conn") as mock_conn, \
         patch("app.services.health.Path.exists") as mock_exists:
        
        mock_exists.return_value = True  # All files exist
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": "track1", "path": "/real/path1.mp3", "duration_sec": 120.0},
            {"id": "track2", "path": "/real/path2.mp3", "duration_sec": 180.0},
        ]
        mock_conn.return_value.__enter__.return_value.execute.return_value = mock_cursor
        
        result = get_catalog_quality()
        assert result.total_tracks == 2
        assert result.tracks_with_missing_files == 0
        assert result.tracks_missing_duration == 0
        assert result.tracks_with_duration == 2


# Health report tests

@pytest.mark.asyncio
async def test_generate_health_report_healthy():
    """All healthy providers and catalog should give healthy overall."""
    with patch("app.services.health.check_provider_health") as mock_check, \
         patch("app.services.health.get_catalog_quality") as mock_catalog:
        
        mock_check.return_value = ProviderHealth(
            name="test", url="http://test", status="healthy", response_time_ms=100
        )
        mock_catalog.return_value = CatalogQuality(
            total_tracks=100,
            tracks_with_missing_files=0,
            tracks_missing_duration=10,
            tracks_with_duration=90
        )
        
        report = await generate_health_report()
        assert report.overall_status == "healthy"


@pytest.mark.asyncio
async def test_generate_health_report_unhealthy_provider():
    """Unhealthy provider should make overall unhealthy."""
    with patch("app.services.health.check_provider_health") as mock_check, \
         patch("app.services.health.get_catalog_quality") as mock_catalog:
        
        mock_check.return_value = ProviderHealth(
            name="test", url="http://test", status="unhealthy", error="Connection refused"
        )
        mock_catalog.return_value = CatalogQuality(
            total_tracks=100,
            tracks_with_missing_files=0,
            tracks_missing_duration=0,
            tracks_with_duration=100
        )
        
        report = await generate_health_report()
        assert report.overall_status == "unhealthy"


@pytest.mark.asyncio
async def test_generate_health_report_degraded_missing_files():
    """Missing files should make overall degraded."""
    with patch("app.services.health.check_provider_health") as mock_check, \
         patch("app.services.health.get_catalog_quality") as mock_catalog:
        
        mock_check.return_value = ProviderHealth(
            name="test", url="http://test", status="healthy", response_time_ms=100
        )
        mock_catalog.return_value = CatalogQuality(
            total_tracks=100,
            tracks_with_missing_files=5,  # 5% missing
            tracks_missing_duration=0,
            tracks_with_duration=100
        )
        
        report = await generate_health_report()
        assert report.overall_status == "degraded"


@pytest.mark.asyncio
async def test_generate_health_report_unhealthy_many_missing_files():
    """>10% missing files should make overall unhealthy."""
    with patch("app.services.health.check_provider_health") as mock_check, \
         patch("app.services.health.get_catalog_quality") as mock_catalog:
        
        mock_check.return_value = ProviderHealth(
            name="test", url="http://test", status="healthy", response_time_ms=100
        )
        mock_catalog.return_value = CatalogQuality(
            total_tracks=100,
            tracks_with_missing_files=15,  # 15% missing
            tracks_missing_duration=0,
            tracks_with_duration=85
        )
        
        report = await generate_health_report()
        assert report.overall_status == "unhealthy"


@pytest.mark.asyncio
async def test_generate_health_report_degraded_missing_duration():
    """>20% missing duration should make overall degraded."""
    with patch("app.services.health.check_provider_health") as mock_check, \
         patch("app.services.health.get_catalog_quality") as mock_catalog:
        
        mock_check.return_value = ProviderHealth(
            name="test", url="http://test", status="healthy", response_time_ms=100
        )
        mock_catalog.return_value = CatalogQuality(
            total_tracks=100,
            tracks_with_missing_files=0,
            tracks_missing_duration=25,  # 25% missing duration
            tracks_with_duration=75
        )
        
        report = await generate_health_report()
        assert report.overall_status == "degraded"


def test_health_report_to_dict():
    """Health report should convert to dict correctly."""
    report = HealthReport(
        overall_status="healthy",
        providers=[
            ProviderHealth(name="suno", url="http://suno", status="healthy", response_time_ms=100),
            ProviderHealth(name="musicgen", url="http://musicgen", status="not_configured"),
        ],
        catalog=CatalogQuality(
            total_tracks=100,
            tracks_with_missing_files=5,
            tracks_missing_duration=10,
            tracks_with_duration=90
        )
    )
    
    data = health_report_to_dict(report)
    
    assert data["status"] == "healthy"
    assert len(data["providers"]) == 2
    assert data["catalog"]["total_tracks"] == 100
    assert data["catalog"]["missing_file_ratio"] == 0.05
    assert data["catalog"]["missing_duration_ratio"] == 0.1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
