-- AI-Powered Official Email Intelligence System
-- 001_schema.sql: Complete PostgreSQL 16 + pgvector + FTS Schema (13 Tables)

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- 1. SENDER AUTHORITY
-- ============================================================================
CREATE TABLE IF NOT EXISTS sender_authority (
    email_address TEXT PRIMARY KEY,
    display_name TEXT,
    inferred_role TEXT NOT NULL DEFAULT 'UNKNOWN',
    -- HOD | DEAN | PURCHASE_OFFICER | FACULTY | CLERK | STUDENT
    authority_rank SMALLINT NOT NULL DEFAULT 1, -- 1 (low) to 5 (binding)
    department TEXT,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 2. EMAILS
-- ============================================================================
CREATE TABLE IF NOT EXISTS emails (
    email_id TEXT PRIMARY KEY,
    raw_thread_id TEXT,
    in_reply_to TEXT,
    sender_email TEXT NOT NULL,
    recipients TEXT[] NOT NULL DEFAULT '{}',
    participants TEXT[] NOT NULL DEFAULT '{}',
    subject TEXT NOT NULL DEFAULT '',
    norm_subject TEXT NOT NULL DEFAULT '',
    sent_at TIMESTAMPTZ NOT NULL,
    raw_body TEXT NOT NULL,
    clean_body TEXT NOT NULL,
    -- Gate A (gemini-decision-1) Triage & RBAC Outputs
    triage_category TEXT NOT NULL DEFAULT 'PENDING',
    -- SPAM | REVIEW | ACK_NOISE | FYI_BROADCAST | ACTIONABLE
    spam_probability REAL,
    sensitivity_level TEXT NOT NULL DEFAULT 'INTERNAL',
    -- PUBLIC | INTERNAL | CONFIDENTIAL
    has_decision_prob REAL,
    needs_ocr_flag BOOLEAN NOT NULL DEFAULT FALSE,
    pfa_retriaged BOOLEAN NOT NULL DEFAULT FALSE,
    urgency_score SMALLINT NOT NULL DEFAULT 0, -- 0 to 4
    triage_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_emails_sent_at ON emails (sent_at ASC);
CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails (raw_thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_reply_to ON emails (in_reply_to);
CREATE INDEX IF NOT EXISTS idx_emails_triage ON emails (triage_category);
CREATE INDEX IF NOT EXISTS idx_emails_sensitivity ON emails (sensitivity_level);
CREATE INDEX IF NOT EXISTS idx_emails_participants ON emails USING GIN (participants);

-- ============================================================================
-- 3. QUARANTINE AUDIT
-- ============================================================================
CREATE TABLE IF NOT EXISTS quarantine_audit (
    audit_id BIGSERIAL PRIMARY KEY,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    spam_probability REAL NOT NULL,
    status TEXT NOT NULL, -- AUTO_QUARANTINED | REVIEW_NEEDED | RESTORED
    reason_summary TEXT,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ
);

-- ============================================================================
-- 4. ATTACHMENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS attachments (
    attachment_id BIGSERIAL PRIMARY KEY,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    sha256_hash TEXT NOT NULL,
    is_skipped_noise BOOLEAN NOT NULL DEFAULT FALSE,
    skip_reason TEXT, -- ICON_TOO_SMALL | DUPLICATE_LOGO | SPAM_PARENT
    page_count INT NOT NULL DEFAULT 0,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (email_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_attachments_email ON attachments (email_id);
CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments (sha256_hash);

-- ============================================================================
-- 5. ATTACHMENT PAGES
-- ============================================================================
CREATE TABLE IF NOT EXISTS attachment_pages (
    page_id BIGSERIAL PRIMARY KEY,
    attachment_id BIGINT NOT NULL REFERENCES attachments(attachment_id) ON DELETE CASCADE,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    page_number INT NOT NULL,
    extraction_method TEXT NOT NULL, -- PDFPLUMBER | RAPIDOCR | GEMINI_VISION
    mean_confidence REAL,
    extracted_text TEXT NOT NULL,
    has_tables BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (attachment_id, page_number)
);

-- ============================================================================
-- 6. MATTERS
-- ============================================================================
CREATE TABLE IF NOT EXISTS matters (
    matter_id TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    topic_domain TEXT, -- PROCUREMENT | EVENT | ACADEMIC | ADMIN | STUDENT
    sensitivity_level TEXT NOT NULL DEFAULT 'INTERNAL',
    allowed_participants TEXT[] NOT NULL DEFAULT '{}',
    first_email_at TIMESTAMPTZ,
    last_email_at TIMESTAMPTZ,
    email_count INT NOT NULL DEFAULT 0,
    max_urgency SMALLINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN',
    -- OPEN | APPROVED | PENDING_ACTION | CLOSED | STALLED
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 7. MATTER EMAILS
-- ============================================================================
CREATE TABLE IF NOT EXISTS matter_emails (
    matter_id TEXT NOT NULL REFERENCES matters(matter_id) ON DELETE CASCADE,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    link_method TEXT NOT NULL, -- THREAD_ID | IN_REPLY_TO | SUBJECT | GATE_B_MERGE
    merge_confidence REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (matter_id, email_id)
);

-- ============================================================================
-- 8. CASE FILES
-- ============================================================================
CREATE TABLE IF NOT EXISTS case_files (
    matter_id TEXT PRIMARY KEY REFERENCES matters(matter_id) ON DELETE CASCADE,
    canonical_title TEXT NOT NULL,
    summary TEXT NOT NULL,
    latest_status_note TEXT NOT NULL,
    final_decision TEXT,
    approved_by TEXT,
    approver_role TEXT,
    approval_email_id TEXT REFERENCES emails(email_id),
    case_file_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 9. DECISIONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS decisions (
    decision_id BIGSERIAL PRIMARY KEY,
    matter_id TEXT NOT NULL REFERENCES matters(matter_id) ON DELETE CASCADE,
    decision_text TEXT NOT NULL,
    decision_type TEXT NOT NULL, -- PROPOSAL | ENDORSEMENT | BINDING_APPROVAL
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | SUPERSEDED | REJECTED
    source_email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    superseded_by_email TEXT REFERENCES emails(email_id),
    decided_by TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL,
    verbatim_quote TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_decisions_matter ON decisions (matter_id);
CREATE INDEX IF NOT EXISTS idx_decisions_type_status ON decisions (decision_type, status);

-- ============================================================================
-- 10. ACTION ITEMS
-- ============================================================================
CREATE TABLE IF NOT EXISTS action_items (
    action_id BIGSERIAL PRIMARY KEY,
    matter_id TEXT NOT NULL REFERENCES matters(matter_id) ON DELETE CASCADE,
    task_description TEXT NOT NULL,
    owner TEXT,
    raw_deadline_text TEXT,
    resolved_due_date DATE,
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING | DONE | OVERDUE
    source_email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    verbatim_quote TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_action_items_matter ON action_items (matter_id);
CREATE INDEX IF NOT EXISTS idx_action_items_due ON action_items (resolved_due_date, status);

-- ============================================================================
-- 11. RETRIEVAL CHUNKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS retrieval_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    matter_id TEXT REFERENCES matters(matter_id) ON DELETE CASCADE,
    email_id TEXT REFERENCES emails(email_id) ON DELETE CASCADE,
    attachment_page_id BIGINT REFERENCES attachment_pages(page_id) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL, -- EMAIL_BODY | ATTACHMENT_PAGE | CASE_SUMMARY
    sensitivity_level TEXT NOT NULL,
    allowed_participants TEXT[] NOT NULL DEFAULT '{}',
    content TEXT NOT NULL,
    embedding vector(3072) NOT NULL,
    tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON retrieval_chunks USING GIN (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_vec ON retrieval_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_chunks_acl ON retrieval_chunks (sensitivity_level);
CREATE INDEX IF NOT EXISTS idx_chunks_parts ON retrieval_chunks USING GIN (allowed_participants);

-- ============================================================================
-- 12. QUERY AUDIT LOGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS query_audit_logs (
    query_id BIGSERIAL PRIMARY KEY,
    active_role TEXT NOT NULL,
    user_email TEXT,
    query_mode TEXT NOT NULL, -- DIRECT_SQL | RAG_INVESTIGATION | OUT_OF_SCOPE
    query_text TEXT NOT NULL,
    retrieved_email_ids TEXT[] NOT NULL DEFAULT '{}',
    verified_claims INT NOT NULL DEFAULT 0,
    dropped_claims INT NOT NULL DEFAULT 0,
    retry_count SMALLINT NOT NULL DEFAULT 0,
    faithfulness_score REAL,
    abstained BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 13. AGENT LOOP TRACES
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_loop_traces (
    trace_id BIGSERIAL PRIMARY KEY,
    query_id BIGINT NOT NULL REFERENCES query_audit_logs(query_id) ON DELETE CASCADE,
    step_index SMALLINT NOT NULL,
    node_name TEXT NOT NULL, -- route | investigate | synthesize | verify | recorrect
    tool_calls_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT,
    step_latency_ms INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
