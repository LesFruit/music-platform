"""Tests for the generation service with graceful degradation."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.generation import (
    check_provider_availability,
    get_available_providers,
    auto_fallback_generation,
)
from app.models import GenerateRequest


# Provider availability tests

@pytest.mark.asyncio
async def test_check_provider_availability_suno_available():
    """Suno should be available when health check passes."""
    with patch("app.services.generation._check_service_health") as mock_health:
        mock_health.return_value = (True, "")
        
        status, error = await check_provider_availability("suno")
        assert status == "available"
        assert error is None


@pytest.mark.asyncio
async def test_check_provider_availability_suno_unavailable():
    """Suno should be unavailable when health check fails."""
    with patch("app.services.generation._check_service_health") as mock_health:
        mock_health.return_value = (False, "Connection refused")
        
        status, error = await check_provider_availability("suno")
        assert status == "unavailable"
        assert "Connection refused" in error


@pytest.mark.asyncio
async def test_check_provider_availability_not_configured():
    """Provider should be not_configured when URL is empty."""
    with patch("app.services.generation.settings") as mock_settings:
        mock_settings.suno_generate_url = ""
        
        status, error = await check_provider_availability("suno")
        assert status == "not_configured"
        assert "not configured" in error.lower()


@pytest.mark.asyncio
async def test_check_provider_availability_unknown_provider():
    """Unknown provider should return unavailable."""
    status, error = await check_provider_availability("unknown")
    assert status == "unavailable"
    assert "Unknown provider" in error


# Available providers list tests

@pytest.mark.asyncio
async def test_get_available_providers_all_healthy():
    """All providers should be listed when healthy."""
    with patch("app.services.generation.check_provider_availability") as mock_check:
        mock_check.return_value = ("available", None)
        
        providers = await get_available_providers()
        
        assert len(providers) == 2
        assert all(p["available"] for p in providers)
        assert providers[0]["name"] == "suno"
        assert providers[1]["name"] == "musicgen"


@pytest.mark.asyncio
async def test_get_available_providers_mixed():
    """Mixed availability should be reflected correctly."""
    with patch("app.services.generation.check_provider_availability") as mock_check:
        # First call (suno) - unavailable, second call (musicgen) - available
        mock_check.side_effect = [
            ("unavailable", "Connection refused"),
            ("available", None),
        ]
        
        providers = await get_available_providers()
        
        assert len(providers) == 2
        assert providers[0]["name"] == "suno"
        assert not providers[0]["available"]
        assert providers[0]["error"] == "Connection refused"
        assert providers[1]["name"] == "musicgen"
        assert providers[1]["available"]


# Auto fallback generation tests

@pytest.mark.asyncio
async def test_auto_fallback_uses_requested_provider_when_available():
    """Should use requested provider when available."""
    with patch("app.services.generation.check_provider_availability") as mock_check, \
         patch("app.services.generation.create_job") as mock_create, \
         patch("app.services.generation.launch_job") as mock_launch:
        
        mock_check.return_value = ("available", None)
        mock_create.return_value = "job-123"
        
        req = GenerateRequest(
            provider="suno",
            prompt="test prompt",
            max_new_tokens=256,
            guidance_scale=3.0,
        )
        
        result = await auto_fallback_generation(req)
        
        assert result["job_id"] == "job-123"
        assert result["status"] == "queued"
        assert result["provider"] == "suno"
        assert result["fallback"] is False
        mock_create.assert_called_once()
        mock_launch.assert_called_once()


@pytest.mark.asyncio
async def test_auto_fallback_to_musicgen_when_suno_unavailable():
    """Should fallback to musicgen when suno is unavailable."""
    with patch("app.services.generation.check_provider_availability") as mock_check, \
         patch("app.services.generation.create_job") as mock_create, \
         patch("app.services.generation.launch_job") as mock_launch:
        
        # Suno unavailable, musicgen available
        mock_check.side_effect = [
            ("unavailable", "Suno auth expired"),
            ("available", None),
        ]
        mock_create.return_value = "job-456"
        
        req = GenerateRequest(
            provider="suno",
            prompt="test prompt",
            max_new_tokens=256,
            guidance_scale=3.0,
        )
        
        result = await auto_fallback_generation(req)
        
        assert result["job_id"] == "job-456"
        assert result["status"] == "queued"
        assert result["provider"] == "musicgen"
        assert result["fallback"] is True
        assert result["original_provider"] == "suno"
        assert "Suno auth expired" in result["original_error"]


@pytest.mark.asyncio
async def test_auto_fallback_to_suno_when_musicgen_unavailable():
    """Should fallback to suno when musicgen is unavailable."""
    with patch("app.services.generation.check_provider_availability") as mock_check, \
         patch("app.services.generation.create_job") as mock_create, \
         patch("app.services.generation.launch_job") as mock_launch:
        
        # Musicgen unavailable, suno available
        mock_check.side_effect = [
            ("unavailable", "GPU server down"),
            ("available", None),
        ]
        mock_create.return_value = "job-789"
        
        req = GenerateRequest(
            provider="musicgen",
            prompt="test prompt",
            max_new_tokens=256,
            guidance_scale=3.0,
        )
        
        result = await auto_fallback_generation(req)
        
        assert result["job_id"] == "job-789"
        assert result["status"] == "queued"
        assert result["provider"] == "suno"
        assert result["fallback"] is True
        assert result["original_provider"] == "musicgen"


@pytest.mark.asyncio
async def test_auto_fallback_fails_when_both_unavailable():
    """Should return error when both providers are unavailable."""
    with patch("app.services.generation.check_provider_availability") as mock_check:
        # Both unavailable
        mock_check.side_effect = [
            ("unavailable", "Suno auth expired"),
            ("unavailable", "GPU server down"),
        ]
        
        req = GenerateRequest(
            provider="suno",
            prompt="test prompt",
            max_new_tokens=256,
            guidance_scale=3.0,
        )
        
        result = await auto_fallback_generation(req)
        
        assert result["job_id"] is None
        assert result["status"] == "failed"
        assert "Suno auth expired" in result["error"]
        assert "GPU server down" in result["error"]


@pytest.mark.asyncio
async def test_auto_fallback_fails_when_both_not_configured():
    """Should return error when both providers are not configured."""
    with patch("app.services.generation.check_provider_availability") as mock_check:
        # Both not configured
        mock_check.side_effect = [
            ("not_configured", "SUNO_GENERATE_URL not configured"),
            ("not_configured", "MUSICGEN_GENERATE_URL not configured"),
        ]
        
        req = GenerateRequest(
            provider="suno",
            prompt="test prompt",
            max_new_tokens=256,
            guidance_scale=3.0,
        )
        
        result = await auto_fallback_generation(req)
        
        assert result["job_id"] is None
        assert result["status"] == "failed"
        assert "not configured" in result["error"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
