# backend/app/api/radar_routes.py
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header

router = APIRouter(prefix="/api/v1/radar", tags=["Radar"])

CANONICAL_STALLS = [
    {
        "stall_id": "STL-01",
        "matter_id": "MAT-2026-EXAM-CONF",
        "matter_title": "End-Semester Confidential Question Paper Moderation & External Examiners",
        "stalled_type": "STALLED_APPROVAL",
        "pending_with_role": "HOD",
        "pending_with_user": "Prof. A. K. Sharma (HoD Mechanical)",
        "days_elapsed": 7,
        "urgency_score": 4,
        "sensitivity_level": "CONFIDENTIAL",
        "allowed_participants": ["hod.mech@institution.edu", "dean.academics@institution.edu"],
        "context_snippet": "External moderation committee draft submitted on 2026-11-10; requires HoD formal sign-off before printing.",
        "recommended_action": "Urgent reminder: exam printing pipeline commences in 48 hours."
    },
    {
        "stall_id": "STL-02",
        "matter_id": "MAT-2026-CNC",
        "matter_title": "Procurement of 3-Axis CNC Milling Machine for CAD/CAM Lab",
        "stalled_type": "ORPHANED_APPROVAL",
        "pending_with_role": "ADMIN_CLERK",
        "pending_with_user": "Shri M. Rawat (Purchase Section)",
        "days_elapsed": 6,
        "urgency_score": 3,
        "sensitivity_level": "INTERNAL",
        "allowed_participants": ["hod.mech@institution.edu", "purchase.clerk@institution.edu", "lab.incharge@institution.edu"],
        "context_snippet": "HoD approved Vendor B on 2026-11-16. No subsequent Purchase Order (PO) draft has been generated in ERP.",
        "recommended_action": "Notify clerk to raise Purchase Order draft to avoid price escalation."
    }
]

CANONICAL_UPCOMING_DEADLINES = [
    {
        "deadline_id": "DDL-101",
        "matter_id": "MAT-2026-CNC",
        "matter_title": "Procurement of 3-Axis CNC Milling Machine for CAD/CAM Lab",
        "task_description": "Raise formal Purchase Order (PO) in ERP with approved Vendor B terms",
        "owner": "Purchase Section Clerk",
        "raw_text": "within 10 days of approval",
        "resolved_due_date": "2026-11-26",
        "days_remaining": 4,
        "urgency": "HIGH",
        "sensitivity_level": "INTERNAL"
    },
    {
        "deadline_id": "DDL-102",
        "matter_id": "MAT-2026-CNC",
        "matter_title": "Procurement of 3-Axis CNC Milling Machine for CAD/CAM Lab",
        "task_description": "Collect 10% Performance Bank Guarantee from Vendor B",
        "owner": "Finance Officer",
        "raw_text": "by first week of December",
        "resolved_due_date": "2026-12-05",
        "days_remaining": 13,
        "urgency": "MEDIUM",
        "sensitivity_level": "INTERNAL"
    },
    {
        "deadline_id": "DDL-103",
        "matter_id": "MAT-2026-FEST",
        "matter_title": "Annual National Tech Symposium 'INNOVENT 2026'",
        "task_description": "Close Early-Bird Student Hackathon Registrations",
        "owner": "Student Affairs Coordinator",
        "raw_text": "by end of November",
        "resolved_due_date": "2026-11-30",
        "days_remaining": 8,
        "urgency": "LOW",
        "sensitivity_level": "PUBLIC"
    }
]


@router.get("/stalls")
async def get_stalls_and_radar(
    x_active_role: Optional[str] = Header(default="HOD"),
    x_user_email: Optional[str] = Header(default="hod.mech@institution.edu")
):
    """
    Returns stalled approval requests, orphaned decisions, and upcoming resolved ISO deadlines.
    Enforces role RBAC visibility.
    """
    role = (x_active_role or "HOD").upper().strip()
    user_email = (x_user_email or "").strip().lower()

    visible_stalls = []
    for s in CANONICAL_STALLS:
        sens = s["sensitivity_level"]
        parts = s["allowed_participants"]
        if role == "STUDENT":
            if sens == "PUBLIC" or user_email in parts:
                visible_stalls.append(s)
        elif role in ["FACULTY", "ADMIN_CLERK"]:
            if sens in ["PUBLIC", "INTERNAL"] or user_email in parts:
                visible_stalls.append(s)
        else:
            visible_stalls.append(s)

    visible_deadlines = []
    for d in CANONICAL_UPCOMING_DEADLINES:
        sens = d["sensitivity_level"]
        if role == "STUDENT" and sens != "PUBLIC":
            continue
        visible_deadlines.append(d)

    return {
        "stalled_items": visible_stalls,
        "upcoming_deadlines": visible_deadlines,
        "threshold_days": 5,
        "active_role": role
    }
