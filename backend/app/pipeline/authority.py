# backend/app/pipeline/authority.py
import re
from typing import Any, Dict, Optional

# Role to numeric rank mappings
ROLE_RANKS = {
    "HOD": 5,
    "DEAN": 5,
    "DIRECTOR": 5,
    "REGISTRAR": 5,
    "PURCHASE_OFFICER": 4,
    "FINANCE_CHAIR": 4,
    "FACULTY": 3,
    "COORDINATOR": 3,
    "ADMIN_CLERK": 2,
    "LAB_ASSISTANT": 2,
    "STUDENT": 1,
    "EXTERNAL": 1,
}

APPROVAL_PHRASES = [
    re.compile(r"\b(?:approved|approval\s+granted|sanctioned|go\s+ahead|confirmed|formally\s+approve)\b", re.IGNORECASE),
]

ENDORSEMENT_PHRASES = [
    re.compile(r"\b(?:looks\s+fine|proceed|recommending|support|fine\s+to\s+proceed|agreed|concur)\b", re.IGNORECASE),
]


def infer_sender_authority(
    email_address: str,
    display_name: Optional[str] = None,
    signature: Optional[str] = None,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Infers institutional role and rank (1 to 5) from email headers, address, display name, and signature.
    Rank 5: HoD / Dean / Director / Registrar (Binding administrative sign-off)
    Rank 4: Purchase Officer / Finance Chair (Binding financial/procurement sign-off)
    Rank 3: Faculty / Professor / Lab Coordinator (Proposals & academic reviews)
    Rank 2: Admin Clerk / Lab Assistant / Technician (Administrative endorsements)
    Rank 1: Student / External Vendor (Proposals, bids, notices)
    """
    text_to_scan = f"{email_address} {display_name or ''} {signature or ''} {body or ''}".lower()
    email_lower = (email_address or "").lower()

    # 1. Rank 5 check: HoD, Dean, Registrar, Director
    if any(k in email_lower for k in ["hod", "head", "dean", "director", "registrar"]):
        role = "DEAN" if "dean" in email_lower else "HOD"
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": role,
            "authority_rank": 5,
            "department": _infer_dept(text_to_scan),
            "evidence": f"Address matches executive role keyword in {email_address}",
        }
    if any(re.search(rf"\b{k}\b", text_to_scan) for k in ["head of department", "hod", "dean", "director", "registrar"]):
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "HOD",
            "authority_rank": 5,
            "department": _infer_dept(text_to_scan),
            "evidence": "Signature or title mentions executive post",
        }

    # 2. Rank 4 check: Purchase Officer / Finance
    if any(k in email_lower for k in ["purchase", "finance", "procurement", "bursar"]):
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "PURCHASE_OFFICER",
            "authority_rank": 4,
            "department": "Finance & Purchase",
            "evidence": f"Address matches procurement role in {email_address}",
        }
    if any(re.search(rf"\b{k}\b", text_to_scan) for k in ["purchase officer", "finance chair", "procurement officer", "store officer"]):
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "PURCHASE_OFFICER",
            "authority_rank": 4,
            "department": "Finance & Purchase",
            "evidence": "Signature or body indicates purchase authority",
        }

    # 3. Rank 3 check: Faculty / Professor / Coordinator
    if any(k in email_lower for k in ["faculty", "prof", "professor", "coordinator"]):
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "FACULTY",
            "authority_rank": 3,
            "department": _infer_dept(text_to_scan),
            "evidence": f"Address matches faculty identifier in {email_address}",
        }
    if any(re.search(rf"\b{k}\b", text_to_scan) for k in ["professor", "asst professor", "associate professor", "lab coordinator"]):
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "FACULTY",
            "authority_rank": 3,
            "department": _infer_dept(text_to_scan),
            "evidence": "Signature or text mentions academic designation",
        }

    # 4. Rank 2 check: Admin Clerk / Lab Assistant
    if any(k in email_lower for k in ["lab.assistant", "assistant", "clerk", "technician", "admin"]):
        role = "LAB_ASSISTANT" if "lab" in email_lower or "assistant" in email_lower else "ADMIN_CLERK"
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": role,
            "authority_rank": 2,
            "department": _infer_dept(text_to_scan),
            "evidence": f"Address matches technical or administrative staff in {email_address}",
        }
    if any(re.search(rf"\b{k}\b", text_to_scan) for k in ["lab assistant", "technical assistant", "admin clerk", "clerk"]):
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "LAB_ASSISTANT",
            "authority_rank": 2,
            "department": _infer_dept(text_to_scan),
            "evidence": "Signature or text mentions lab assistant or clerk designation",
        }

    # 5. Rank 1 check: Student / External
    if "student" in email_lower or "scholar" in email_lower:
        return {
            "email_address": email_address,
            "display_name": display_name,
            "inferred_role": "STUDENT",
            "authority_rank": 1,
            "department": _infer_dept(text_to_scan),
            "evidence": "Student address domain",
        }

    # Default external / unknown
    return {
        "email_address": email_address,
        "display_name": display_name,
        "inferred_role": "EXTERNAL",
        "authority_rank": 1,
        "department": None,
        "evidence": "Default external or unregistered sender",
    }


def _infer_dept(text: str) -> Optional[str]:
    if "mech" in text:
        return "Mechanical Engineering"
    if "cse" in text or "computer" in text:
        return "Computer Science & Engineering"
    if "ece" in text or "electronics" in text:
        return "Electronics & Communication"
    if "civil" in text:
        return "Civil Engineering"
    return None


def classify_approval_weight(authority_rank: int, text: str) -> str:
    """
    Determines decision classification:
    - Rank >= 4 with approval phrasing -> BINDING_APPROVAL
    - Rank <= 3 with endorsement or approval phrasing -> ENDORSEMENT
    - Otherwise -> PROPOSAL
    """
    has_approval = any(p.search(text) for p in APPROVAL_PHRASES)
    has_endorsement = any(p.search(text) for p in ENDORSEMENT_PHRASES)

    if authority_rank >= 4 and has_approval:
        return "BINDING_APPROVAL"
    if authority_rank in [2, 3] and (has_approval or has_endorsement):
        return "ENDORSEMENT"
    if authority_rank >= 4 and has_endorsement:
        return "BINDING_APPROVAL"
    return "PROPOSAL"
