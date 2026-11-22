# backend/tests/conftest.py
import pytest
import pytest_asyncio
from app.config import settings

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool():
    from app.db import init_db_pool, close_db_pool
    pool = await init_db_pool()
    yield pool
    await close_db_pool()

@pytest.fixture(autouse=True)
def ensure_mock_ai_if_no_key(monkeypatch):
    if not settings.gemini_api_key:
        monkeypatch.setattr(settings, "use_mock_ai", True)
