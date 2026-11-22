# backend/tests/test_triage_and_stitch.py
import pytest
import time
from pathlib import Path
import fitz

from app.clients.decision_client import DecisionPlaneClient, TokenRateLimiter
from app.pipeline.stitcher import extract_entity_tokens, stitch_emails_into_matters
from app.pipeline.triage import triage_and_route_email


class MockDBTracker:
    def __init__(self):
        self.quarantined = []
        self.triaged = []
        self.pages = []

    async def mark_quarantined(self, email_id: str, spam_probability: float, status: str, reason_summary: str = None):
        self.quarantined.append({
            "email_id": email_id,
            "spam_probability": spam_probability,
            "status": status,
            "reason_summary": reason_summary,
        })

    async def update_email_triage(self, email_id: str, category: str, spam_p=None, sensitivity=None, has_decision=None, urgency=None, meta=None):
        self.triaged.append({
            "email_id": email_id,
            "category": category,
            "spam_p": spam_p,
            "sensitivity": sensitivity,
            "has_decision": has_decision,
            "urgency": urgency,
            "meta": meta,
        })

    async def upsert_attachment_pages(self, pages: list):
        self.pages.extend(pages)


@pytest.mark.asyncio
async def test_t08_cold_webinar_quarantine_zero_ocr(tmp_path: Path):
    """
    T-08: Cold vendor webinar promo with mocked P(spam)=0.96 and attached PDF brochure.
    Asserts: Inserted in quarantine_audit (AUTO_QUARANTINED); OCR call count equals 0.
    """
    # Create attached PDF brochure
    pdf_path = tmp_path / "webinar_brochure.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Webinar Brochure: AI in Enterprise Automation")
    doc.save(pdf_path)
    doc.close()

    email = {
        "email_id": "E_SPAM_01",
        "sender_email": "sales@cloudtech-promo.com",
        "recipients": ["mech.hod@northbridge.edu"],
        "subject": "Exclusive Webinar Promo: 50% Off Cloud Solutions",
        "clean_body": "Join our sponsored webinar this Thursday to see our latest cloud tooling.",
        "active_attachments": [
            {"filename": "webinar_brochure.pdf", "file_path": str(pdf_path)}
        ],
    }

    db = MockDBTracker()
    ocr_calls = []
    client = DecisionPlaneClient(use_mock=True)

    route = await triage_and_route_email(
        db=db,
        email=email,
        decision_client=client,
        ocr_call_tracker=ocr_calls,
    )

    # 1. Classified and routed as SPAM
    assert route == "SPAM"

    # 2. Inserted in quarantine_audit as AUTO_QUARANTINED
    assert len(db.quarantined) == 1
    q_entry = db.quarantined[0]
    assert q_entry["email_id"] == "E_SPAM_01"
    assert q_entry["status"] == "AUTO_QUARANTINED"
    assert q_entry["spam_probability"] >= 0.90

    # 3. OCR call count must strictly equal 0 (no OCR spent on cold junk)
    assert len(ocr_calls) == 0
    assert len(db.pages) == 0


@pytest.mark.asyncio
async def test_t09_borderline_workshop_review_needed():
    """
    T-09: Borderline external workshop email with mocked P(spam)=0.63.
    Asserts: Routed to REVIEW_NEEDED in quarantine_audit.
    """
    email = {
        "email_id": "E_REV_01",
        "sender_email": "organizer@external-symposium.org",
        "recipients": ["faculty.mech@northbridge.edu"],
        "subject": "Workshop Invitation: Regional Engineering Faculty Development Program",
        "clean_body": "We invite mechanical faculty members to submit abstracts for the upcoming workshop.",
        "active_attachments": [],
    }

    db = MockDBTracker()
    client = DecisionPlaneClient(use_mock=True)

    route = await triage_and_route_email(
        db=db,
        email=email,
        decision_client=client,
    )

    # 1. Routed to REVIEW tier
    assert route == "REVIEW"

    # 2. Logged into quarantine audit as REVIEW_NEEDED
    assert len(db.quarantined) == 1
    q_entry = db.quarantined[0]
    assert q_entry["email_id"] == "E_REV_01"
    assert q_entry["status"] == "REVIEW_NEEDED"
    assert 0.40 <= q_entry["spam_probability"] < 0.90


@pytest.mark.asyncio
async def test_t10_ack_noise_classification():
    """
    T-10: Reply 'Noted, thanks sir.' classified as ACK_NOISE.
    Asserts: Categorized as ACK_NOISE; 0 rows inserted into retrieval_chunks.
    """
    email = {
        "email_id": "E_ACK_01",
        "sender_email": "lab.assistant@northbridge.edu",
        "recipients": ["mech.hod@northbridge.edu"],
        "subject": "Re: Lab equipment maintenance schedule",
        "clean_body": "Noted, thanks sir.",
        "active_attachments": [],
    }

    db = MockDBTracker()
    client = DecisionPlaneClient(use_mock=True)

    route = await triage_and_route_email(
        db=db,
        email=email,
        decision_client=client,
    )

    # 1. Classified as ACK_NOISE
    assert route == "ACK_NOISE"

    # 2. Must not be quarantined
    assert len(db.quarantined) == 0

    # 3. Logged in triage updates with ACK_NOISE
    assert len(db.triaged) == 1
    assert db.triaged[0]["category"] == "ACK_NOISE"


@pytest.mark.asyncio
async def test_t11_pfa_re_triage_loop(tmp_path: Path):
    """
    T-11: Email body reads only 'PFA.' with attached PDF specifying CNC budget deadline.
    Asserts: needs_ocr_flag=True triggers Plane 2 extraction -> Gate A re-scores as ACTIONABLE.
    """
    # 1. Create attached CNC quotation PDF with explicit decision deadline
    pdf_path = tmp_path / "cnc_budget_note.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 50),
        "Official Mechanical Engineering Note:\n"
        "CNC Turning Centre Budget of INR 17.9 Lakh is approved.\n"
        "Purchase Order must be submitted before Friday 18 September 2026."
    )
    doc.save(pdf_path)
    doc.close()

    email = {
        "email_id": "E_PFA_01",
        "sender_email": "mech.hod@northbridge.edu",
        "recipients": ["purchase@northbridge.edu"],
        "subject": "CNC Turning Centre Procurement",
        "clean_body": "PFA.",
        "active_attachments": [
            {"filename": "cnc_budget_note.pdf", "file_path": str(pdf_path)}
        ],
    }

    db = MockDBTracker()
    ocr_calls = []
    client = DecisionPlaneClient(use_mock=True)

    final_route = await triage_and_route_email(
        db=db,
        email=email,
        decision_client=client,
        ocr_call_tracker=ocr_calls,
    )

    # 1. OCR was triggered because body delegated meaning to attachment ("PFA")
    assert len(ocr_calls) == 1
    assert len(db.pages) == 1
    assert "CNC Turning Centre Budget" in db.pages[0].extracted_text

    # 2. Re-triage loop escalated the category from stub to ACTIONABLE
    assert final_route == "ACTIONABLE"

    # 3. Database updated with final ACTIONABLE category
    assert len(db.triaged) == 1
    assert db.triaged[0]["category"] == "ACTIONABLE"
    assert db.triaged[0]["meta"]["needs_ocr"] is True


def test_token_rate_limiter_guards_50k_quota():
    """Verifies that TokenRateLimiter enforces token budget tracking and respects 50K TPM window."""
    limiter = TokenRateLimiter(max_tpm=1000, window_seconds=2.0)

    # Consume 400 tokens
    limiter.acquire(400)
    assert sum(t[1] for t in limiter.history) == 400

    # Consume another 400 tokens (total 800 <= 1000)
    limiter.acquire(400)
    assert sum(t[1] for t in limiter.history) == 800

    # Requesting 300 more would exceed 1000; limiter will sleep until oldest window expires
    t0 = time.time()
    limiter.acquire(300)
    t1 = time.time()

    # Verified pacing/sleep triggered to prevent quota breach
    assert (t1 - t0) >= 0.5


def test_t12_pass_a_union_find_missing_thread_id():
    """
    T-12: 4 emails linked by in_reply_to where one message has a missing thread_id.
    Asserts: Pass A Union-Find assigns all 4 emails to the same matter_id.
    """
    emails = [
        {
            "email_id": "E101",
            "raw_thread_id": "TH_101",
            "in_reply_to": None,
            "subject": "Lab equipment quotation",
            "norm_subject": "lab equipment quotation",
            "sender_email": "faculty.mech@northbridge.edu",
            "recipients": ["mech.hod@northbridge.edu"],
            "participants": ["faculty.mech@northbridge.edu", "mech.hod@northbridge.edu"],
            "clean_body": "Please find attached quotations for workshop equipment.",
            "sent_at": "2026-09-01T10:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        {
            "email_id": "E102",
            "raw_thread_id": "TH_101",
            "in_reply_to": "E101",
            "subject": "Re: Lab equipment quotation",
            "norm_subject": "lab equipment quotation",
            "sender_email": "mech.hod@northbridge.edu",
            "recipients": ["faculty.mech@northbridge.edu"],
            "participants": ["mech.hod@northbridge.edu", "faculty.mech@northbridge.edu"],
            "clean_body": "Can we negotiate a 5% educational discount?",
            "sent_at": "2026-09-01T11:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        {
            "email_id": "E103",
            "raw_thread_id": None,  # Missing thread_id!
            "in_reply_to": "E102",  # Linked by in_reply_to
            "subject": "Re: Lab equipment quotation",
            "norm_subject": "lab equipment quotation",
            "sender_email": "faculty.mech@northbridge.edu",
            "recipients": ["mech.hod@northbridge.edu"],
            "participants": ["faculty.mech@northbridge.edu", "mech.hod@northbridge.edu"],
            "clean_body": "Vendor agreed to 5% discount on total order.",
            "sent_at": "2026-09-01T14:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        {
            "email_id": "E104",
            "raw_thread_id": "TH_101",
            "in_reply_to": "E103",
            "subject": "Re: Lab equipment quotation",
            "norm_subject": "lab equipment quotation",
            "sender_email": "mech.hod@northbridge.edu",
            "recipients": ["faculty.mech@northbridge.edu"],
            "participants": ["mech.hod@northbridge.edu", "faculty.mech@northbridge.edu"],
            "clean_body": "Approved, please initiate the purchase order.",
            "sent_at": "2026-09-01T16:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
    ]

    client = DecisionPlaneClient(use_mock=True)
    matters, links = stitch_emails_into_matters(emails, decision_client=client)

    # 1. Exactly 1 unified matter created
    assert len(matters) == 1
    matter = matters[0]
    assert matter["email_count"] == 4

    # 2. All 4 emails belong to the exact same matter_id
    linked_eids = {item["email_id"] for item in links if item["matter_id"] == matter["matter_id"]}
    assert linked_eids == {"E101", "E102", "E103", "E104"}


def test_t13_pass_b_gate_b_cross_thread_merge():
    """
    T-13: Separate thread 'Fwd: Vendor B CNC Revised Quote' sharing participants & CNC entity.
    Asserts: Pass B generates candidate pair; Gate B (P=0.89) merges into primary CNC Matter.
    """
    emails = [
        # Primary Thread A: Initial CNC discussion
        {
            "email_id": "E101",
            "raw_thread_id": "TH_CNC_MAIN",
            "in_reply_to": None,
            "subject": "Procurement of CNC Turning Centre",
            "norm_subject": "procurement of cnc turning centre",
            "sender_email": "faculty.mech@northbridge.edu",
            "recipients": ["purchase@northbridge.edu", "mech.hod@northbridge.edu"],
            "participants": ["faculty.mech@northbridge.edu", "purchase@northbridge.edu", "mech.hod@northbridge.edu"],
            "clean_body": "We need to procure a 3-axis CNC Turning Centre for manufacturing lab.",
            "sent_at": "2026-09-10T10:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        {
            "email_id": "E102",
            "raw_thread_id": "TH_CNC_MAIN",
            "in_reply_to": "E101",
            "subject": "Re: Procurement of CNC Turning Centre",
            "norm_subject": "procurement of cnc turning centre",
            "sender_email": "purchase@northbridge.edu",
            "recipients": ["faculty.mech@northbridge.edu", "mech.hod@northbridge.edu"],
            "participants": ["purchase@northbridge.edu", "faculty.mech@northbridge.edu", "mech.hod@northbridge.edu"],
            "clean_body": "Quotations received from Vendor A and Vendor B.",
            "sent_at": "2026-09-11T12:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        # Separate Thread B: Forwarded revised quote from Vendor B (different subject, no reply headers)
        {
            "email_id": "E201",
            "raw_thread_id": "TH_VENDOR_FWD",
            "in_reply_to": None,
            "subject": "Fwd: Vendor B CNC Revised Quote",
            "norm_subject": "vendor b cnc revised quote",
            "sender_email": "purchase@northbridge.edu",
            "recipients": ["mech.hod@northbridge.edu"],
            "participants": ["purchase@northbridge.edu", "mech.hod@northbridge.edu"],
            "clean_body": "Forwarding revised quote from Vendor B for CNC Turning Centre with warranty.",
            "sent_at": "2026-09-15T09:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
    ]

    client = DecisionPlaneClient(use_mock=True)
    matters, links = stitch_emails_into_matters(emails, decision_client=client)

    # 1. Gate B merged both threads into 1 single CNC Matter
    assert len(matters) == 1
    matter = matters[0]
    assert matter["email_count"] == 3

    # 2. E201 was linked via GATE_B_MERGE with confidence >= 0.78
    e201_link = next(item for item in links if item["email_id"] == "E201")
    assert e201_link["link_method"] == "GATE_B_MERGE"
    assert e201_link["merge_confidence"] >= 0.78


def test_t14_gate_b_no_overmerge_unrelated_matters():
    """
    T-14: Two unrelated threads from the same HoD (CNC purchase vs. Convocation schedule).
    Asserts: Gate B returns P < 0.30; Matters remain strictly separate (no over-merging).
    """
    emails = [
        # CNC Machine Procurement Thread
        {
            "email_id": "E_CNC_01",
            "raw_thread_id": "TH_CNC",
            "in_reply_to": None,
            "subject": "CNC Machine Procurement Budget Approval",
            "norm_subject": "cnc machine procurement budget approval",
            "sender_email": "mech.hod@northbridge.edu",
            "recipients": ["dean.admin@northbridge.edu"],
            "participants": ["mech.hod@northbridge.edu", "dean.admin@northbridge.edu"],
            "clean_body": "Seeking administrative sanction of INR 17.9 Lakh for CNC Turning Centre.",
            "sent_at": "2026-09-10T10:00:00Z",
            "category": "ACTIONABLE",
            "sensitivity": "INTERNAL",
        },
        # Convocation Ceremony Thread (also from same HoD, overlapping time window)
        {
            "email_id": "E_CONV_01",
            "raw_thread_id": "TH_CONV",
            "in_reply_to": None,
            "subject": "Annual Convocation Schedule and Chief Guest",
            "norm_subject": "annual convocation schedule and chief guest",
            "sender_email": "mech.hod@northbridge.edu",
            "recipients": ["dean.admin@northbridge.edu"],
            "participants": ["mech.hod@northbridge.edu", "dean.admin@northbridge.edu"],
            "clean_body": "The 18th Annual Convocation schedule has been finalized for December 15.",
            "sent_at": "2026-09-12T14:00:00Z",
            "category": "FYI_BROADCAST",
            "sensitivity": "PUBLIC",
        },
    ]

    client = DecisionPlaneClient(use_mock=True)
    matters, links = stitch_emails_into_matters(emails, decision_client=client)

    # 1. Matters must remain strictly separate (NO over-merging)
    assert len(matters) == 2
    matter_ids = {m["matter_id"] for m in matters}
    assert len(matter_ids) == 2
    assert matters[0]["canonical_title"] != matters[1]["canonical_title"]

