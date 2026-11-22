// frontend/src/services/api.ts

export type UserRole = 'HOD' | 'FACULTY' | 'ADMIN_CLERK' | 'STUDENT';

export interface RoleProfile {
  role: UserRole;
  name: string;
  title: string;
  email: string;
  clearance: string;
}

export const ROLE_PROFILES: Record<UserRole, RoleProfile> = {
  HOD: {
    role: 'HOD',
    name: 'Prof. A. K. Sharma',
    title: 'Head of Department (Mechanical)',
    email: 'hod.mech@institution.edu',
    clearance: 'FULL (Public, Internal, Confidential)'
  },
  FACULTY: {
    role: 'FACULTY',
    name: 'Dr. S. Verma',
    title: 'Lab Incharge & Associate Professor',
    email: 'lab.incharge@institution.edu',
    clearance: 'Public, Internal + Participant'
  },
  ADMIN_CLERK: {
    role: 'ADMIN_CLERK',
    name: 'Shri M. Rawat',
    title: 'Senior Purchase Section Clerk',
    email: 'purchase.clerk@institution.edu',
    clearance: 'Public, Internal + PO Workflows'
  },
  STUDENT: {
    role: 'STUDENT',
    name: 'Rohan Mehta',
    title: 'B.Tech Mechanical (Final Year)',
    email: 'student.2023me@institution.edu',
    clearance: 'Public Circulars Only'
  }
};

export interface SourceCitation {
  email_id: string;
  attachment_filename?: string;
  attachment_page?: number;
  verbatim_quote: string;
  substring_verified: boolean;
}

export interface ClaimItem {
  claim_text: string;
  sources: SourceCitation[];
  entailment_score: number;
  verified: boolean;
}

export interface AgentTraceStep {
  step_index: number;
  node_name: string;
  tool_calls: string[];
  note: string;
  step_latency_ms: number;
}

export interface RAGAnswerPayload {
  query: string;
  query_mode: string;
  abstained: boolean;
  summary: string;
  final_decision?: string | null;
  approved_by?: string | null;
  pending_actions: string[];
  claims: ClaimItem[];
  conflicts_detected: Array<{ alert_text: string; conflict_type: string; email_ids: string[] }>;
  source_email_ids: string[];
  retries_used: number;
  faithfulness_score: number;
  agent_trace: AgentTraceStep[];
}

export interface AttachmentPage {
  filename: string;
  page_number: number;
  extraction_method: string;
  has_tables: boolean;
  markdown_table?: string;
  raw_text: string;
}

export interface SourceEmail {
  email_id: string;
  subject: string;
  sender: string;
  sender_authority_rank: number;
  sender_role: string;
  recipients: string[];
  sent_at: string;
  sensitivity_level: string;
  clean_body: string;
  raw_body: string;
  attachments: AttachmentPage[];
}

const API_BASE = 'http://127.0.0.1:8000';

export async function checkBackendHealth(): Promise<{ status: string; phase?: string; mcp_tools?: number }> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Offline
  }
  return { status: 'disconnected', phase: 'Phase 8 - Layer 3 LangGraph' };
}

export async function submitGroundedQuery(
  query: string,
  role: UserRole
): Promise<RAGAnswerPayload> {
  const profile = ROLE_PROFILES[role];
  const res = await fetch(`${API_BASE}/api/v1/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Active-Role': role,
      'X-User-Email': profile.email
    },
    body: JSON.stringify({
      query,
      active_role: role,
      user_email: profile.email
    })
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`API Error (${res.status}): ${errText || res.statusText}`);
  }

  return await res.json();
}

export async function fetchSourceEmail(emailId: string, role: UserRole): Promise<SourceEmail> {
  const profile = ROLE_PROFILES[role];
  const res = await fetch(`${API_BASE}/api/v1/sources/${emailId}`, {
    headers: {
      'X-Active-Role': role,
      'X-User-Email': profile.email
    }
  });

  if (!res.ok) {
    const errJson = await res.json().catch(() => null);
    throw new Error(errJson?.detail || `HTTP ${res.status}: Lacked RBAC clearance to inspect #${emailId}`);
  }

  return await res.json();
}
