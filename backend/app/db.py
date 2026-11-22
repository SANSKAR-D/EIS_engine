# backend/app/db.py
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List

# if sys.platform == "win32":
#     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from app.config import settings

_pool: Optional[AsyncConnectionPool] = None

async def init_db_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=2,
            max_size=20,
            open=False,
            kwargs={"row_factory": dict_row}
        )
        await _pool.open()
    return _pool

async def close_db_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

async def get_db_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        await init_db_pool()
    return _pool

@asynccontextmanager
async def get_db_connection():
    pool = await get_db_pool()
    async with pool.connection() as conn:
        yield conn

async def check_db_health() -> Dict[str, Any]:
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1 as alive;")
            await cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            vector_row = await cur.fetchone()
            await cur.execute("SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = 'public';")
            table_row = await cur.fetchone()
            return {
                "postgres": "connected",
                "pgvector": vector_row["extversion"] if vector_row else None,
                "public_tables": table_row["table_count"] if table_row else 0
            }

async def mark_quarantined(email_id: str, spam_probability: float, status: str, reason_summary: Optional[str] = None):
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO quarantine_audit (email_id, spam_probability, status, reason_summary)
                VALUES (%s, %s, %s, %s);
                UPDATE emails SET triage_category = 'SPAM' WHERE email_id = %s;
                """,
                (email_id, spam_probability, status, reason_summary, email_id)
            )

async def update_email_triage(email_id: str, category: str, spam_p: Optional[float] = None,
                              sensitivity: Optional[str] = None, has_decision: Optional[float] = None,
                              urgency: Optional[int] = None, meta: Optional[dict] = None):
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE emails SET
                    triage_category = %s,
                    spam_probability = COALESCE(%s, spam_probability),
                    sensitivity_level = COALESCE(%s, sensitivity_level),
                    has_decision_prob = COALESCE(%s, has_decision_prob),
                    urgency_score = COALESCE(%s, urgency_score),
                    triage_meta = COALESCE(%s::jsonb, triage_meta)
                WHERE email_id = %s;
                """,
                (category, spam_p, sensitivity, has_decision, urgency, meta, email_id)
            )

async def upsert_attachment_pages(pages: list):
    if not pages:
        return
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for page in pages:
                await cur.execute(
                    "SELECT attachment_id FROM attachments WHERE email_id = %s AND filename = %s LIMIT 1;",
                    (page.email_id, page.filename)
                )
                row = await cur.fetchone()
                if row:
                    att_id = row["attachment_id"]
                    await cur.execute(
                        """
                        INSERT INTO attachment_pages (
                            attachment_id, email_id, page_number, extraction_method,
                            mean_confidence, has_tables, extracted_text
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (attachment_id, page_number) DO UPDATE SET
                            extraction_method = EXCLUDED.extraction_method,
                            mean_confidence = EXCLUDED.mean_confidence,
                            has_tables = EXCLUDED.has_tables,
                            extracted_text = EXCLUDED.extracted_text;
                        """,
                        (att_id, page.email_id, page.page_number, page.extraction_method, page.mean_confidence, page.has_tables, page.extracted_text)
                    )

async def upsert_matters(matters: list):
    if not matters:
        return
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for m in matters:
                await cur.execute(
                    """
                    INSERT INTO matters (
                        matter_id, canonical_title, topic_domain, sensitivity_level,
                        allowed_participants, first_email_at, last_email_at,
                        email_count, max_urgency, status, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (matter_id) DO UPDATE SET
                        canonical_title = EXCLUDED.canonical_title,
                        topic_domain = EXCLUDED.topic_domain,
                        sensitivity_level = EXCLUDED.sensitivity_level,
                        allowed_participants = EXCLUDED.allowed_participants,
                        first_email_at = EXCLUDED.first_email_at,
                        last_email_at = EXCLUDED.last_email_at,
                        email_count = EXCLUDED.email_count,
                        max_urgency = EXCLUDED.max_urgency,
                        status = EXCLUDED.status,
                        updated_at = NOW();
                    """,
                    (
                        m["matter_id"], m["canonical_title"], m.get("topic_domain", "ADMIN"),
                        m["sensitivity_level"], m["allowed_participants"], m["first_email_at"],
                        m["last_email_at"], m["email_count"], m["max_urgency"], m.get("status", "OPEN")
                    )
                )

async def upsert_matter_emails(links: list):
    if not links:
        return
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for link in links:
                await cur.execute(
                    """
                    INSERT INTO matter_emails (matter_id, email_id, link_method, merge_confidence)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (matter_id, email_id) DO UPDATE SET
                        link_method = EXCLUDED.link_method,
                        merge_confidence = EXCLUDED.merge_confidence;
                    """,
                    (link["matter_id"], link["email_id"], link["link_method"], link["merge_confidence"])
                )

async def upsert_case_file(case_file: dict):
    pool = await get_db_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            import json
            await cur.execute(
                """
                INSERT INTO case_files (
                    matter_id, canonical_title, summary, latest_status_note,
                    final_decision, approved_by, approver_role, approval_email_id,
                    case_file_json, version, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
                ON CONFLICT (matter_id) DO UPDATE SET
                    canonical_title = EXCLUDED.canonical_title,
                    summary = EXCLUDED.summary,
                    latest_status_note = EXCLUDED.latest_status_note,
                    final_decision = EXCLUDED.final_decision,
                    approved_by = EXCLUDED.approved_by,
                    approver_role = EXCLUDED.approver_role,
                    approval_email_id = EXCLUDED.approval_email_id,
                    case_file_json = EXCLUDED.case_file_json,
                    version = case_files.version + 1,
                    updated_at = NOW();
                """,
                (
                    case_file["matter_id"], case_file["canonical_title"], case_file["summary"],
                    case_file["latest_status_note"], case_file.get("final_decision"),
                    case_file.get("approved_by"), case_file.get("approver_role"),
                    case_file.get("approval_email_id"), json.dumps(case_file),
                    case_file.get("version", 1)
                )
            )

