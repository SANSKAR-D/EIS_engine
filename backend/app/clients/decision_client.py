# backend/app/clients/decision_client.py
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.schemas.decision_plane import (
    ChoiceResponse,
    GateATriageRaw,
    GateATriageResponse,
    GateBMergeRaw,
    NoulResponse,
    ScoreResponse,
)

logger = logging.getLogger(__name__)


class TokenRateLimiter:
    """
    Sliding window rate limiter to strictly observe the 50K input tokens per minute quota.
    Buffers safely at max_tpm (default 42,000 TPM) and enforces minimum spacing.
    """
    def __init__(self, max_tpm: int = 42000, window_seconds: float = 60.0):
        self.max_tpm = max_tpm
        self.window_seconds = window_seconds
        self.history: List[Tuple[float, int]] = []
        self.min_interval = 1.0  # minimum seconds between live API calls
        self.last_call_time = 0.0

    def acquire(self, estimated_tokens: int):
        now = time.time()
        # 1. Clean history older than window
        cutoff = now - self.window_seconds
        self.history = [item for item in self.history if item[0] > cutoff]

        # 2. Check token volume
        current_tokens = sum(item[1] for item in self.history)
        if current_tokens + estimated_tokens > self.max_tpm:
            oldest_time = self.history[0][0]
            sleep_needed = (oldest_time + self.window_seconds) - now + 0.5
            if sleep_needed > 0:
                logger.warning(
                    f"50K TPM quota guard: sleeping {sleep_needed:.2f}s "
                    f"(current {current_tokens} tokens + {estimated_tokens} requested)"
                )
                time.sleep(sleep_needed)
                now = time.time()
                self.history = [item for item in self.history if item[0] > (now - self.window_seconds)]

        # 3. Enforce pacing interval
        elapsed = now - self.last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        self.last_call_time = time.time()
        self.history.append((self.last_call_time, estimated_tokens))


# Shared process-level limiter instance
_rate_limiter = TokenRateLimiter(max_tpm=42000)


class DecisionPlaneClient:
    """
    Gate A/B/C/D control plane client.
    Supports live Google GenAI structured JSON calls with TPM guardrails,
    and a deterministic mock provider for isolated unit tests.
    """
    def __init__(
        self,
        use_mock: Optional[bool] = None,
        model_id: Optional[str] = None,
    ):
        if use_mock is not None:
            self.use_mock = use_mock
        else:
            self.use_mock = settings.use_mock_ai or not bool(settings.gemini_api_key)

        self.model_id = model_id or settings.decision_model_id or settings.flash_model_id
        self._genai_client = None

    def _get_client(self):
        if self._genai_client is None:
            from google import genai
            self._genai_client = genai.Client(api_key=settings.gemini_api_key)
        return self._genai_client

    def triage_email(self, payload: Dict[str, Any]) -> GateATriageResponse:
        """
        Executes Gate A Triage:
        - is_spam probability
        - route category: SPAM | ACK_NOISE | FYI_BROADCAST | ACTIONABLE
        - sensitivity: PUBLIC | INTERNAL | CONFIDENTIAL
        - needs_attachment_ocr probability
        - has_decision_or_deadline probability
        - urgency_score (0..4)
        """
        if self.use_mock:
            return self._mock_triage(payload)

        return self._live_triage(payload)

    def _mock_triage(self, payload: Dict[str, Any]) -> GateATriageResponse:
        """Deterministic rule engine for isolated tests (T-08..T-11)."""
        subject = (payload.get("subject") or "").lower()
        sender = (payload.get("sender") or "").lower()
        body = (payload.get("clean_body") or "").strip()
        body_lower = body.lower()

        # T-08: Cold webinar promo / spam (P(spam) = 0.96)
        if any(w in subject or w in body_lower for w in ["webinar", "cold sales", "promo", "limited discount", "sponsored product"]):
            return GateATriageResponse(
                is_spam=NoulResponse(noul=0.96, label="Cold sales / webinar promo"),
                route=ChoiceResponse(choice="SPAM"),
                sensitivity=ChoiceResponse(choice="PUBLIC"),
                needs_attachment_ocr=NoulResponse(noul=0.05),
                has_decision_or_deadline=NoulResponse(noul=0.0),
                urgency_score=ScoreResponse(score=0),
            )

        # T-09: Borderline external workshop (P(spam) = 0.63 -> REVIEW_NEEDED)
        if any(w in subject or w in body_lower for w in ["workshop", "external symposium", "faculty development program", "fwd: call for papers"]):
            return GateATriageResponse(
                is_spam=NoulResponse(noul=0.63, label="Borderline external invitation"),
                route=ChoiceResponse(choice="REVIEW"),
                sensitivity=ChoiceResponse(choice="PUBLIC"),
                needs_attachment_ocr=NoulResponse(noul=0.10),
                has_decision_or_deadline=NoulResponse(noul=0.15),
                urgency_score=ScoreResponse(score=1),
            )

        # T-10: Brief acknowledgment noise (ACK_NOISE)
        ack_phrases = ["noted, thanks sir.", "noted, thanks", "noted", "received, thanks", "thanks sir", "ok noted", "acknowledged"]
        if body_lower in ack_phrases or (len(body_lower) < 25 and any(p in body_lower for p in ["noted", "received", "thanks"])):
            return GateATriageResponse(
                is_spam=NoulResponse(noul=0.01),
                route=ChoiceResponse(choice="ACK_NOISE"),
                sensitivity=ChoiceResponse(choice="INTERNAL"),
                needs_attachment_ocr=NoulResponse(noul=0.0),
                has_decision_or_deadline=NoulResponse(noul=0.0),
                urgency_score=ScoreResponse(score=0),
            )

        # T-11: "PFA" attachment delegation
        is_pfa_stub = body_lower in ["pfa", "pfa.", "please find attached.", "please find attached", "see attached."] or (len(body_lower) <= 15 and "pfa" in body_lower)
        has_excerpt = "[ATTACHMENT_EXCERPT]" in body

        if is_pfa_stub and not has_excerpt:
            # Initial pass: needs attachment OCR before routing
            return GateATriageResponse(
                is_spam=NoulResponse(noul=0.02),
                route=ChoiceResponse(choice="FYI_BROADCAST"),
                sensitivity=ChoiceResponse(choice="INTERNAL"),
                needs_attachment_ocr=NoulResponse(noul=0.88),
                has_decision_or_deadline=NoulResponse(noul=0.10),
                urgency_score=ScoreResponse(score=1),
            )

        if has_excerpt:
            # Re-triage pass with attachment contents appended
            return GateATriageResponse(
                is_spam=NoulResponse(noul=0.02),
                route=ChoiceResponse(choice="ACTIONABLE"),
                sensitivity=ChoiceResponse(choice="INTERNAL"),
                needs_attachment_ocr=NoulResponse(noul=0.05),
                has_decision_or_deadline=NoulResponse(noul=0.88),
                urgency_score=ScoreResponse(score=3),
            )

        # Sensitivity tags
        sensitivity = "INTERNAL"
        if any(w in subject or w in body_lower for w in ["disciplinary", "misconduct", "salary", "confidential", "exam paper"]):
            sensitivity = "CONFIDENTIAL"
        elif any(w in subject for w in ["holiday", "circular", "convocation", "fest"]):
            sensitivity = "PUBLIC"

        # Default legitimate departmental correspondence
        has_decision = 0.85 if any(w in body_lower for w in ["approved", "deadline", "procure", "quotation", "purchase order", "submit"]) else 0.20
        route = "ACTIONABLE" if has_decision >= 0.55 else "FYI_BROADCAST"

        return GateATriageResponse(
            is_spam=NoulResponse(noul=0.03),
            route=ChoiceResponse(choice=route),
            sensitivity=ChoiceResponse(choice=sensitivity),
            needs_attachment_ocr=NoulResponse(noul=0.15),
            has_decision_or_deadline=NoulResponse(noul=has_decision),
            urgency_score=ScoreResponse(score=2),
        )

    def _live_triage(self, payload: Dict[str, Any]) -> GateATriageResponse:
        """Executes live Gate A Gemini inference with strict 50K TPM quota protection."""
        # 1. Truncate payload to avoid quota waste (max 2000 chars body)
        clean_body = (payload.get("clean_body") or "")[:2000]
        prompt = (
            f"Sender: {payload.get('sender', '')}\n"
            f"Recipients: {', '.join(payload.get('recipients', []))}\n"
            f"Subject: {payload.get('subject', '')}\n"
            f"Attachments: {', '.join(payload.get('attachments', []))}\n\n"
            f"Body:\n{clean_body}\n"
        )

        estimated_tokens = max(100, int(len(prompt) / 3.5))
        _rate_limiter.acquire(estimated_tokens)

        from google.genai import types

        client = self._get_client()

        # Retry with backoff for rate limits
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=(
                            "You are Gate A, an institutional email triage classifier. "
                            "Assess is_spam_prob (cold sales/promos), route (SPAM, ACK_NOISE, FYI_BROADCAST, ACTIONABLE), "
                            "sensitivity (PUBLIC, INTERNAL, CONFIDENTIAL), needs_attachment_ocr_prob (body says PFA or delegates to attachment), "
                            "has_decision_prob (approvals, orders, deadlines), and urgency_score (0 to 4)."
                        ),
                        response_mime_type="application/json",
                        response_schema=GateATriageRaw,
                        temperature=0.0,
                    ),
                )
                data = json.loads(response.text)
                return GateATriageResponse(
                    is_spam=NoulResponse(noul=data["is_spam_prob"]),
                    route=ChoiceResponse(choice=data["route"]),
                    sensitivity=ChoiceResponse(choice=data["sensitivity"]),
                    needs_attachment_ocr=NoulResponse(noul=data["needs_attachment_ocr_prob"]),
                    has_decision_or_deadline=NoulResponse(noul=data["has_decision_prob"]),
                    urgency_score=ScoreResponse(score=data["urgency_score"]),
                )
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    backoff = (2 ** attempt) * 2.0
                    logger.warning(f"Live Gemini 429 encountered; backing off {backoff:.1f}s (attempt {attempt+1})")
                    time.sleep(backoff)
                else:
                    logger.error(f"Gate A live inference error: {e}. Falling back to mock heuristics.")
                    return self._mock_triage(payload)

        # Fallback if retries exhausted
        return self._mock_triage(payload)

    def check_matter_merge(self, pair: Dict[str, Any]) -> float:
        """
        Executes Gate B Matter Merge verification:
        Determines probability [0.0, 1.0] that two thread clusters belong
        to the exact same operational or administrative matter.
        """
        if self.use_mock:
            return self._mock_matter_merge(pair)
        return self._live_matter_merge(pair)

    def _mock_matter_merge(self, pair: Dict[str, Any]) -> float:
        """Deterministic Gate B mock verification for T-13 and T-14."""
        ta = pair.get("thread_a", {})
        tb = pair.get("thread_b", {})

        subj_a = (ta.get("subject") or "").lower()
        subj_b = (tb.get("subject") or "").lower()
        body_a = (ta.get("sample_body") or "").lower()
        body_b = (tb.get("sample_body") or "").lower()

        tokens_a = {str(t).lower() for t in ta.get("entity_tokens", [])}
        tokens_b = {str(t).lower() for t in tb.get("entity_tokens", [])}
        shared_tokens = tokens_a.intersection(tokens_b)

        parts_a = {str(p).lower() for p in ta.get("participants", [])}
        parts_b = {str(p).lower() for p in tb.get("participants", [])}
        shared_participants = parts_a.intersection(parts_b)

        # Negative case (T-14): Same HoD / participant, but completely disjoint operational topics
        # e.g. CNC machine purchase vs Convocation schedule / Annual Day / Exam
        disjoint_topics = [
            ("cnc", "convocation"),
            ("procurement", "convocation"),
            ("purchase", "annual day"),
            ("disciplinary", "procurement"),
            ("turning centre", "convocation"),
        ]
        for t1, t2 in disjoint_topics:
            if (t1 in subj_a or t1 in body_a or t1 in tokens_a) and (t2 in subj_b or t2 in body_b or t2 in tokens_b):
                return 0.12
            if (t2 in subj_a or t2 in body_a or t2 in tokens_a) and (t1 in subj_b or t1 in body_b or t1 in tokens_b):
                return 0.12

        # Positive case (T-13): Vendor B CNC quote revision merged into primary CNC matter
        cnc_terms = {"cnc", "turning centre", "vendor b", "vendor_b", "quote", "revised quote"}
        if (tokens_a & cnc_terms or any(w in subj_a for w in ["cnc", "turning centre"])) and (
            tokens_b & cnc_terms or any(w in subj_b for w in ["cnc", "turning centre"])
        ):
            if shared_participants or len(shared_tokens) >= 1:
                return 0.89

        # General entity matching rule
        if len(shared_tokens) >= 2 and len(shared_participants) >= 1:
            return 0.85

        return 0.20

    def _live_matter_merge(self, pair: Dict[str, Any]) -> float:
        """Executes live Gate B Gemini inference with rate limiting."""
        ta = pair.get("thread_a", {})
        tb = pair.get("thread_b", {})

        prompt = (
            "Evaluate if these two administrative email thread clusters belong to the exact same operational matter.\n\n"
            f"Thread A:\nSubject: {ta.get('subject', '')}\nParticipants: {', '.join(ta.get('participants', []))}\n"
            f"Entity Tokens: {', '.join(str(t) for t in ta.get('entity_tokens', []))}\n"
            f"Body Snippet: {(ta.get('sample_body', ''))[:500]}\n\n"
            f"Thread B:\nSubject: {tb.get('subject', '')}\nParticipants: {', '.join(tb.get('participants', []))}\n"
            f"Entity Tokens: {', '.join(str(t) for t in tb.get('entity_tokens', []))}\n"
            f"Body Snippet: {(tb.get('sample_body', ''))[:500]}\n"
        )

        estimated_tokens = max(100, int(len(prompt) / 3.5))
        _rate_limiter.acquire(estimated_tokens)

        from google.genai import types
        client = self._get_client()

        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=(
                            "You are Gate B, a strict cross-thread matter merge verifier for an academic institution. "
                            "Assess whether two threads describe the exact same specific procurement, event, or incident. "
                            "Do NOT merge merely because the same person sent both emails (e.g. HoD sending both a CNC purchase and a Convocation email). "
                            "Output is_same_matter_prob between 0.0 and 1.0."
                        ),
                        response_mime_type="application/json",
                        response_schema=GateBMergeRaw,
                        temperature=0.0,
                    ),
                )
                data = json.loads(response.text)
                return float(data.get("is_same_matter_prob", 0.0))
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    backoff = (2 ** attempt) * 2.0
                    logger.warning(f"Gate B 429 backoff: sleeping {backoff:.1f}s")
                    time.sleep(backoff)
                else:
                    logger.error(f"Gate B live inference error: {e}. Falling back to mock heuristics.")
                    return self._mock_matter_merge(pair)

        return self._mock_matter_merge(pair)

