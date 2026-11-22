# backend/app/schemas/decision_plane.py
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class NoulResponse(BaseModel):
    """Calibrated probability output [0.0, 1.0]."""
    noul: float = Field(ge=0.0, le=1.0)
    label: Optional[str] = None


class ChoiceResponse(BaseModel):
    """Categorical discrete choice output."""
    choice: str
    confidence: float = 1.0


class ScoreResponse(BaseModel):
    """Calibrated ordinal score [0..4]."""
    score: int = Field(ge=0, le=4)


class GateATriageResponse(BaseModel):
    """Structured output contract for Gate A Ingestion Triage."""
    is_spam: NoulResponse
    route: ChoiceResponse
    sensitivity: ChoiceResponse
    needs_attachment_ocr: NoulResponse
    has_decision_or_deadline: NoulResponse
    urgency_score: ScoreResponse

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class GateATriageRaw(BaseModel):
    """Structured Pydantic schema for live Gemini JSON mode."""
    is_spam_prob: float = Field(description="Probability between 0.0 and 1.0 that this email is spam or cold promotional", ge=0.0, le=1.0)
    route: Literal["SPAM", "ACK_NOISE", "FYI_BROADCAST", "ACTIONABLE"] = Field(description="Processing tier")
    sensitivity: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL"] = Field(description="Access control sensitivity tier")
    needs_attachment_ocr_prob: float = Field(description="Probability between 0.0 and 1.0 that the body delegates meaning to attachments (e.g. PFA)", ge=0.0, le=1.0)
    has_decision_prob: float = Field(description="Probability between 0.0 and 1.0 that this email contains a decision, approval, action, or deadline", ge=0.0, le=1.0)
    urgency_score: int = Field(ge=0, le=4, description="Urgency from 0 (routine) to 4 (critical)")


class GateBMergeRaw(BaseModel):
    """Structured Pydantic schema for live Gemini Gate B Matter Merge verification."""
    is_same_matter_prob: float = Field(
        description="Probability between 0.0 and 1.0 that both email threads refer to the exact same administrative, procurement, or academic matter",
        ge=0.0,
        le=1.0,
    )
    shared_context_summary: Optional[str] = Field(
        default=None,
        description="Brief explanation of why the two threads should or should not be merged",
    )


class CandidateRelevanceScore(BaseModel):
    candidate_id: str
    relevance_score: int = Field(ge=0, le=4, description="Relevance from 0 (irrelevant) to 4 (direct answer/terminal approval)")
    reason: Optional[str] = None


class GateCRerankRaw(BaseModel):
    """Structured Pydantic schema for live Gemini Gate C Top-20 candidate reranking."""
    scored_candidates: list[CandidateRelevanceScore]


