# backend/app/mcp_server/transport.py
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastmcp import Client as FastMCPClient

from app.mcp_server.server import mcp


@asynccontextmanager
async def get_in_memory_mcp_client() -> AsyncIterator[FastMCPClient]:
    """Provides zero-serialization in-memory FastMCP client session bound to request context."""
    async with FastMCPClient(mcp) as client:
        yield client
