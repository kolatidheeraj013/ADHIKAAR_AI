import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from app.live_schemes import (
    LIVE_EXTRACTION_FAILURE_MSG,
    LIVE_GOVT_SCHEMES,
    fetch_live_government_schemes,
)


def run_async(coro):
    return asyncio.run(coro)


def test_live_govt_schemes_catalog_contains_real_world_portals():
    """Verify the verified live welfare schemes have real live portals and details."""
    assert len(LIVE_GOVT_SCHEMES) >= 6
    ids = {s["scheme_id"] for s in LIVE_GOVT_SCHEMES}
    assert {"pm_kisan", "pmay_g_u", "ayushman_bharat", "pm_ujjwala", "pm_svanidhi", "atal_pension"}.issubset(ids)

    pm_kisan = next(s for s in LIVE_GOVT_SCHEMES if s["scheme_id"] == "pm_kisan")
    assert pm_kisan["official_url"] == "https://pmkisan.gov.in/"
    assert "₹6,000" in pm_kisan["benefit"]
    assert "Aadhaar Card" in pm_kisan["required_documents"]


def test_fetch_live_schemes_fallback_on_failure():
    """Verify that when extraction from myscheme or india.gov fails, it produces the requested failure message."""
    assert "Oh we can't able extract the data from the websites" in LIVE_EXTRACTION_FAILURE_MSG
    assert "https://www.myscheme.gov.in/" in LIVE_EXTRACTION_FAILURE_MSG
    assert "https://www.india.gov.in/my-government/schemes" in LIVE_EXTRACTION_FAILURE_MSG

    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection timed out")):
        schemes, notice = run_async(fetch_live_government_schemes(timeout=0.1))
        assert notice == LIVE_EXTRACTION_FAILURE_MSG
        assert len(schemes) >= 6
        assert any(s["scheme_id"] == "pm_kisan" for s in schemes)
