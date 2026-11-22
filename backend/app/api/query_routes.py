# backend/app/api/query_routes.py
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["Query"])


class SourceCitation(BaseModel):
    email_id: str
    attachment_filename: Optional[str] = None
    attachment_page: Optional[int] = None
    verbatim_quote: str
    substring_verified: bool = True


class ClaimItem(BaseModel):
    claim_text: str
    sources: List[SourceCitation]
    entailment_score: float = Field(ge=0.0, le=1.0)
    verified: bool = True


class AgentTraceStep(BaseModel):
    step_index: int
    node_name: str
    tool_calls: List[str] = Field(default_factory=list)
    note: str
    step_latency_ms: int


class QueryRequest(BaseModel):
    query: str
    active_role: Optional[str] = None
    role: Optional[str] = None
    user_email: Optional[str] = None


class RAGAnswerPayload(BaseModel):
    query: str
    query_mode: str = "RAG_INVESTIGATION"
    abstained: bool = False
    summary: str
    final_decision: Optional[str] = None
    approved_by: Optional[str] = None
    pending_actions: List[str] = Field(default_factory=list)
    claims: List[ClaimItem] = Field(default_factory=list)
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list)
    source_email_ids: List[str] = Field(default_factory=list)
    retries_used: int = 0
    faithfulness_score: float = 1.0
    agent_trace: List[AgentTraceStep] = Field(default_factory=list)


CANONICAL_AUTHORIZED_RESPONSE = RAGAnswerPayload(
    query="What happened with the CNC machine procurement?",
    query_mode="RAG_INVESTIGATION",
    abstained=False,
    summary="The department reviewed comparative quotations from three vendors (A, B, and C) for the CNC machine procurement. Following technical evaluation, Option B was officially sanctioned.",
    final_decision="Vendor B selected at approved cost of INR 14,80,000.",
    approved_by="Prof. A. K. Sharma (Head of Department)",
    pending_actions=[
        "Administrative clerk to initiate formal Purchase Order (PO) generation",
        "Finance section to verify vendor advance bank guarantee by 2026-12-05"
    ],
    claims=[
        ClaimItem(
            claim_text="Quotations from Vendors A, B, and C were compared in the procurement statement with Vendor B offering lowest conforming spec.",
            sources=[
                SourceCitation(
                    email_id="E102",
                    attachment_filename="Vendor_Comparison.pdf",
                    attachment_page=1,
                    verbatim_quote="Comparative Statement: Vendor A (16.2L), Vendor B (14.8L), and Vendor C (15.5L) quotations evaluated.",
                    substring_verified=True
                )
            ],
            entailment_score=0.96,
            verified=True
        ),
        ClaimItem(
            claim_text="The Head of Department approved Vendor B and requested immediate purchase order generation.",
            sources=[
                SourceCitation(
                    email_id="E111",
                    verbatim_quote="Approved, go ahead with Option B. Please initiate purchase order generation.",
                    substring_verified=True
                )
            ],
            entailment_score=0.98,
            verified=True
        )
    ],
    conflicts_detected=[
        {
            "alert_text": "Vendor A submitted a revised quote post-deadline claiming 14.5L, but was rejected due to tender closure cutoff.",
            "conflict_type": "DEADLINE_CUTOFF",
            "email_ids": ["E102", "E109"]
        }
    ],
    source_email_ids=["E102", "E111"],
    retries_used=1,
    faithfulness_score=1.0,
    agent_trace=[
        AgentTraceStep(step_index=1, node_name="route_query", tool_calls=[], note="Gate Q routed to RAG_INVESTIGATION (actionable matter intent detected)", step_latency_ms=185),
        AgentTraceStep(step_index=2, node_name="investigate", tool_calls=["search_hybrid_with_expansion"], note="Attempt 1: retrieved 6 candidate chunks across matter MAT-2026-CNC", step_latency_ms=420),
        AgentTraceStep(step_index=3, node_name="synthesize", tool_calls=[], note="Synthesized draft answer with 2 claims and initial citations", step_latency_ms=1150),
        AgentTraceStep(step_index=4, node_name="verify", tool_calls=["substring_check", "gate_d_nli"], note="Claim 1 quote verified against Vendor_Comparison.pdf p.1; Claim 2 verified against E111", step_latency_ms=210),
        AgentTraceStep(step_index=5, node_name="recorrect", tool_calls=["inspect_attachment_page"], note="Self-correction loop 1/2: re-checked PDF table span to confirm exact price figure", step_latency_ms=315),
        AgentTraceStep(step_index=6, node_name="conclude", tool_calls=[], note="Gate D passed with entailment score 0.97. High-confidence payload compiled.", step_latency_ms=95)
    ]
)


STUDENT_RESTRICTED_RESPONSE = RAGAnswerPayload(
    query="What happened with the CNC machine procurement?",
    query_mode="RAG_INVESTIGATION",
    abstained=True,
    summary="Access Restricted (RBAC Policy): CNC Machine Procurement records are classified as INTERNAL / CONFIDENTIAL institutional matters. The active role (STUDENT) does not have authorization to view financial quotes, vendor comparative statements, or HoD approval threads.",
    final_decision=None,
    approved_by=None,
    pending_actions=[],
    claims=[],
    conflicts_detected=[],
    source_email_ids=[],
    retries_used=0,
    faithfulness_score=1.0,
    agent_trace=[
        AgentTraceStep(step_index=1, node_name="route_query", tool_calls=[], note="Gate Q classified intent as RAG_INVESTIGATION", step_latency_ms=140),
        AgentTraceStep(step_index=2, node_name="investigate", tool_calls=["search_hybrid_with_expansion"], note="Pre-retrieval RBAC CTE evaluated: Role=STUDENT. Zero matching chunks in PUBLIC scope for MAT-2026-CNC.", step_latency_ms=180),
        AgentTraceStep(step_index=3, node_name="verify", tool_calls=["gate_q_rbac_check"], note="Pre-retrieval RBAC filter returned 0 records. Abstention protocol triggered.", step_latency_ms=45),
        AgentTraceStep(step_index=4, node_name="conclude", tool_calls=[], note="System safely abstained without leaking internal procurement details.", step_latency_ms=25)
    ]
)


@router.post("/query", response_model=RAGAnswerPayload)
async def execute_query(
    req: QueryRequest,
    x_active_role: Optional[str] = Header(default=None),
    x_user_email: Optional[str] = Header(default=None),
):
    """
    Executes LangGraph grounded QA with server-side RBAC enforcement.
    Returns structured claims, verbatim citations, entailment scores, and execution trace.
    """
    from app.agent.qa_graph import run_grounded_qa
    effective_role = (req.active_role or req.role or x_active_role or "HOD").upper().strip()
    effective_email = req.user_email or x_user_email or f"{effective_role.lower()}@institution.edu"

    # Invokes the full 6-node LangGraph StateGraph pipeline
    return await run_grounded_qa(
        query=req.query,
        active_role=effective_role,
        user_email=effective_email,
    )
