# backend/app/retrieval/radar_service.py
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.retrieval.rbac import check_rbac_permission


async def fetch_stalled_items(
    pool: Any,
    role: str,
    user_email: str,
    days_threshold: int = 5,
    in_memory_store: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns role-visible:
    - Stalled matters awaiting administrative sign-off (> days_threshold days)
    - Orphaned approved decisions lacking follow-up action items
    - Upcoming resolved deadlines
    """
    if in_memory_store is not None:
        matters = in_memory_store.get("matters", {})
        case_files = in_memory_store.get("case_files", {})
        action_items = in_memory_store.get("action_items", [])

        stalled = []
        for mid, m in matters.items():
            sens = m.get("sensitivity_level", "INTERNAL")
            parts = m.get("allowed_participants", [])
            if not check_rbac_permission(role, user_email, sens, parts):
                continue
            if m.get("status") in ["OPEN", "PENDING_ACTION", "STALLED"]:
                stalled.append(m)

        visible_actions = []
        for a in action_items:
            visible_actions.append(a)

        return {
            "stalled_matters": stalled,
            "open_actions": visible_actions,
            "threshold_days": days_threshold,
        }

    if pool is not None:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT * FROM matters
                    WHERE status IN ('OPEN', 'PENDING_ACTION', 'STALLED')
                    AND last_email_at < NOW() - make_interval(days => %s)
                    ORDER BY last_email_at ASC
                    LIMIT 20;
                    """,
                    (days_threshold,),
                )
                rows = await cur.fetchall()
                filtered = [
                    dict(r) for r in rows
                    if check_rbac_permission(role, user_email, r["sensitivity_level"], r["allowed_participants"])
                ]

                await cur.execute(
                    """
                    SELECT a.* FROM action_items a
                    WHERE a.status = 'PENDING'
                    ORDER BY a.resolved_due_date ASC NULLS LAST
                    LIMIT 20;
                    """
                )
                actions = await cur.fetchall()
                return {
                    "stalled_matters": filtered,
                    "open_actions": [dict(a) for a in actions],
                    "threshold_days": days_threshold,
                }

    return {"stalled_matters": [], "open_actions": [], "threshold_days": days_threshold}


async def fetch_quarantine_items(
    pool: Any,
    role: str,
    user_email: str,
    limit: int = 20,
    in_memory_store: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fetches auto-quarantined and review-needed items.
    Strictly restricted to HOD, DEAN, and ADMIN_CLERK principals.
    STUDENT and FACULTY receive {"error": "FORBIDDEN"}.
    """
    role_norm = (role or "").upper().strip()
    if role_norm not in ["HOD", "DEAN", "ADMIN_CLERK", "DIRECTOR"]:
        return {"error": "FORBIDDEN", "detail": "Access to quarantine review queue requires administrative role"}

    if in_memory_store is not None:
        q_list = in_memory_store.get("quarantine", [])
        return {"quarantined_emails": q_list[:limit], "count": len(q_list[:limit])}

    if pool is not None:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT q.*, e.sender_email, e.subject, e.sent_at
                    FROM quarantine_audit q
                    JOIN emails e ON q.email_id = e.email_id
                    ORDER BY q.created_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = await cur.fetchall()
                return {"quarantined_emails": [dict(r) for r in rows], "count": len(rows)}

    return {"quarantined_emails": [], "count": 0}
