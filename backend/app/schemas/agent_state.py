# backend/app/schemas/agent_state.py
from typing import Any, Dict, List, Optional, TypedDict


class AgentQueryState(TypedDict, total=False):
    query: str
    active_role: str
    user_email: str
    query_mode: str
    retries: int
    evidence_blocks: List[Dict[str, Any]]
    context_sources: Dict[str, str]
    summary: str
    final_decision: Optional[str]
    approved_by: Optional[str]
    pending_actions: List[str]
    claims: List[Dict[str, Any]]
    failed_claims: List[str]
    conflicts_detected: List[Dict[str, Any]]
    faithfulness_score: float
    abstained: bool
    simulate_initial_low_claim: bool
    trace: List[Dict[str, Any]]
    final_payload: Optional[Dict[str, Any]]
