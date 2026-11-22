# backend/app/pipeline/state_reducer.py
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.clients.decision_client import DecisionPlaneClient
from app.config import settings
from app.pipeline.authority import classify_approval_weight, infer_sender_authority
from app.schemas.case_file import ActionItem, CompiledCaseFile, ConflictAlert, DecisionRecord

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

MONTHS = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

RELATIVE_DEADLINE_PATTERNS = [
    re.compile(r"\bby\s+next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE),
    re.compile(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE),
    re.compile(r"\bby\s+(this\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE),
    re.compile(r"\bby\s+tomorrow\b", re.IGNORECASE),
    re.compile(r"\btomorrow\b", re.IGNORECASE),
    re.compile(r"\b(before|by|on)\s+(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+)?(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+)?(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]


def resolve_relative_date(text: str, base_datetime: datetime) -> Optional[Tuple[str, date]]:
    """
    Resolves relative time expressions into an exact ISO calendar date against base_datetime.
    E.g., Wednesday 2026-11-18 with 'Submit PO by next Friday' -> 2026-11-27.
    Preserves raw matched deadline text verbatim.
    """
    base_date = base_datetime.date()
    base_weekday = base_datetime.weekday()  # Monday = 0 ... Sunday = 6

    # 1. "by next <weekday>" or "next <weekday>"
    m_next = re.search(r"\b(?:by\s+)?next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.IGNORECASE)
    if m_next:
        raw_text = m_next.group(0)
        target_name = m_next.group(1).lower()
        target_wd = WEEKDAYS[target_name]
        days_ahead = (target_wd - base_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7
        # Next week's instance
        resolved = base_date + timedelta(days=days_ahead + 7)
        return raw_text, resolved

    # 2. "by <weekday>" / "this <weekday>"
    m_this = re.search(r"\b(?:by\s+)?(?:this\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.IGNORECASE)
    if m_this:
        raw_text = m_this.group(0)
        target_name = m_this.group(1).lower()
        target_wd = WEEKDAYS[target_name]
        days_ahead = (target_wd - base_weekday) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved = base_date + timedelta(days=days_ahead)
        return raw_text, resolved

    # 3. "tomorrow"
    m_tom = re.search(r"\b(?:by\s+)?tomorrow\b", text, re.IGNORECASE)
    if m_tom:
        return m_tom.group(0), base_date + timedelta(days=1)

    # 4. Explicit date: e.g. "Friday 18 September 2026" or "18 September 2026"
    m_exp = re.search(
        r"\b(?:(?:before|by|on)\s+)?(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+)?(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if m_exp:
        day = int(m_exp.group(1))
        month_name = m_exp.group(2).lower()
        year = int(m_exp.group(3))
        if month_name in MONTHS:
            return m_exp.group(0), date(year, MONTHS[month_name], day)

    # 5. ISO format: "2026-09-18"
    m_iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m_iso:
        return m_iso.group(0), date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))

    return None


def _ensure_dt(val: Any) -> datetime:
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def reduce_matter_to_case_file(
    matter: Dict[str, Any],
    emails: List[Dict[str, Any]],
    decision_client: Optional[DecisionPlaneClient] = None,
) -> CompiledCaseFile:
    """
    Chronological Event-Sourced State Reducer:
    Processes all emails in a Matter sorted by sent_at ASC.
    - Tracks ACTIVE vs SUPERSEDED decisions.
    - Evaluates sender authority rank for BINDING_APPROVAL vs ENDORSEMENT vs PROPOSAL.
    - Resolves relative deadlines into ISO dates.
    - Elevates sensitivity ceiling if confidential items appear.
    """
    sorted_emails = sorted(emails, key=lambda x: _ensure_dt(x.get("sent_at")))
    matter_id = matter.get("matter_id", f"MAT_{sorted_emails[0]['email_id']}")
    canonical_title = matter.get("canonical_title", sorted_emails[0].get("subject", "Official Matter"))

    decisions: List[DecisionRecord] = []
    action_items: List[ActionItem] = []
    conflicts: List[ConflictAlert] = []

    final_decision_str: Optional[str] = None
    approved_by: Optional[str] = None
    approver_role: Optional[str] = None
    approval_email_id: Optional[str] = None

    # Track sensitivity elevation
    has_confidential = any(str(e.get("sensitivity", "")).upper() == "CONFIDENTIAL" for e in sorted_emails)
    if has_confidential:
        matter["sensitivity_level"] = "CONFIDENTIAL"

    for email in sorted_emails:
        eid = email["email_id"]
        sender = email.get("sender_email", "")
        body = email.get("clean_body", "") or email.get("raw_body", "")
        body_lower = body.lower()
        sent_at = _ensure_dt(email.get("sent_at"))

        # 1. Infer Authority
        auth = infer_sender_authority(
            email_address=sender,
            display_name=email.get("display_name"),
            signature=email.get("signature"),
            body=body,
        )
        rank = auth["authority_rank"]
        role = auth["inferred_role"]

        # 2. Decision & Approval Extraction
        # Look for proposals, choices, and approvals
        is_approval = any(w in body_lower for w in ["approved", "approval granted", "go ahead", "sanctioned", "confirmed"])
        is_endorsement = any(w in body_lower for w in ["looks fine", "proceed", "agreed", "recommending"])
        is_proposal = any(w in body_lower for w in ["proposing", "propose", "quotations received", "vendor a", "vendor b", "vendor c"])

        # Check vendor mentions for supersession tracking
        vendor_match = re.search(r"\b(Vendor\s+[A-C]|Option\s+[A-C])\b", body, re.IGNORECASE)

        if is_approval or is_endorsement or is_proposal:
            weight = classify_approval_weight(rank, body)
            target_entity = vendor_match.group(0).title() if vendor_match else "Option"

            # Check if this overrides an earlier decision/proposal
            if weight == "BINDING_APPROVAL" or (is_approval and rank >= 4):
                # HoD / Dean binding approval
                # Mark previous active decisions regarding competing vendors as SUPERSEDED
                for prev_dec in decisions:
                    if prev_dec.status == "ACTIVE" and prev_dec.decision_type in ["PROPOSAL", "ENDORSEMENT", "BINDING_APPROVAL"]:
                        prev_dec.status = "SUPERSEDED"
                        prev_dec.superseded_by_email = eid

                dec_text = f"{target_entity} approved for procurement" if "procure" in canonical_title.lower() or "cnc" in canonical_title.lower() else f"{target_entity} approved"
                final_decision_str = dec_text
                approved_by = sender
                approver_role = role
                approval_email_id = eid

                # Find exact quote
                quote = body.strip()
                for line in body.splitlines():
                    if any(w in line.lower() for w in ["approved", "approval", "go ahead", "sanctioned"]):
                        quote = line.strip()
                        break

                decisions.append(DecisionRecord(
                    matter_id=matter_id,
                    decision_text=dec_text,
                    decision_type="BINDING_APPROVAL",
                    status="ACTIVE",
                    source_email_id=eid,
                    superseded_by_email=None,
                    decided_by=sender,
                    decided_at=sent_at,
                    verbatim_quote=quote,
                ))

            elif weight == "ENDORSEMENT" or is_endorsement:
                quote = body.strip()
                for line in body.splitlines():
                    if any(w in line.lower() for w in ["looks fine", "proceed", "agreed"]):
                        quote = line.strip()
                        break

                decisions.append(DecisionRecord(
                    matter_id=matter_id,
                    decision_text=f"{target_entity} endorsed by {role}",
                    decision_type="ENDORSEMENT",
                    status="ACTIVE",
                    source_email_id=eid,
                    superseded_by_email=None,
                    decided_by=sender,
                    decided_at=sent_at,
                    verbatim_quote=quote,
                ))

            elif is_proposal and vendor_match:
                quote = body.strip()
                for line in body.splitlines():
                    if vendor_match.group(0).lower() in line.lower():
                        quote = line.strip()
                        break

                decisions.append(DecisionRecord(
                    matter_id=matter_id,
                    decision_text=f"{target_entity} proposed",
                    decision_type="PROPOSAL",
                    status="ACTIVE",
                    source_email_id=eid,
                    superseded_by_email=None,
                    decided_by=sender,
                    decided_at=sent_at,
                    verbatim_quote=quote,
                ))

        # 3. Action Items and Deadline Resolution
        # Look for deadline / action markers
        has_action = any(w in body_lower for w in ["submit po", "purchase order", "submit before", "prepare", "by tomorrow", "next friday", "deadline"])
        date_res = resolve_relative_date(body, sent_at)

        if has_action or date_res:
            raw_deadline, resolved_date = date_res if date_res else (None, None)

            # Extract task description and verbatim quote
            task_desc = "Submit Purchase Order"
            verbatim = body.strip()
            for line in body.splitlines():
                if any(w in line.lower() for w in ["submit", "purchase order", "po", "deadline", "by "]):
                    verbatim = line.strip()
                    task_desc = line.strip()
                    break

            action_items.append(ActionItem(
                matter_id=matter_id,
                task_description=task_desc,
                owner=email.get("recipients", [None])[0] if email.get("recipients") else None,
                raw_deadline_text=raw_deadline,
                resolved_due_date=resolved_date,
                status="PENDING",
                source_email_id=eid,
                verbatim_quote=verbatim,
            ))

    # Compile summary and status note
    if final_decision_str:
        summary = f"Matter concluded with final binding approval: {final_decision_str} by {approved_by} ({approver_role})."
        latest_status = "APPROVED"
    elif decisions:
        summary = f"Matter actively under review. Latest proposal/endorsement by {decisions[-1].decided_by}."
        latest_status = "PENDING_ACTION"
    else:
        summary = f"Correspondence on {canonical_title} with {len(sorted_emails)} emails."
        latest_status = "OPEN"

    case_file = CompiledCaseFile(
        matter_id=matter_id,
        canonical_title=canonical_title,
        summary=summary,
        latest_status_note=latest_status,
        final_decision=final_decision_str,
        approved_by=approved_by,
        approver_role=approver_role,
        approval_email_id=approval_email_id,
        decisions=decisions,
        action_items=action_items,
        conflicts_detected=conflicts,
        version=1,
    )

    return case_file
