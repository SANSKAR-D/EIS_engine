# backend/app/pipeline/triage.py
import logging
from typing import Any, Dict, Optional

from app.clients.decision_client import DecisionPlaneClient
from app.clients.ocr_engine import extract_email_attachments
from app.config import settings

logger = logging.getLogger(__name__)


async def triage_and_route_email(
    db: Any,
    email: Dict[str, Any],
    decision_client: DecisionPlaneClient,
    ocr_call_tracker: Optional[list] = None,
) -> str:
    """
    Executes Gate A Ingestion Router & PFA Attachment Re-Triage Loop:
    1. Evaluates Gate A (is_spam, route, sensitivity, needs_attachment_ocr, has_decision).
    2. Auto-quarantines P(spam) >= 0.90 (0 OCR calls on junk).
    3. Routes 0.40 <= P(spam) < 0.90 to REVIEW_NEEDED.
    4. For legitimate mail with attachments: extracts OCR if needs_ocr or ACTIONABLE or stub body.
    5. PFA Loop: if needs_ocr and pages found, appends [ATTACHMENT_EXCERPT] and re-runs Gate A.
    6. Updates database tables (quarantine_audit, attachment_pages, emails).
    """
    payload = {
        "sender": email.get("sender_email", ""),
        "recipients": email.get("recipients", []),
        "subject": email.get("subject", ""),
        "clean_body": (email.get("clean_body") or "")[:2000],
        "attachments": [
            a.get("filename", "") for a in email.get("active_attachments", [])
        ],
    }

    ans = decision_client.triage_email(payload)
    spam_p = float(ans["is_spam"].noul)
    needs_ocr = float(ans["needs_attachment_ocr"].noul) >= settings.pfa_ocr_cutoff
    route = ans["route"].choice.upper()
    sensitivity = ans["sensitivity"].choice.upper()
    has_dec_p = float(ans["has_decision_or_deadline"].noul)
    urgency = int(ans["urgency_score"].score)

    # 1. Auto-quarantine high-confidence spam (P(spam) >= 0.90) - zero OCR calls
    if spam_p >= settings.spam_quarantine_cutoff:
        if db is not None:
            await db.mark_quarantined(
                email_id=email["email_id"],
                spam_probability=spam_p,
                status="AUTO_QUARANTINED",
                reason_summary="High-confidence spam detected",
            )
        return "SPAM"

    # 2. Human review needed for borderline spam (0.40 - 0.90)
    if spam_p >= settings.spam_review_cutoff:
        if db is not None:
            await db.mark_quarantined(
                email_id=email["email_id"],
                spam_probability=spam_p,
                status="REVIEW_NEEDED",
                reason_summary="Borderline spam score requires administrative review",
            )
        return "REVIEW"

    # 3. Process attachments for legitimate emails if active attachments exist
    extracted_pages = []
    active_attachments = email.get("active_attachments", [])
    # Non-spam emails with attachments are extracted (SPAM gets zero OCR)
    if active_attachments and route != "SPAM":
        if ocr_call_tracker is not None:
            ocr_call_tracker.append(email["email_id"])

        extracted_pages = await extract_email_attachments(
            email_id=email["email_id"],
            active_attachments=active_attachments,
            allow_vision=(route == "ACTIONABLE"),
        )
        if db is not None and extracted_pages:
            await db.upsert_attachment_pages(extracted_pages)

        # 4. PFA Re-Triage Loop when body delegated its meaning to attachment
        if needs_ocr and extracted_pages:
            combined_excerpt = "\n".join(p.extracted_text for p in extracted_pages)[:1500]
            email["attachment_text"] = combined_excerpt
            email["clean_body"] = (
                f"{email.get('clean_body', '')}\n\n[ATTACHMENT_EXCERPT]\n{combined_excerpt}"
            )
            payload["clean_body"] = email["clean_body"]
            re_ans = decision_client.triage_email(payload)
            route = re_ans["route"].choice.upper()
            sensitivity = re_ans["sensitivity"].choice.upper()
            has_dec_p = float(re_ans["has_decision_or_deadline"].noul)
            urgency = max(urgency, int(re_ans["urgency_score"].score))

    # Promote to ACTIONABLE if decision / approval probability is high
    if has_dec_p >= settings.decision_promote_cutoff:
        route = "ACTIONABLE"

    if db is not None:
        await db.update_email_triage(
            email_id=email["email_id"],
            category=route,
            spam_p=spam_p,
            sensitivity=sensitivity,
            has_decision=has_dec_p,
            urgency=urgency,
            meta={"needs_ocr": needs_ocr, "extracted_pages_count": len(extracted_pages)},
        )

    return route
