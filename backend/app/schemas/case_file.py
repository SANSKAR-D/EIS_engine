# backend/app/schemas/case_file.py
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    """Atomic decision or approval event within a Matter."""
    decision_id: Optional[int] = None
    matter_id: Optional[str] = None
    decision_text: str
    decision_type: Literal["PROPOSAL", "ENDORSEMENT", "BINDING_APPROVAL"]
    status: Literal["ACTIVE", "SUPERSEDED", "REJECTED"] = "ACTIVE"
    source_email_id: str
    superseded_by_email: Optional[str] = None
    decided_by: str
    decided_at: datetime
    verbatim_quote: str


class ActionItem(BaseModel):
    """Pending or completed action item with resolved ISO deadline."""
    action_id: Optional[int] = None
    matter_id: Optional[str] = None
    task_description: str
    owner: Optional[str] = None
    raw_deadline_text: Optional[str] = None
    resolved_due_date: Optional[date] = None
    status: Literal["PENDING", "DONE", "OVERDUE"] = "PENDING"
    source_email_id: str
    verbatim_quote: str


class ConflictAlert(BaseModel):
    """Contradiction or conflicting claim across messages in a Matter."""
    alert_text: str
    conflict_type: str = "VALUE_CONFLICT"
    email_ids: List[str] = Field(default_factory=list)


class CompiledCaseFile(BaseModel):
    """Chronologically compiled case file state for an actionable Matter."""
    matter_id: str
    canonical_title: str
    summary: str
    latest_status_note: str
    final_decision: Optional[str] = None
    approved_by: Optional[str] = None
    approver_role: Optional[str] = None
    approval_email_id: Optional[str] = None
    decisions: List[DecisionRecord] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    conflicts_detected: List[ConflictAlert] = Field(default_factory=list)
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
