# backend/app/pipeline/stitcher.py
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.clients.decision_client import DecisionPlaneClient
from app.config import settings

# Sensitivity priority hierarchy
SENSITIVITY_RANKS = {
    "CONFIDENTIAL": 3,
    "INTERNAL": 2,
    "PUBLIC": 1,
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "to", "for", "in", "on", "at", "by", "from",
    "with", "is", "was", "are", "were", "be", "been", "this", "that", "it",
    "please", "thanks", "regards", "dear", "sir", "madam", "subject", "re",
    "fwd", "fw", "attached", "pfa", "meeting", "update", "note", "noted",
}

ENTITY_PATTERN = re.compile(
    r"\b(?:CNC|PO|GeM|INR|Lakh|Lakhs|Quotation|Vendor|Vendor_[A-Z]|Vendor\s+[A-Z]|Turning\s+Centre|Turning\s+Center|[A-Z][a-zA-Z0-9_-]+|\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)


def extract_entity_tokens(email: Dict[str, Any]) -> Set[str]:
    """
    Extracts lightweight entity tokens:
    - Capitalized nouns/codes (e.g. CNC, Turning Centre, Vendor B)
    - Monetary terms & equipment identifiers
    - Incorporates attachment filenames and excerpts
    - Preserves case-normalized tokens while stripping common stop words
    """
    att_names = " ".join(email.get("attachment_names", []))
    att_text = email.get("attachment_text", "")
    text = f"{email.get('subject', '')} {email.get('clean_body', '')} {att_names} {att_text}"
    matches = ENTITY_PATTERN.findall(text)
    tokens: Set[str] = set()
    for m in matches:
        token = m.strip().lower()
        if len(token) > 1 and token not in STOP_WORDS and not token.isdigit():
            tokens.add(token)
        elif token.isdigit() and len(token) >= 2:
            tokens.add(token)

    # Normalize specific multi-word tokens
    text_lower = text.lower()
    if "turning centre" in text_lower or "turning center" in text_lower:
        tokens.add("turning centre")
    if "vendor b" in text_lower or "vendor_b" in text_lower:
        tokens.add("vendor b")
    if "vendor a" in text_lower or "vendor_a" in text_lower:
        tokens.add("vendor a")
    if "vendor c" in text_lower or "vendor_c" in text_lower:
        tokens.add("vendor c")

    return tokens


def _ensure_datetime(val: Any) -> datetime:
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


class UnionFind:
    def __init__(self, elements: List[str]):
        self.parent = {el: el for el in elements}
        self.rank = {el: 0 for el in elements}

    def find(self, i: str) -> str:
        if self.parent[i] != i:
            self.parent[i] = self.find(self.parent[i])
        return self.parent[i]

    def union(self, i: str, j: str) -> bool:
        root_i = self.find(i)
        root_j = self.find(j)
        if root_i == root_j:
            return False
        if self.rank[root_i] < self.rank[root_j]:
            self.parent[root_i] = root_j
        elif self.rank[root_i] > self.rank[root_j]:
            self.parent[root_j] = root_i
        else:
            self.parent[root_j] = root_i
            self.rank[root_i] += 1
        return True


def stitch_emails_into_matters(
    emails: List[Dict[str, Any]],
    decision_client: Optional[DecisionPlaneClient] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Two-stage Matter Stitcher:
    - Pass A: Deterministic Union-Find over in_reply_to, thread_id, and norm_subject (within 30 days).
    - Pass B: Candidate pair generation (shared >=1 participant, >=2 entity tokens, within 45 days)
              verified via Gate B (check_matter_merge).
    - ACL Ceiling & Participant Union calculation.

    Returns:
        (matters, matter_emails_links)
    """
    if not emails:
        return [], []

    # Filter out quarantined SPAM emails from matter clustering
    active_emails = [e for e in emails if e.get("category") != "SPAM"]
    if not active_emails:
        return [], []

    email_map = {e["email_id"]: e for e in active_emails}
    email_ids = list(email_map.keys())

    uf = UnionFind(email_ids)
    email_link_methods: Dict[str, Tuple[str, float]] = {eid: ("THREAD_ID", 1.0) for eid in email_ids}

    # =========================================================================
    # PASS A: Deterministic Thread Clustering
    # =========================================================================
    # 1. in_reply_to linking
    for e in active_emails:
        eid = e["email_id"]
        in_reply = e.get("in_reply_to")
        if in_reply and in_reply in email_map:
            if uf.union(eid, in_reply):
                email_link_methods[eid] = ("IN_REPLY_TO", 1.0)

    # 2. raw_thread_id linking
    thread_to_emails: Dict[str, List[str]] = {}
    for e in active_emails:
        tid = e.get("raw_thread_id")
        if tid:
            thread_to_emails.setdefault(tid, []).append(e["email_id"])

    for tid, members in thread_to_emails.items():
        first = members[0]
        for m in members[1:]:
            if uf.union(first, m):
                email_link_methods[m] = ("THREAD_ID", 1.0)

    # 3. Normalized subject matching within 30-day temporal window
    subject_to_emails: Dict[str, List[Dict[str, Any]]] = {}
    for e in active_emails:
        norm_subj = e.get("norm_subject", "").strip().lower()
        if norm_subj:
            subject_to_emails.setdefault(norm_subj, []).append(e)

    for norm_subj, subj_emails in subject_to_emails.items():
        if len(subj_emails) < 2:
            continue
        for i in range(len(subj_emails)):
            for j in range(i + 1, len(subj_emails)):
                e1 = subj_emails[i]
                e2 = subj_emails[j]
                d1 = _ensure_datetime(e1.get("sent_at"))
                d2 = _ensure_datetime(e2.get("sent_at"))
                if abs((d1 - d2).days) <= 30:
                    if uf.union(e1["email_id"], e2["email_id"]):
                        email_link_methods[e2["email_id"]] = ("SUBJECT", 1.0)

    # Group Pass A clusters
    pass_a_clusters: Dict[str, List[Dict[str, Any]]] = {}
    for eid in email_ids:
        root = uf.find(eid)
        pass_a_clusters.setdefault(root, []).append(email_map[eid])

    # =========================================================================
    # PASS B: Cross-Thread Candidate Pairing & Gate B Verification
    # =========================================================================
    if decision_client is None:
        decision_client = DecisionPlaneClient()

    cluster_roots = list(pass_a_clusters.keys())
    cluster_meta: Dict[str, Dict[str, Any]] = {}

    for root in cluster_roots:
        cluster_emails = pass_a_clusters[root]
        participants: Set[str] = set()
        entity_tokens: Set[str] = set()
        dates: List[datetime] = []

        for e in cluster_emails:
            for p in e.get("participants", []):
                participants.add(p.lower().strip())
            if e.get("sender_email"):
                participants.add(e["sender_email"].lower().strip())
            for r in e.get("recipients", []):
                participants.add(r.lower().strip())

            entity_tokens.update(extract_entity_tokens(e))
            dates.append(_ensure_datetime(e.get("sent_at")))

        # Chronological sort of emails
        sorted_emails = sorted(cluster_emails, key=lambda x: _ensure_datetime(x.get("sent_at")))

        cluster_meta[root] = {
            "root": root,
            "emails": sorted_emails,
            "participants": participants,
            "entity_tokens": entity_tokens,
            "earliest_date": min(dates) if dates else datetime.now(timezone.utc),
            "latest_date": max(dates) if dates else datetime.now(timezone.utc),
            "primary_subject": sorted_emails[0].get("subject", ""),
            "sample_body": sorted_emails[0].get("clean_body", "")[:500],
        }

    # Evaluate candidate pairs
    for i in range(len(cluster_roots)):
        for j in range(i + 1, len(cluster_roots)):
            r1 = cluster_roots[i]
            r2 = cluster_roots[j]
            current_root_1 = uf.find(r1)
            current_root_2 = uf.find(r2)
            if current_root_1 == current_root_2:
                continue

            c1 = cluster_meta[r1]
            c2 = cluster_meta[r2]

            # 1. Temporal proximity: within 45 days
            day_diff = abs((c1["earliest_date"] - c2["latest_date"]).days)
            if day_diff > 45:
                continue

            # 2. Shared participants: >= 1
            shared_parts = c1["participants"].intersection(c2["participants"])
            if not shared_parts:
                continue

            # 3. Shared entity tokens: >= 2
            shared_entities = c1["entity_tokens"].intersection(c2["entity_tokens"])
            if len(shared_entities) < 2:
                continue

            # Candidate pair matches criteria -> Evaluate with Gate B
            pair_payload = {
                "thread_a": {
                    "subject": c1["primary_subject"],
                    "participants": list(c1["participants"]),
                    "entity_tokens": list(c1["entity_tokens"]),
                    "sample_body": c1["sample_body"],
                },
                "thread_b": {
                    "subject": c2["primary_subject"],
                    "participants": list(c2["participants"]),
                    "entity_tokens": list(c2["entity_tokens"]),
                    "sample_body": c2["sample_body"],
                },
            }

            prob = decision_client.check_matter_merge(pair_payload)
            if prob >= settings.matter_merge_cutoff:
                # Merge clusters in Union-Find
                merged = uf.union(current_root_1, current_root_2)
                if merged:
                    new_root = uf.find(current_root_1)
                    # Mark all emails in the secondary cluster as GATE_B_MERGE
                    merged_cluster = c2 if new_root == current_root_1 else c1
                    for me in merged_cluster["emails"]:
                        email_link_methods[me["email_id"]] = ("GATE_B_MERGE", prob)

    # =========================================================================
    # Unified Matter Metadata & ACL Ceiling
    # =========================================================================
    final_matters: Dict[str, List[Dict[str, Any]]] = {}
    for eid in email_ids:
        final_root = uf.find(eid)
        final_matters.setdefault(final_root, []).append(email_map[eid])

    matter_records: List[Dict[str, Any]] = []
    matter_email_links: List[Dict[str, Any]] = []

    for root_id, m_emails in final_matters.items():
        sorted_m_emails = sorted(m_emails, key=lambda x: _ensure_datetime(x.get("sent_at")))
        earliest_email = sorted_m_emails[0]

        # Matter ID: format MAT_<earliest_email_id>
        matter_id = f"MAT_{earliest_email['email_id']}"

        # Canonical title: normalized title of root email
        canonical_title = earliest_email.get("subject", "").strip()
        # Clean Re: / Fwd: prefixes
        canonical_title = re.sub(r"^(?:(?:re|fwd|fw)\s*:\s*)+", "", canonical_title, flags=re.IGNORECASE).strip()

        # ACL Sensitivity Ceiling: CONFIDENTIAL (3) > INTERNAL (2) > PUBLIC (1)
        max_sens_rank = 1
        for e in sorted_m_emails:
            sens = str(e.get("sensitivity", "INTERNAL")).upper()
            rank = SENSITIVITY_RANKS.get(sens, 2)
            if rank > max_sens_rank:
                max_sens_rank = rank

        final_sensitivity = "PUBLIC"
        if max_sens_rank == 3:
            final_sensitivity = "CONFIDENTIAL"
        elif max_sens_rank == 2:
            final_sensitivity = "INTERNAL"

        # Participant union
        all_participants: Set[str] = set()
        for e in sorted_m_emails:
            for p in e.get("participants", []):
                all_participants.add(p.lower().strip())
            if e.get("sender_email"):
                all_participants.add(e["sender_email"].lower().strip())
            for r in e.get("recipients", []):
                all_participants.add(r.lower().strip())

        dates = [_ensure_datetime(e.get("sent_at")) for e in sorted_m_emails]
        urgencies = [int(e.get("urgency_score", 0) or 0) for e in sorted_m_emails]

        matter_record = {
            "matter_id": matter_id,
            "canonical_title": canonical_title,
            "topic_domain": "PROCUREMENT" if "cnc" in canonical_title.lower() or "procure" in canonical_title.lower() else "ADMIN",
            "sensitivity_level": final_sensitivity,
            "allowed_participants": sorted(list(all_participants)),
            "first_email_at": min(dates),
            "last_email_at": max(dates),
            "email_count": len(sorted_m_emails),
            "max_urgency": max(urgencies) if urgencies else 0,
            "status": "OPEN",
        }
        matter_records.append(matter_record)

        for e in sorted_m_emails:
            eid = e["email_id"]
            method, conf = email_link_methods.get(eid, ("THREAD_ID", 1.0))
            matter_email_links.append({
                "matter_id": matter_id,
                "email_id": eid,
                "link_method": method,
                "merge_confidence": conf,
            })

    return matter_records, matter_email_links
