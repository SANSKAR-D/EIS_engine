// frontend/src/components/MatterTimeline.tsx
import React, { useState, useEffect } from 'react';
import { GitBranch, ArrowRight, UserCheck, Calendar } from 'lucide-react';
import { type MatterSummary, type TimelineData, type UserRole, fetchMatters, fetchMatterTimeline } from '../services/api';

interface MatterTimelineProps {
  activeRole: UserRole;
}

export const MatterTimeline: React.FC<MatterTimelineProps> = ({ activeRole }) => {
  const [matters, setMatters] = useState<MatterSummary[]>([]);
  const [selectedMatterId, setSelectedMatterId] = useState<string>('MAT-2026-CNC');
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchMatters(activeRole).then(list => {
      setMatters(list);
      if (list.length > 0 && !list.find(m => m.matter_id === selectedMatterId)) {
        setSelectedMatterId(list[0].matter_id);
      }
    });
  }, [activeRole, selectedMatterId]);

  useEffect(() => {
    if (!selectedMatterId) return;
    setLoading(true);
    fetchMatterTimeline(selectedMatterId, activeRole)
      .then(t => {
        setTimeline(t);
        setLoading(false);
      })
      .catch(() => {
        setTimeline(null);
        setLoading(false);
      });
  }, [selectedMatterId, activeRole]);

  const getDecisionBadge = (type: string, status: string) => {
    if (status === 'SUPERSEDED') {
      return (
        <span style={{
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          background: 'rgba(239, 68, 68, 0.15)',
          color: '#f87171',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          padding: '2px 8px',
          borderRadius: 4
        }}>
          SUPERSEDED
        </span>
      );
    }
    if (type === 'BINDING_APPROVAL') {
      return (
        <span style={{
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          background: 'rgba(16, 185, 129, 0.15)',
          color: '#34d399',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          padding: '2px 8px',
          borderRadius: 4
        }}>
          BINDING APPROVAL
        </span>
      );
    }
    if (type === 'ENDORSEMENT') {
      return (
        <span style={{
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          fontWeight: 700,
          background: 'rgba(168, 85, 247, 0.15)',
          color: '#c084fc',
          border: '1px solid rgba(168, 85, 247, 0.3)',
          padding: '2px 8px',
          borderRadius: 4
        }}>
          ENDORSEMENT
        </span>
      );
    }
    return (
      <span style={{
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        fontWeight: 700,
        background: 'rgba(59, 130, 246, 0.15)',
        color: '#60a5fa',
        border: '1px solid rgba(59, 130, 246, 0.3)',
        padding: '2px 8px',
        borderRadius: 4
      }}>
        PROPOSAL
      </span>
    );
  };

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* Matter Selector Header */}
      <div style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-accent)',
        borderRadius: 12,
        padding: 20,
        marginBottom: 24
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <GitBranch size={20} color="#60a5fa" />
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#f8fafc' }}>
              Matter Decision Evolution Timeline
            </h2>
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Authorized Matters for {activeRole}: <strong>{matters.length}</strong>
          </span>
        </div>

        {/* Matter Pills */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {matters.map(m => {
            const isSelected = m.matter_id === selectedMatterId;
            return (
              <button
                key={m.matter_id}
                onClick={() => setSelectedMatterId(m.matter_id)}
                className="btn-tactile"
                style={{
                  background: isSelected ? 'rgba(59, 130, 246, 0.2)' : 'var(--bg-tertiary)',
                  border: '1px solid',
                  borderColor: isSelected ? '#3b82f6' : 'var(--border-subtle)',
                  borderRadius: 8,
                  padding: '10px 14px',
                  color: isSelected ? '#ffffff' : '#94a3b8',
                  textAlign: 'left'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700 }}>
                    {m.matter_id}
                  </span>
                  <span style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '1px 6px',
                    borderRadius: 4,
                    background: m.sensitivity_level === 'CONFIDENTIAL' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    color: m.sensitivity_level === 'CONFIDENTIAL' ? '#f87171' : '#fbbf24'
                  }}>
                    {m.sensitivity_level}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: isSelected ? '#e2e8f0' : 'var(--text-muted)', maxWidth: 280, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {m.canonical_title}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Matter Details & Timeline */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Loading matter state reducer timeline...
        </div>
      ) : timeline ? (
        <div>
          {/* Matter Summary Card */}
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 12,
            padding: 20,
            marginBottom: 24
          }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: '#f8fafc', marginBottom: 6 }}>
              {timeline.canonical_title}
            </h3>
            <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 14 }}>
              {timeline.summary}
            </p>
            <div style={{ display: 'flex', gap: 12, fontSize: 12, fontFamily: 'var(--font-mono)' }}>
              <span style={{ color: 'var(--text-muted)' }}>
                Matter ID: <strong style={{ color: '#f8fafc' }}>{timeline.matter_id}</strong>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                Classification: <strong style={{ color: '#fbbf24' }}>{timeline.sensitivity_level}</strong>
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                Total Recorded Events: <strong style={{ color: '#34d399' }}>{timeline.decisions.length}</strong>
              </span>
            </div>
          </div>

          {/* Decision Evolution Vertical Feed */}
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 12,
            padding: 24,
            marginBottom: 24
          }}>
            <h4 style={{ fontSize: 14, fontWeight: 700, color: '#f8fafc', marginBottom: 20, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Chronological Decision Supersession Chain
            </h4>

            <div style={{ position: 'relative', paddingLeft: 28 }}>
              {/* Vertical line connecting decisions */}
              <div style={{
                position: 'absolute',
                left: 9,
                top: 14,
                bottom: 14,
                width: 2,
                background: 'var(--border-accent)'
              }} />

              {timeline.decisions.map((dec, idx) => {
                const isSuperseded = dec.status === 'SUPERSEDED';
                return (
                  <div key={idx} style={{ position: 'relative', marginBottom: idx === timeline.decisions.length - 1 ? 0 : 28 }}>
                    {/* Circle Node */}
                    <div style={{
                      position: 'absolute',
                      left: -28,
                      top: 4,
                      width: 18,
                      height: 18,
                      borderRadius: '50%',
                      background: isSuperseded ? '#ef4444' : dec.decision_type === 'BINDING_APPROVAL' ? '#10b981' : '#3b82f6',
                      border: '3px solid var(--bg-secondary)',
                      zIndex: 2
                    }} />

                    {/* Decision Content Box */}
                    <div style={{
                      background: 'var(--bg-tertiary)',
                      border: '1px solid',
                      borderColor: isSuperseded ? 'rgba(239, 68, 68, 0.3)' : 'var(--border-subtle)',
                      borderRadius: 10,
                      padding: 16
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {getDecisionBadge(dec.decision_type, dec.status)}
                          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                            #{dec.source_email_id}
                          </span>
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            • {new Date(dec.decided_at).toLocaleDateString()}
                          </span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#94a3b8' }}>
                          <UserCheck size={14} color="#60a5fa" />
                          <span>{dec.decided_by} ({dec.approver_role})</span>
                        </div>
                      </div>

                      {/* Decision Text with Supersession Strike-through */}
                      <p style={{
                        fontSize: 14,
                        lineHeight: 1.5,
                        color: isSuperseded ? '#94a3b8' : '#f8fafc',
                        marginBottom: 10
                      }} className={isSuperseded ? 'superseded-text' : ''}>
                        {dec.decision_text}
                      </p>

                      {/* Superseded Notification Banner */}
                      {isSuperseded && dec.superseded_by_email && (
                        <div style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          background: 'rgba(239, 68, 68, 0.1)',
                          color: '#f87171',
                          padding: '4px 10px',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          marginBottom: 10,
                          border: '1px solid rgba(239, 68, 68, 0.25)'
                        }}>
                          <ArrowRight size={13} />
                          Superseded by terminal approval email #{dec.superseded_by_email}
                        </div>
                      )}

                      {/* Verbatim Quote from Email */}
                      <div style={{
                        background: 'var(--bg-primary)',
                        padding: '8px 12px',
                        borderRadius: 6,
                        borderLeft: '3px solid #60a5fa',
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                        color: '#cbd5e1'
                      }}>
                        "{dec.verbatim_quote}"
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Action Items with Resolved ISO Deadlines */}
          {timeline.action_items && timeline.action_items.length > 0 && (
            <div style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-accent)',
              borderRadius: 12,
              padding: 20
            }}>
              <h4 style={{ fontSize: 14, fontWeight: 700, color: '#f8fafc', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Calendar size={16} color="#fbbf24" />
                Action Items &amp; Resolved ISO Deadlines
              </h4>

              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '8px 10px' }}>Task Description</th>
                      <th style={{ padding: '8px 10px' }}>Assigned Owner</th>
                      <th style={{ padding: '8px 10px' }}>Raw Expression</th>
                      <th style={{ padding: '8px 10px' }}>Resolved ISO Deadline</th>
                      <th style={{ padding: '8px 10px' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.action_items.map((act, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '10px 10px', color: '#f8fafc', fontWeight: 500 }}>
                          {act.task_description}
                        </td>
                        <td style={{ padding: '10px 10px', color: '#cbd5e1' }}>
                          {act.owner}
                        </td>
                        <td style={{ padding: '10px 10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                          "{act.raw_deadline_text}"
                        </td>
                        <td style={{ padding: '10px 10px', color: '#34d399', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                          {act.resolved_due_date}
                        </td>
                        <td style={{ padding: '10px 10px' }}>
                          <span style={{
                            fontSize: 11,
                            fontFamily: 'var(--font-mono)',
                            background: 'rgba(245, 158, 11, 0.15)',
                            color: '#fbbf24',
                            padding: '2px 8px',
                            borderRadius: 4,
                            fontWeight: 600
                          }}>
                            {act.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          No timeline data available for active credentials.
        </div>
      )}
    </div>
  );
};
