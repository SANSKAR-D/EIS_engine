# AI-Powered Official Email Intelligence System

3-Layer Direct-Method Architecture: Dual-Plane Event-Sourced Core + FastMCP Tool Boundary + LangGraph Self-Correction Shell via Native `google-genai` SDK.

## Architecture Overview

```
=============================================================================
LAYER 3: UPPER COVER -- LANGGRAPH SELF-CORRECTION SHELL (ONLINE Q&A ONLY)
=============================================================================
User Query + Active Role (HOD | FACULTY | ADMIN_CLERK | STUDENT)
    │
    ▼
[Node 0: route_query (Gate Q: gemini-decision-1)]
  ├── out_of_scope --------> Safe Refusal Payload
  ├── direct_sql_dashboard -> Call MCP Dashboard Tool -> Return Table
  └── rag_investigation ---> Enter Self-Correction Loop:
        │
        ▼
[Node 1: investigate (Direct google-genai + FastMCP Session)]
  - MCP Tools: search_hybrid_with_expansion, get_matter_timeline,
               inspect_attachment_page, get_raw_email
        │
        ▼
[Node 2: synthesize (Gemini Flash Structured JSON)]
  - Produces Summary, Final Decision, Approver, Pending Actions,
    Conflicts + Atomic Claims with exact [Email #ID / Page] Quotes
        │
        ▼
[Node 3: verify (Deterministic Substring Check + Gate D gemini-decision-1)]
  - Checks every quote exists verbatim in fetched raw text/OCR pages
  - Evaluates K parallel noul entailment checks in 1 decision call
  ├── (Failed claims OR score < 0.70) and retries < 2 ──┐
  │                                                      ▼
  │                                            [Node 4: recorrect]
  │                                              - Diagnose gap
  │                                              - Rewrite query / target page
  │                                              - retries += 1 ──> loop to Node 1
  ▼
[Node 5: finalize_or_abstain]
  - Strip residual unverified claims
  - Abstain if 0 verified claims remain
  - Persist query_audit_logs + agent_loop_traces
        │
        ▼
React Cockpit UI
=============================================================================
                 || In-Memory Client / Streamable HTTP
                 ▼▼
=============================================================================
LAYER 2: MCP BOUNDARY -- FASTMCP SERVER (THIN RBAC-ENFORCED TOOL LAYER)
=============================================================================
Server-Side Injected Context (Hidden from LLM): {db_pool, role, user_email}
Exposed Tools:
  1. search_hybrid_with_expansion(query, limit)
  2. get_matter_timeline(matter_id)
  3. inspect_attachment_page(email_id, filename, page_number)
  4. get_raw_email(email_id)
  5. get_stalled_approvals(days_threshold)
  6. get_quarantine_summary(limit)
=============================================================================
                 || Direct Async Python Service Calls
                 ▼▼
=============================================================================
LAYER 1: CORE DUAL-PLANE ENGINE (OFFLINE INGESTION + UNIFIED POSTGRESQL)
=============================================================================
- Decision Plane (Gate A triage, Gate B stitcher)
- Privacy-First Attachment Plane (PyMuPDF, pdfplumber, RapidOCR)
- Chronological Event-Sourced State Reducer (Case Files)
- Unified PostgreSQL 16 + pgvector HNSW + FTS tsvector
=============================================================================
```

## Mandatory Model & API Disclosure (Rule 1 Compliance)

This system discloses all external and local models, APIs, and components:

1. **External APIs & Cloud Models**:
   - `gemini-decision-1`: Calibrated, zero-output-token control gates (`api_version="v1beta"`, Gate A triage, Gate B stitching, Gate C reranking, Gate D entailment, Gate Q routing).
   - `gemini-2.5-flash`: Structured chronological state reduction and grounded Q&A synthesis.
   - `text-embedding-004`: 768-dimensional dense semantic embeddings.
   - Primary SDK: Native `google-genai >= 3.6.1` directly (zero LangChain wrappers).

2. **Local Processing & Private OCR**:
   - `PyMuPDF (fitz)` & `pdfplumber`: Digital PDF extraction and markdown table preservation.
   - `RapidOCR` (`rapidocr-onnxruntime`): Local CPU ONNX neural OCR for scanned campus circulars and approval letters.
   - Zero external OCR API leakage for routine departmental documents.

3. **Database & Infrastructure**:
   - `PostgreSQL 16` + `pgvector` (HNSW indexing with cosine similarity).
   - Native `tsvector` full-text search with Reciprocal Rank Fusion (RRF, k=60).
   - `FastMCP`: Standardized tool protocol with server-side RBAC injection.
   - `LangGraph`: Typed state machine governing online self-correction.

## Phase 0: Quickstart & Verification

```bash
# 1. Start PostgreSQL 16 + pgvector
docker-compose up -d

# 2. Verify Database Health & Tables
docker exec -it email_intel_pg psql -U intel_user -d email_intel -c "\dt"

# 3. Run Phase 0 Verification Tests
pytest backend/tests/test_phase0_health.py -v
```
