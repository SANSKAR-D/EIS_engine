# backend/tests/test_phase0_health.py
import pytest
from httpx import AsyncClient, ASGITransport
import google.genai
from app.main import app
from app.db import check_db_health

@pytest.mark.asyncio
async def test_google_genai_version():
    """Verify google-genai >= 3.6.1 is installed and available."""
    version = google.genai.__version__
    parts = [int(p) for p in version.split(".")[:2]]
    assert parts[0] > 3 or (parts[0] == 3 and parts[1] >= 6), f"Expected >= 3.6.1, got {version}"

@pytest.mark.asyncio
async def test_database_health_and_tables(db_pool):
    """Verify PostgreSQL 16 + pgvector is healthy with 13 tables."""
    health = await check_db_health()
    assert health["postgres"] == "connected"
    assert health["pgvector"] is not None, "pgvector extension must be installed"
    assert health["public_tables"] == 13, f"Expected 13 tables, found {health['public_tables']}"

@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify GET /health returns 200 OK with expected payload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "healthy"
        assert payload["db"]["postgres"] == "connected"
        assert payload["db"]["pgvector"] is not None
        assert payload["db"]["public_tables"] == 13
