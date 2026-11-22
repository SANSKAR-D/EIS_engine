# backend/app/retrieval/rbac.py
from typing import Any, Dict, List, Optional, Tuple


def build_rbac_filter(role: str, user_email: str, table_prefix: str = "") -> Tuple[str, List[Any]]:
    """
    Constructs parameterized SQL WHERE clause enforcing Pre-Retrieval RBAC isolation.
    Roles:
    - HOD / DEAN: Access to PUBLIC, INTERNAL, and all CONFIDENTIAL departmental records.
    - FACULTY / ADMIN_CLERK: Access to PUBLIC, INTERNAL, and CONFIDENTIAL only where participant.
    - STUDENT: Access to PUBLIC notices + own participant threads only.
    """
    role_norm = (role or "").upper().strip()
    user_norm = (user_email or "").lower().strip()
    prefix = f"{table_prefix}." if table_prefix else ""

    col_sens = f"{prefix}sensitivity_level"
    col_parts = f"{prefix}allowed_participants"

    if role_norm in ["HOD", "DEAN", "DIRECTOR", "AUDITOR"]:
        return "1=1", []

    if role_norm in ["FACULTY", "ADMIN_CLERK", "CLERK", "PURCHASE_OFFICER"]:
        sql = f"({col_sens} IN ('PUBLIC', 'INTERNAL') OR ({col_sens} = 'CONFIDENTIAL' AND %s = ANY({col_parts})))"
        return sql, [user_norm]

    # STUDENT / EXTERNAL default
    sql = f"({col_sens} = 'PUBLIC' OR %s = ANY({col_parts}))"
    return sql, [user_norm]


def check_rbac_permission(
    role: str,
    user_email: str,
    sensitivity_level: str,
    allowed_participants: Optional[List[str]] = None,
) -> bool:
    """
    Synchronous RBAC validator for standalone object inspection and unit tests.
    """
    role_norm = (role or "").upper().strip()
    user_norm = (user_email or "").lower().strip()
    sens_norm = (sensitivity_level or "INTERNAL").upper().strip()
    participants = {p.lower().strip() for p in (allowed_participants or [])}

    if role_norm in ["HOD", "DEAN", "DIRECTOR", "AUDITOR"]:
        return True

    if role_norm in ["FACULTY", "ADMIN_CLERK", "CLERK", "PURCHASE_OFFICER"]:
        if sens_norm in ["PUBLIC", "INTERNAL"]:
            return True
        if sens_norm == "CONFIDENTIAL":
            return user_norm in participants
        return False

    if role_norm in ["STUDENT", "EXTERNAL"]:
        if sens_norm == "PUBLIC":
            return True
        return user_norm in participants

    return False


async def fetch_authorized_matter_timeline(
    pool: Any,
    matter_id: str,
    role: str,
    user_email: str,
    in_memory_matters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetches matter timeline if principal has RBAC authorization."""
    if in_memory_matters and matter_id in in_memory_matters:
        m = in_memory_matters[matter_id]
        if not check_rbac_permission(role, user_email, m.get("sensitivity_level", "INTERNAL"), m.get("allowed_participants", [])):
            return {"error": "FORBIDDEN", "detail": "RBAC access denied for confidential matter"}
        return m

    if pool is not None:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM matters WHERE matter_id = %s LIMIT 1;",
                    (matter_id,)
                )
                m = await cur.fetchone()
                if not m:
                    return {"error": "NOT_FOUND"}
                if not check_rbac_permission(role, user_email, m["sensitivity_level"], m["allowed_participants"]):
                    return {"error": "FORBIDDEN", "detail": "RBAC access denied for confidential matter"}

                await cur.execute("SELECT * FROM case_files WHERE matter_id = %s LIMIT 1;", (matter_id,))
                cf = await cur.fetchone()
                return {"matter": m, "case_file": cf}

    return {"error": "NOT_FOUND"}


async def fetch_authorized_email(
    pool: Any,
    email_id: str,
    role: str,
    user_email: str,
    in_memory_emails: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetches email raw body and metadata if authorized."""
    if in_memory_emails and email_id in in_memory_emails:
        e = in_memory_emails[email_id]
        if not check_rbac_permission(role, user_email, e.get("sensitivity_level", "INTERNAL"), e.get("participants", [])):
            return {"error": "FORBIDDEN"}
        return e

    if pool is not None:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM emails WHERE email_id = %s LIMIT 1;", (email_id,))
                e = await cur.fetchone()
                if not e:
                    return {"error": "NOT_FOUND"}
                if not check_rbac_permission(role, user_email, e["sensitivity_level"], e["participants"]):
                    return {"error": "FORBIDDEN"}
                return e

    return {"error": "NOT_FOUND"}


async def fetch_authorized_attachment_page(
    pool: Any,
    email_id: str,
    filename: str,
    page_number: int,
    role: str,
    user_email: str,
    in_memory_pages: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Inspects attachment page verifying parent email RBAC."""
    key = f"{email_id}:{filename}:{page_number}"
    if in_memory_pages and key in in_memory_pages:
        item = in_memory_pages[key]
        if not check_rbac_permission(role, user_email, item.get("sensitivity_level", "INTERNAL"), item.get("participants", [])):
            return {"error": "FORBIDDEN"}
        return item

    if pool is not None:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT sensitivity_level, participants FROM emails WHERE email_id = %s LIMIT 1;", (email_id,))
                e = await cur.fetchone()
                if not e:
                    return {"error": "NOT_FOUND"}
                if not check_rbac_permission(role, user_email, e["sensitivity_level"], e["participants"]):
                    return {"error": "FORBIDDEN"}

                await cur.execute(
                    """
                    SELECT p.* FROM attachment_pages p
                    JOIN attachments a ON p.attachment_id = a.attachment_id
                    WHERE p.email_id = %s AND a.filename = %s AND p.page_number = %s
                    LIMIT 1;
                    """,
                    (email_id, filename, page_number)
                )
                p = await cur.fetchone()
                return p if p else {"error": "NOT_FOUND"}

    return {"error": "NOT_FOUND"}
