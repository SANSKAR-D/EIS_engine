# backend/app/api/sources_routes.py
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from app.retrieval.dataset_store import get_email_record, append_email_record

router = APIRouter(prefix="/api/v1/sources", tags=["Sources"])


class IngestEmailRequest(BaseModel):
    email_id: str
    thread_id: str
    sender: str
    recipients: List[str]
    subject: str
    timestamp: str
    body: str
    in_reply_to: Optional[str] = ""
    attachments: Optional[List[str]] = Field(default_factory=list)


@router.post("/ingest", status_code=201)
async def ingest_new_email(
    req: IngestEmailRequest,
    x_active_role: Optional[str] = Header(default="HOD")
):
    """
    Ingests a new institutional email record into the dataset ledger and hot-reloads the index.
    Restricted to HOD and ADMIN_CLERK roles.
    """
    role = (x_active_role or "HOD").upper().strip()
    if role not in ["HOD", "ADMIN_CLERK"]:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Ingestion privileges are restricted to administrative roles (HOD or ADMIN_CLERK)."
        )

    record = append_email_record(
        email_id=req.email_id,
        thread_id=req.thread_id,
        sender=req.sender,
        recipients=req.recipients,
        subject=req.subject,
        timestamp=req.timestamp,
        body=req.body,
        in_reply_to=req.in_reply_to or "",
        attachments=req.attachments or []
    )
    return {"status": "ingested", "record": record}


@router.get("/{email_id}")
async def get_source_email(
    email_id: str,
    x_active_role: Optional[str] = Header(default="HOD"),
    x_user_email: Optional[str] = Header(default=None)
):
    """
    Returns immutable raw email, sender authority, and parsed attachment pages.
    Enforces RBAC against the active user role.
    """
    role = (x_active_role or "HOD").upper().strip()
    user_email = (x_user_email or f"{role.lower()}@institution.edu").strip().lower()

    record = get_email_record(email_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Email source record #{email_id} not found in institutional repository.")

    sens = record.get("sensitivity_level", "INTERNAL")
    sender = record.get("sender", "").lower()
    recipients = [r.lower() for r in record.get("recipients", [])]

    # Enforce RBAC
    if role == "STUDENT":
        if sens != "PUBLIC" and user_email not in sender and user_email not in recipients:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: Email #{email_id} is classified as {sens} institutional correspondence and cannot be viewed by the STUDENT role."
            )
    elif role in ["FACULTY", "ADMIN_CLERK"]:
        if sens == "CONFIDENTIAL" and user_email not in sender and user_email not in recipients:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: Email #{email_id} is marked as CONFIDENTIAL and requires administrative or participant clearance."
            )

    return record
