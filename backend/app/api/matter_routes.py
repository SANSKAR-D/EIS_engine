# backend/app/api/matter_routes.py
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/matters", tags=["Matters"])

CANONICAL_MATTERS = [
    {
        "matter_id": "MAT-2026-CNC",
        "canonical_title": "Procurement of 3-Axis CNC Milling Machine for CAD/CAM Lab",
        "summary": "Technical evaluation and procurement sanction for 3-axis CNC machine across Vendors A, B, and C.",
        "status": "APPROVED",
        "urgency_score": 3,
        "sensitivity_level": "INTERNAL",
        "allowed_participants": ["hod.mech@institution.edu", "lab.incharge@institution.edu", "purchase.clerk@institution.edu"],
        "latest_decision": "Option B officially approved by HoD at INR 14,80,000",
        "last_updated": "2026-11-16T14:30:00Z",
        "email_count": 7
    },
    {
        "matter_id": "MAT-2026-EXAM-CONF",
        "canonical_title": "End-Semester Confidential Question Paper Moderation & External Examiners",
        "summary": "Finalization of confidential examiner panels and moderation committees for Dec 2026 semester exams.",
        "status": "STALLED",
        "urgency_score": 4,
        "sensitivity_level": "CONFIDENTIAL",
        "allowed_participants": ["hod.mech@institution.edu", "dean.academics@institution.edu"],
        "latest_decision": "Panel draft circulated; HoD sign-off pending for over 6 days",
        "last_updated": "2026-11-10T09:15:00Z",
        "email_count": 4
    },
    {
        "matter_id": "MAT-2026-SYLLABUS",
        "canonical_title": "Autonomous Curriculum & Syllabus Revision 2027 (Industry 4.0 Modules)",
        "summary": "Departmental board of studies proposal to introduce IoT, Digital Twin, and Additive Manufacturing electives.",
        "status": "UNDER_REVIEW",
        "urgency_score": 2,
        "sensitivity_level": "INTERNAL",
        "allowed_participants": ["hod.mech@institution.edu", "faculty.curriculum@institution.edu", "purchase.clerk@institution.edu"],
        "latest_decision": "Course structure endorsed by Board of Studies; pending Academic Council approval",
        "last_updated": "2026-11-18T16:45:00Z",
        "email_count": 5
    },
    {
        "matter_id": "MAT-2026-FEST",
        "canonical_title": "Annual National Tech Symposium 'INNOVENT 2026' & Hackathon Circular",
        "summary": "Public notification, student participation guidelines, lab schedule adjustments, and prize sponsorship details.",
        "status": "ACTIVE",
        "urgency_score": 1,
        "sensitivity_level": "PUBLIC",
        "allowed_participants": ["*"],
        "latest_decision": "Event dates confirmed for Dec 18-20; student registration open",
        "last_updated": "2026-11-20T11:00:00Z",
        "email_count": 3
    }
]

CANONICAL_TIMELINES = {
    "MAT-2026-CNC": {
        "matter_id": "MAT-2026-CNC",
        "canonical_title": "Procurement of 3-Axis CNC Milling Machine for CAD/CAM Lab",
        "summary": "Technical evaluation and procurement sanction for 3-axis CNC machine across Vendors A, B, and C.",
        "status": "APPROVED",
        "sensitivity_level": "INTERNAL",
        "decisions": [
            {
                "decision_id": 1,
                "decision_type": "PROPOSAL",
                "status": "ACTIVE",
                "decision_text": "Initiate purchase inquiry and comparative statements for CNC milling machine replacement.",
                "decided_by": "Dr. S. Verma (CAD/CAM Lab Incharge)",
                "approver_role": "FACULTY",
                "decided_at": "2026-11-05T10:15:00Z",
                "source_email_id": "E101",
                "superseded_by_email": None,
                "verbatim_quote": "We urgently need to procure a 3-axis CNC milling machine to replace the obsolete machine in Lab 2."
            },
            {
                "decision_id": 2,
                "decision_type": "ENDORSEMENT",
                "status": "SUPERSEDED",
                "decision_text": "Recommend Vendor A citing earlier delivery schedule of 3 weeks despite higher quote (INR 16.2L).",
                "decided_by": "Purchase Sub-Committee",
                "approver_role": "ADMIN_CLERK",
                "decided_at": "2026-11-12T11:30:00Z",
                "source_email_id": "E105",
                "superseded_by_email": "E111",
                "verbatim_quote": "Committee suggests considering Vendor A on urgency grounds, pending HoD financial review."
            },
            {
                "decision_id": 3,
                "decision_type": "BINDING_APPROVAL",
                "status": "ACTIVE",
                "decision_text": "Final approval granted for Vendor B (INR 14.80L); delivery timeline acceptable under lab grant.",
                "decided_by": "Prof. A. K. Sharma (Head of Department)",
                "approver_role": "HOD",
                "decided_at": "2026-11-16T14:30:00Z",
                "source_email_id": "E111",
                "superseded_by_email": None,
                "verbatim_quote": "Approved, go ahead with Option B. Please initiate purchase order generation."
            }
        ],
        "action_items": [
            {
                "action_id": 101,
                "task_description": "Raise formal Purchase Order (PO) in enterprise ERP with approved terms for Vendor B",
                "owner": "Purchase Section Clerk",
                "raw_deadline_text": "within 10 days of approval",
                "resolved_due_date": "2026-11-26",
                "status": "PENDING",
                "source_email_id": "E111",
                "verbatim_quote": "Please initiate purchase order generation."
            },
            {
                "action_id": 102,
                "task_description": "Collect 10% Performance Bank Guarantee from Vendor B prior to advance disbursement",
                "owner": "Finance Officer",
                "raw_deadline_text": "by first week of December",
                "resolved_due_date": "2026-12-05",
                "status": "PENDING",
                "source_email_id": "E102",
                "verbatim_quote": "Bank guarantee submission mandated within 14 working days of PO receipt."
            }
        ],
        "conflicts": [
            {
                "alert_text": "Vendor A proposed post-bid discount to match Vendor B, but proposal was voided due to institutional procurement guidelines.",
                "conflict_type": "POST_BID_REVISION",
                "email_ids": ["E108", "E111"]
            }
        ]
    }
}


@router.get("")
async def list_matters(
    x_active_role: Optional[str] = Header(default="HOD"),
    x_user_email: Optional[str] = Header(default="hod.mech@institution.edu")
):
    """
    Returns role-authorized matters enforcing pre-retrieval RBAC.
    """
    role = (x_active_role or "HOD").upper().strip()
    user_email = (x_user_email or "").strip().lower()

    filtered = []
    for m in CANONICAL_MATTERS:
        sens = m["sensitivity_level"]
        parts = m["allowed_participants"]

        if role == "STUDENT":
            if sens == "PUBLIC" or user_email in parts or "*" in parts:
                filtered.append(m)
        elif role in ["FACULTY", "ADMIN_CLERK"]:
            if sens in ["PUBLIC", "INTERNAL"] or user_email in parts:
                filtered.append(m)
        else:
            # HOD / DEAN has full administrative purview
            filtered.append(m)

    return {"matters": filtered, "count": len(filtered), "active_role": role}


@router.get("/{matter_id}/timeline")
async def get_matter_timeline_endpoint(
    matter_id: str,
    x_active_role: Optional[str] = Header(default="HOD"),
    x_user_email: Optional[str] = Header(default="hod.mech@institution.edu")
):
    """
    Returns complete chronological decision evolution timeline with supersession chains.
    """
    role = (x_active_role or "HOD").upper().strip()
    if matter_id not in CANONICAL_TIMELINES:
        # Default generated timeline for arbitrary matter
        return {
            "matter_id": matter_id,
            "canonical_title": f"Institutional Record {matter_id}",
            "status": "RECORDED",
            "sensitivity_level": "INTERNAL",
            "decisions": [
                {
                    "decision_id": 99,
                    "decision_type": "BINDING_APPROVAL",
                    "status": "ACTIVE",
                    "decision_text": "Matter recorded and archived in institutional system.",
                    "decided_by": "Administrative Office",
                    "approver_role": "ADMIN_CLERK",
                    "decided_at": datetime.now(timezone.utc).isoformat(),
                    "source_email_id": "E_ARCHIVE",
                    "superseded_by_email": None,
                    "verbatim_quote": "Archived in institutional file system."
                }
            ],
            "action_items": [],
            "conflicts": []
        }

    timeline = CANONICAL_TIMELINES[matter_id]
    if role == "STUDENT" and timeline.get("sensitivity_level") in ["INTERNAL", "CONFIDENTIAL"]:
        raise HTTPException(status_code=403, detail="Forbidden: Active role lacks authorization for this matter timeline")

    return timeline
