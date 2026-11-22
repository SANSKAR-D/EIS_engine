// frontend/src/components/QueryWorkbench.tsx
import React, { useState } from 'react';
import { Search, Sparkles, CheckCircle, AlertTriangle, UserCheck, Clock, FileText, ArrowRight, ShieldAlert } from 'lucide-react';
import { type RAGAnswerPayload, type SourceCitation, type UserRole, submitGroundedQuery, ROLE_PROFILES } from '../services/api';
import { TraceAccordion } from './TraceAccordion';
import { CitationDrawer } from './CitationDrawer';

interface QueryWorkbenchProps {
  activeRole: UserRole;
}

const PRESET_QUERIES = [
  'What happened with the CNC machine procurement?',
  'What documents are required for a bonafide certificate?',
  'When and where is the AI in Manufacturing seminar?',
  'What caused the Engineering Block network outage and what is the status?',
  'What was the quotation for repairing the UTM machine?',
  'Are there any confidential exam moderation circulars pending?'
];

export const QueryWorkbench: React.FC<QueryWorkbenchProps> = ({ activeRole }) => {
  const [queryInput, setQueryInput] = useState('What happened with the CNC machine procurement?');
  const [loading, setLoading] = useState(false);
  const [answerPayload, setAnswerPayload] = useState<RAGAnswerPayload | null>(null);
  const [activeCitation, setActiveCitation] = useState<SourceCitation | null>(null);

  const handleSearch = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    try {
      const res = await submitGroundedQuery(q, activeRole);
      setAnswerPayload(res);
    } catch {
      // Error handled
    } finally {
      setLoading(false);
    }
  };

  const currentProfile = ROLE_PROFILES[activeRole];

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* Search Header & Query Presets */}
      <div style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-accent)',
        borderRadius: 12,
        padding: 24,
        marginBottom: 24
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Sparkles size={20} color="#60a5fa" />
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#f8fafc' }}>
              Split-Screen Verifiable Q&amp;A Workbench
            </h2>
          </div>
          <div style={{
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            background: 'var(--bg-tertiary)',
            padding: '4px 10px',
            borderRadius: 6,
            color: 'var(--text-secondary)',
            border: '1px solid var(--border-subtle)'
          }}>
            Active Context: <strong style={{ color: '#60a5fa' }}>{activeRole}</strong> ({currentProfile.clearance})
          </div>
        </div>

        {/* Query Input Bar */}
        <form
          onSubmit={e => {
            e.preventDefault();
            handleSearch(queryInput);
          }}
          style={{ display: 'flex', gap: 10, marginBottom: 14 }}
        >
          <div style={{
            flex: 1,
            position: 'relative',
            display: 'flex',
            alignItems: 'center'
          }}>
            <Search size={18} color="var(--text-muted)" style={{ position: 'absolute', left: 14 }} />
            <input
              type="text"
              value={queryInput}
              onChange={e => setQueryInput(e.target.value)}
              placeholder="Ask any institutional governance or procurement question..."
              style={{
                width: '100%',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border-accent)',
                borderRadius: 8,
                padding: '12px 14px 12px 42px',
                color: '#f8fafc',
                fontSize: 14,
                fontFamily: 'inherit',
                outline: 'none'
              }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-tactile"
            style={{
              background: '#2563eb',
              color: '#ffffff',
              border: 'none',
              borderRadius: 8,
              padding: '0 24px',
              fontSize: 14,
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              opacity: loading ? 0.7 : 1
            }}
          >
            {loading ? 'Synthesizing...' : 'Investigate'}
            <ArrowRight size={16} />
          </button>
        </form>

        {/* Quick Canonical Query Presets */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
            Canonical Queries:
          </span>
          {PRESET_QUERIES.map((preset, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setQueryInput(preset);
                handleSearch(preset);
              }}
              className="btn-tactile"
              style={{
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                color: '#94a3b8',
                borderRadius: 6,
                padding: '4px 10px',
                fontSize: 12,
                fontFamily: 'inherit'
              }}
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      {/* Answer Area */}
      {answerPayload ? (
        <div style={{
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-accent)',
          borderRadius: 12,
          padding: 24
        }}>
          {/* Header Status Bar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingBottom: 16,
            marginBottom: 20,
            borderBottom: '1px solid var(--border-subtle)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {answerPayload.abstained ? (
                <ShieldAlert size={20} color="#f87171" />
              ) : (
                <CheckCircle size={20} color="#34d399" />
              )}
              <span style={{
                fontSize: 13,
                fontWeight: 700,
                color: answerPayload.abstained ? '#f87171' : '#34d399',
                fontFamily: 'var(--font-mono)'
              }}>
                {answerPayload.abstained ? 'PRE-RETRIEVAL RBAC ABSTENTION' : 'VERIFIED GROUNDED SYNTHESIS'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>
                Faithfulness: <strong style={{ color: '#34d399' }}>{(answerPayload.faithfulness_score * 100).toFixed(0)}%</strong>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                Sources: <strong style={{ color: '#60a5fa' }}>{answerPayload.source_email_ids.length}</strong>
              </span>
            </div>
          </div>

          {/* Executive Summary */}
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 6 }}>
              Institutional Executive Summary:
            </div>
            <p style={{ fontSize: 15, lineHeight: 1.6, color: '#f1f5f9' }}>
              {answerPayload.summary}
            </p>
          </div>

          {/* Final Decision & Approver Badge (if available) */}
          {answerPayload.final_decision && (
            <div style={{
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 20,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: 12
            }}>
              <div>
                <span style={{ fontSize: 11, color: '#34d399', fontWeight: 700, display: 'block', textTransform: 'uppercase' }}>
                  Binding Terminal Decision:
                </span>
                <span style={{ fontSize: 14, fontWeight: 600, color: '#f8fafc' }}>
                  {answerPayload.final_decision}
                </span>
              </div>
              {answerPayload.approved_by && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#94a3b8' }}>
                  <UserCheck size={16} color="#34d399" />
                  <span>Approved By: <strong style={{ color: '#f1f5f9' }}>{answerPayload.approved_by}</strong></span>
                </div>
              )}
            </div>
          )}

          {/* Pending Action Items */}
          {answerPayload.pending_actions.length > 0 && (
            <div style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 20
            }}>
              <div style={{ fontSize: 11, color: '#fbbf24', fontWeight: 700, textTransform: 'uppercase', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Clock size={14} />
                Open Administrative Actions:
              </div>
              <ul style={{ paddingLeft: 18, fontSize: 13, color: '#cbd5e1', lineHeight: 1.6 }}>
                {answerPayload.pending_actions.map((act, aIdx) => (
                  <li key={aIdx}>{act}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Conflict Alerts */}
          {answerPayload.conflicts_detected.length > 0 && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 8,
              padding: 16,
              marginBottom: 20
            }}>
              <div style={{ fontSize: 11, color: '#f87171', fontWeight: 700, textTransform: 'uppercase', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertTriangle size={14} />
                Contradiction / Conflict Detected Across Thread:
              </div>
              {answerPayload.conflicts_detected.map((c, cIdx) => (
                <p key={cIdx} style={{ fontSize: 13, color: '#fca5a5' }}>
                  {c.alert_text} (Source: {c.email_ids.join(', ')})
                </p>
              ))}
            </div>
          )}

          {/* Grounded Atomic Claims with Clickable Citation Chips */}
          {answerPayload.claims.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 12 }}>
                Grounded Atomic Claims with Verbatim Evidence:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {answerPayload.claims.map((claim, idx) => (
                  <div key={idx} style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 8,
                    padding: 14
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
                      <p style={{ fontSize: 14, color: '#f1f5f9', lineHeight: 1.5 }}>
                        {claim.claim_text}
                      </p>
                      <span style={{
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        background: 'rgba(16, 185, 129, 0.15)',
                        color: '#34d399',
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontWeight: 600,
                        whiteSpace: 'nowrap'
                      }}>
                        NLI Entailment: {(claim.entailment_score * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* Clickable Citation Chips */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Verified Proof:</span>
                      {claim.sources.map((src, sIdx) => (
                        <button
                          key={sIdx}
                          onClick={() => setActiveCitation(src)}
                          className="citation-chip btn-tactile"
                          title="Click to view raw immutable email & yellow verbatim highlight in Citation Drawer"
                        >
                          <FileText size={11} />
                          #{src.email_id}
                          {src.attachment_filename && ` • ${src.attachment_filename} p.${src.attachment_page || 1}`}
                          <span style={{ color: '#60a5fa', marginLeft: 2 }}>→ View Proof</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Self-Correction Trace Accordion */}
          <TraceAccordion
            trace={answerPayload.agent_trace}
            retriesUsed={answerPayload.retries_used}
            faithfulnessScore={answerPayload.faithfulness_score}
            abstained={answerPayload.abstained}
          />
        </div>
      ) : (
        <div style={{
          textAlign: 'center',
          padding: 60,
          background: 'var(--bg-secondary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 12,
          color: 'var(--text-muted)'
        }}>
          Click <strong>Investigate</strong> or select one of the canonical query buttons above to run verifiable RAG synthesis.
        </div>
      )}

      {/* Sliding Citation Drawer */}
      <CitationDrawer
        citation={activeCitation}
        activeRole={activeRole}
        onClose={() => setActiveCitation(null)}
      />
    </div>
  );
};
