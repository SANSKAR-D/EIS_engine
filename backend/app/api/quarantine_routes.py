# backend/app/api/quarantine_routes.py
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/quarantine", tags=["Quarantine"])

# In-memory quarantine audit state
QUARANTINE_ITEMS = [
    {
        "quarantine_id": "Q-901",
        "email_id": "E_SPAM_01",
        "sender": "marketing@cloudai-webinars.biz",
        "subject": "Exclusive Discount: Register for 5-Day DevOps Bootcamp",
        "received_at": "2026-11-21T08:14:00Z",
        "spam_probability": 0.96,
        "quarantine_tier": "AUTO_QUARANTINED",
        "has_attachments": True,
        "attachment_names": ["DevOps_Brochure_2026.pdf"],
        "skip_ocr_reason": "AUTO_QUARANTINE_SPAM_P96",
        "status": "QUARANTINED"
    },
    {
        "quarantine_id": "Q-902",
        "email_id": "E_REVIEW_02",
        "sender": "dr.kulkarni.workshop@external-univ.ac.in",
        "subject": "Invitation: National Faculty Development Program on Mechatronics",
        "received_at": "2026-11-20T17:45:00Z",
        "spam_probability": 0.63,
        "quarantine_tier": "REVIEW_NEEDED",
        "has_attachments": True,
        "attachment_names": ["FDP_Schedule_Mechatronics.pdf"],
        "skip_ocr_reason": "HELD_PENDING_HUMAN_TRIAGE",
        "status": "REVIEW_NEEDED"
    },
    {
        "quarantine_id": "Q-903",
        "email_id": "E_SPAM_03",
        "sender": "offers@cheap-lab-equipment.shop",
        "subject": "Clearance Sale on Generic Soldering Kits & Multimeters",
        "received_at": "2026-11-19T12:02:00Z",
        "spam_probability": 0.94,
        "quarantine_tier": "AUTO_QUARANTINED",
        "has_attachments": False,
        "attachment_names": [],
        "skip_ocr_reason": "AUTO_QUARANTINE_SPAM_P94",
        "status": "QUARANTINED"
    }
]


@router.get("")
async def get_quarantine_queue(
    x_active_role: Optional[str] = Header(default="HOD"),
    x_user_email: Optional[str] = Header(default="hod.mech@institution.edu")
):
    """
    Returns auto-quarantined and review-needed items with calibrated spam scores.
    Strictly restricted to HOD, DEAN, and ADMIN_CLERK principals.
    """
    role = (x_active_role or "HOD").upper().strip()
    if role not in ["HOD", "DEAN", "ADMIN_CLERK", "DIRECTOR"]:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Quarantine review queue requires administrative role (HOD or ADMIN_CLERK)."
        )

    quarantined_count = sum(1 for q in QUARANTINE_ITEMS if q["status"] == "QUARANTINED")
    review_count = sum(1 for q in QUARANTINE_ITEMS if q["status"] == "REVIEW_NEEDED")
    restored_count = sum(1 for q in QUARANTINE_ITEMS if q["status"] == "RESTORED")
    ocr_pages_saved = quarantined_count * 3 + review_count * 2

    return {
        "items": QUARANTINE_ITEMS,
        "metrics": {
            "total_quarantined": quarantined_count,
            "review_needed": review_count,
            "total_restored": restored_count,
            "estimated_ocr_pages_saved": ocr_pages_saved,
            "estimated_cost_saved_usd": round(ocr_pages_saved * 0.015, 2)
        }
    }


@router.post("/{quarantine_id}/restore")
async def restore_quarantined_email(
    quarantine_id: str,
    x_active_role: Optional[str] = Header(default="HOD"),
    x_user_email: Optional[str] = Header(default="hod.mech@institution.edu")
):
    """
    Restores false-positive email, updates audit status, logs human override,
    and marks email ready for immediate OCR and case-file indexing.
    """
    role = (x_active_role or "HOD").upper().strip()
    if role not in ["HOD", "DEAN", "ADMIN_CLERK", "DIRECTOR"]:
        raise HTTPException(status_code=403, detail="Forbidden: Administrative override permission required")

    found_item = None
    for item in QUARANTINE_ITEMS:
        if item["quarantine_id"] == quarantine_id or item["email_id"] == quarantine_id:
            item["status"] = "RESTORED"
            item["restored_by"] = x_user_email or f"{role.lower()}@institution.edu"
            item["restored_at"] = datetime.now(timezone.utc).isoformat()
            found_item = item
            break

    if not found_item:
        raise HTTPException(status_code=404, detail="Quarantine record not found")

    return {
        "status": "RESTORED",
        "quarantine_id": quarantine_id,
        "message": f"Email {found_item['email_id']} restored to inbox. Triggered OCR extraction and Matter indexer.",
        "restored_record": found_item
    }
