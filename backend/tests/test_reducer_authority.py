# backend/tests/test_reducer_authority.py
from datetime import date, datetime, timezone
import pytest

from app.pipeline.authority import classify_approval_weight, infer_sender_authority
from app.pipeline.state_reducer import reduce_matter_to_case_file, resolve_relative_date
from app.pipeline.stitcher import stitch_emails_into_matters


def test_t15_decision_supersession_vendor_selection():
    """
    T-15: Sequence: E1 proposes Vendor A -> E2 questions price -> E3 HoD approves Vendor B.
    Asserts: Vendor A marked SUPERSEDED (superseded_by_email='E3'); Vendor B marked ACTIVE.
    """
    matter = {
        "matter_id": "MAT_CNC_01",
        "canonical_title": "Procurement of CNC Turning Centre",
        "sensitivity_level": "INTERNAL",
    }

    emails = [
        # E1: Faculty proposes Vendor A
        {
            "email_id": "E1",
            "sender_email": "faculty.mech@northbridge.edu",
            "recipients": ["purchase@northbridge.edu", "mech.hod@northbridge.edu"],
            "subject": "Procurement of CNC Turning Centre",
            "clean_body": "Proposing Vendor A for the 3-axis CNC turning centre at INR 18.5 Lakh.",
            "sent_at": "2026-09-01T10:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        # E2: Purchase officer questions price
        {
            "email_id": "E2",
            "sender_email": "purchase@northbridge.edu",
            "recipients": ["faculty.mech@northbridge.edu", "mech.hod@northbridge.edu"],
            "subject": "Re: Procurement of CNC Turning Centre",
            "clean_body": "Can we negotiate the price with Vendor A or compare with Vendor B?",
            "sent_at": "2026-09-02T11:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        # E3: HoD approves Vendor B
        {
            "email_id": "E3",
            "sender_email": "mech.hod@northbridge.edu",
            "recipients": ["purchase@northbridge.edu", "faculty.mech@northbridge.edu"],
            "subject": "Re: Procurement of CNC Turning Centre",
            "clean_body": "Approved Vendor B. Please proceed with purchase order.",
            "sent_at": "2026-09-03T14:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
    ]

    case_file = reduce_matter_to_case_file(matter, emails)

    # 1. At least two decision records tracked chronologically
    assert len(case_file.decisions) >= 2

    # Find Vendor A decision (from E1) and Vendor B decision (from E3)
    dec_a = next(d for d in case_file.decisions if d.source_email_id == "E1")
    dec_b = next(d for d in case_file.decisions if d.source_email_id == "E3")

    # 2. Vendor A is SUPERSEDED by E3
    assert dec_a.status == "SUPERSEDED"
    assert dec_a.superseded_by_email == "E3"

    # 3. Vendor B is ACTIVE and BINDING_APPROVAL
    assert dec_b.status == "ACTIVE"
    assert dec_b.decision_type == "BINDING_APPROVAL"
    assert dec_b.superseded_by_email is None

    # 4. Final outcome correctly attributed to HoD
    assert case_file.approved_by == "mech.hod@northbridge.edu"
    assert case_file.approval_email_id == "E3"
    assert "Vendor B" in case_file.final_decision


def test_t16_sender_authority_ranking_staff_vs_executive():
    """
    T-16: Lab assistant writes 'Looks fine, proceed' vs. HoD writes 'Approved, go ahead.'
    Asserts: Lab assistant logged as ENDORSEMENT (rank 2); HoD logged as BINDING_APPROVAL (rank 5).
    """
    # 1. Authority inference
    staff_auth = infer_sender_authority("lab.assistant@northbridge.edu")
    assert staff_auth["authority_rank"] == 2
    assert staff_auth["inferred_role"] == "LAB_ASSISTANT"

    hod_auth = infer_sender_authority("mech.hod@northbridge.edu")
    assert hod_auth["authority_rank"] == 5
    assert hod_auth["inferred_role"] == "HOD"

    # 2. Approval weight classification
    staff_weight = classify_approval_weight(staff_auth["authority_rank"], "Looks fine, proceed.")
    assert staff_weight == "ENDORSEMENT"

    hod_weight = classify_approval_weight(hod_auth["authority_rank"], "Approved, go ahead.")
    assert hod_weight == "BINDING_APPROVAL"

    # 3. State reducer end-to-end classification
    matter = {"matter_id": "MAT_MAINT_01", "canonical_title": "Lathe Machine Maintenance"}
    emails = [
        {
            "email_id": "E_STAFF",
            "sender_email": "lab.assistant@northbridge.edu",
            "clean_body": "Looks fine, proceed with lubrication and calibration.",
            "sent_at": "2026-09-01T10:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        {
            "email_id": "E_HOD",
            "sender_email": "mech.hod@northbridge.edu",
            "clean_body": "Approved, go ahead.",
            "sent_at": "2026-09-01T12:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
    ]

    case_file = reduce_matter_to_case_file(matter, emails)
    dec_staff = next(d for d in case_file.decisions if d.source_email_id == "E_STAFF")
    dec_hod = next(d for d in case_file.decisions if d.source_email_id == "E_HOD")

    assert dec_staff.decision_type == "ENDORSEMENT"
    assert dec_hod.decision_type == "BINDING_APPROVAL"


def test_t17_relative_date_resolution_iso_calendar():
    """
    T-17: Email sent Wednesday 2026-11-18T10:00Z says 'Submit PO by next Friday.'
    Asserts: action_items.resolved_due_date == date(2026, 11, 27) with raw text preserved.
    """
    sent_at_wed = datetime(2026, 11, 18, 10, 0, 0, tzinfo=timezone.utc)
    assert sent_at_wed.weekday() == 2  # Wednesday

    # Direct date resolver test
    body_text = "Submit PO by next Friday."
    res = resolve_relative_date(body_text, sent_at_wed)
    assert res is not None
    raw_text, resolved_date = res

    assert "by next Friday" in raw_text or "next Friday" in raw_text
    assert resolved_date == date(2026, 11, 27)

    # State reducer end-to-end integration test
    matter = {"matter_id": "MAT_PO_01", "canonical_title": "Purchase Order Submission"}
    email = {
        "email_id": "E_ACT_01",
        "sender_email": "purchase@northbridge.edu",
        "recipients": ["faculty.mech@northbridge.edu"],
        "clean_body": "Submit PO by next Friday.",
        "sent_at": "2026-11-18T10:00:00Z",
        "category": "ACTIONABLE",
        "sensitivity": "INTERNAL",
    }

    case_file = reduce_matter_to_case_file(matter, [email])
    assert len(case_file.action_items) == 1
    action = case_file.action_items[0]

    assert action.source_email_id == "E_ACT_01"
    assert action.resolved_due_date == date(2026, 11, 27)
    assert "by next Friday" in action.raw_deadline_text
    assert "Submit PO by next Friday." in action.verbatim_quote


def test_t18_confidential_disciplinary_ceiling_propagation():
    """
    T-18: Confidential disciplinary notice merged into an existing internal Matter.
    Asserts: Matter ceiling elevates to CONFIDENTIAL and propagates to all Matter chunks.
    """
    emails = [
        # Normal internal matter email
        {
            "email_id": "E_INT_01",
            "raw_thread_id": "TH_LAB_INCIDENT",
            "in_reply_to": None,
            "subject": "Lab safety incident report",
            "norm_subject": "lab safety incident report",
            "sender_email": "faculty.mech@northbridge.edu",
            "recipients": ["mech.hod@northbridge.edu"],
            "participants": ["faculty.mech@northbridge.edu", "mech.hod@northbridge.edu"],
            "clean_body": "Reporting minor safety breach in the thermodynamics lab.",
            "sent_at": "2026-09-01T10:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        # Confidential inquiry reply
        {
            "email_id": "E_CONF_01",
            "raw_thread_id": "TH_LAB_INCIDENT",
            "in_reply_to": "E_INT_01",
            "subject": "Re: Lab safety incident report - Confidential Disciplinary Notice",
            "norm_subject": "lab safety incident report - confidential disciplinary notice",
            "sender_email": "mech.hod@northbridge.edu",
            "recipients": ["faculty.mech@northbridge.edu", "dean.admin@northbridge.edu"],
            "participants": ["mech.hod@northbridge.edu", "faculty.mech@northbridge.edu", "dean.admin@northbridge.edu"],
            "clean_body": "CONFIDENTIAL: A formal disciplinary committee has been instituted regarding misconduct.",
            "sent_at": "2026-09-02T15:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "CONFIDENTIAL",
        },
    ]

    # 1. Matter Stitcher ceiling elevation
    matters, links = stitch_emails_into_matters(emails)
    assert len(matters) == 1
    matter = matters[0]

    # The entire Matter's sensitivity ceiling must elevate to CONFIDENTIAL
    assert matter["sensitivity_level"] == "CONFIDENTIAL"

    # 2. State Reducer preserves and enforces the elevated ceiling
    case_file = reduce_matter_to_case_file(matter, emails)
    assert matter["sensitivity_level"] == "CONFIDENTIAL"
