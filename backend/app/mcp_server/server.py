# backend/app/mcp_server/server.py
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from app.db import get_db_pool
from app.retrieval.hybrid_search import run_expanded_hybrid_search
from app.retrieval.radar_service import fetch_quarantine_items, fetch_stalled_items
from app.retrieval.rbac import (
    fetch_authorized_attachment_page,
    fetch_authorized_email,
    fetch_authorized_matter_timeline,
)
from app.security_context import get_principal

mcp = FastMCP(name="official-email-intelligence")

# Optional in-memory test store injected for sandbox tests
_in_memory_store: Optional[Dict[str, Any]] = None


def set_mcp_in_memory_store(store: Optional[Dict[str, Any]]) -> None:
    """Sets optional mock store for offline testing without database."""
    global _in_memory_store
    _in_memory_store = store


async def _safe_pool():
    if _in_memory_store is not None:
        return None
    try:
        import asyncio
        return await asyncio.wait_for(get_db_pool(), timeout=1.0)
    except Exception:
        return None


@mcp.tool()
async def search_hybrid_with_expansion(query: str, limit: int = 8) -> dict:
    """
    Hybrid BM25 + vector search with Case-State expansion and Gate C reranking.
    RBAC principal is automatically injected from security context.
    """
    principal = get_principal()
    pool = await _safe_pool()
    results = await run_expanded_hybrid_search(
        pool=pool,
        query=query,
        role=principal.role,
        user_email=principal.user_email,
        limit=min(limit, 12),
        in_memory_store=_in_memory_store,
    )
    return {"results": results, "count": len(results)}


@mcp.tool()
async def get_matter_timeline(matter_id: str) -> dict:
    """
    Fetch chronological decisions (ACTIVE vs SUPERSEDED), approvers, and open actions.
    Enforces RBAC against the active role.
    """
    principal = get_principal()
    pool = await _safe_pool()
    return await fetch_authorized_matter_timeline(
        pool=pool,
        matter_id=matter_id,
        role=principal.role,
        user_email=principal.user_email,
        in_memory_matters=_in_memory_store.get("matters") if _in_memory_store else None,
    )


@mcp.tool()
async def inspect_attachment_page(email_id: str, filename: str, page_number: int = 1) -> dict:
    """
    Verifies parent email ACL; returns full Markdown table or RapidOCR text for requested page.
    """
    principal = get_principal()
    pool = await _safe_pool()
    return await fetch_authorized_attachment_page(
        pool=pool,
        email_id=email_id,
        filename=filename,
        page_number=page_number,
        role=principal.role,
        user_email=principal.user_email,
        in_memory_pages=_in_memory_store.get("pages") if _in_memory_store else None,
    )


@mcp.tool()
async def get_raw_email(email_id: str) -> dict:
    """
    Verifies email ACL; returns full immutable headers, raw_body, and sender authority rank.
    """
    principal = get_principal()
    pool = await _safe_pool()
    return await fetch_authorized_email(
        pool=pool,
        email_id=email_id,
        role=principal.role,
        user_email=principal.user_email,
        in_memory_emails=_in_memory_store.get("emails") if _in_memory_store else None,
    )


@mcp.tool()
async def get_stalled_approvals(days_threshold: int = 5) -> dict:
    """
    Returns role-visible stalled requests awaiting sign-off and upcoming resolved deadlines.
    """
    principal = get_principal()
    pool = await _safe_pool()
    return await fetch_stalled_items(
        pool=pool,
        role=principal.role,
        user_email=principal.user_email,
        days_threshold=days_threshold,
        in_memory_store=_in_memory_store,
    )


@mcp.tool()
async def get_quarantine_summary(limit: int = 20) -> dict:
    """
    Restricted to HOD and ADMIN_CLERK; lists auto-quarantined and review-needed emails.
    """
    principal = get_principal()
    pool = await _safe_pool()
    return await fetch_quarantine_items(
        pool=pool,
        role=principal.role,
        user_email=principal.user_email,
        limit=limit,
        in_memory_store=_in_memory_store,
    )
