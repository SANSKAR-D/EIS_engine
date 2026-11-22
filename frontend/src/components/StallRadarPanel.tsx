// frontend/src/components/StallRadarPanel.tsx
import React, { useState, useEffect } from 'react';
import { Radio, AlertOctagon, Clock, Calendar, ArrowRight } from 'lucide-react';
import { type RadarData, type UserRole, fetchRadarData } from '../services/api';

interface StallRadarPanelProps {
  activeRole: UserRole;
}

export const StallRadarPanel: React.FC<StallRadarPanelProps> = ({ activeRole }) => {
  const [radarData, setRadarData] = useState<RadarData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchRadarData(activeRole)
      .then(data => {
        setRadarData(data);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [activeRole]);

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* Header Banner */}
      <div style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-accent)',
        borderRadius: 12,
        padding: 24,
        marginBottom: 24
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Radio size={22} color="#f59e0b" />
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#f8fafc' }}>
              Proactive Administrative Radar &amp; Stalled Sign-Offs
            </h2>
          </div>
          <span style={{
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            background: 'rgba(245, 158, 11, 0.15)',
            color: '#fbbf24',
            padding: '4px 10px',
            borderRadius: 6,
            fontWeight: 600
          }}>
            Threshold: &gt; 5 Days Inactive
          </span>
        </div>
        <p style={{ fontSize: 13, color: '#94a3b8', lineHeight: 1.5 }}>
          Autonomous Layer 2 radar service monitoring institutional bottlenecks: requests awaiting signature beyond threshold, terminal approvals lacking follow-up ERP action, and approaching resolved ISO deadlines.
        </p>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          Polling radar service metrics...
        </div>
      ) : radarData ? (
        <div>
          {/* Stalled Approval Bottlenecks */}
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 12,
            padding: 24,
            marginBottom: 24
          }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: '#f8fafc', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertOctagon size={18} color="#ef4444" />
              Stalled Sign-Offs &amp; Orphaned Approvals ({radarData.stalled_items.length})
            </h3>

            {radarData.stalled_items.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 12, background: 'var(--bg-tertiary)', borderRadius: 8 }}>
                No stalled approvals detected in your authorized operational purview.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {radarData.stalled_items.map(stall => (
                  <div key={stall.stall_id} style={{
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 10,
                    padding: 18
                  }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <span style={{
                            fontSize: 11,
                            fontFamily: 'var(--font-mono)',
                            fontWeight: 700,
                            padding: '2px 8px',
                            borderRadius: 4,
                            background: stall.stalled_type === 'STALLED_APPROVAL' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: stall.stalled_type === 'STALLED_APPROVAL' ? '#f87171' : '#fbbf24',
                            border: `1px solid ${stall.stalled_type === 'STALLED_APPROVAL' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`
                          }}>
                            {stall.stalled_type.replace('_', ' ')}
                          </span>
                          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                            {stall.matter_id}
                          </span>
                          <span style={{
                            fontSize: 10,
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: 4,
                            background: stall.sensitivity_level === 'CONFIDENTIAL' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: stall.sensitivity_level === 'CONFIDENTIAL' ? '#f87171' : '#fbbf24'
                          }}>
                            {stall.sensitivity_level}
                          </span>
                        </div>
                        <h4 style={{ fontSize: 14, fontWeight: 600, color: '#f8fafc' }}>
                          {stall.matter_title}
                        </h4>
                      </div>

                      <div style={{ textAlign: 'right' }}>
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          fontSize: 12,
                          fontFamily: 'var(--font-mono)',
                          color: '#f87171',
                          fontWeight: 700
                        }}>
                          <Clock size={13} />
                          {stall.days_elapsed} days stalled
                        </span>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                          Pending with: <strong>{stall.pending_with_role}</strong>
                        </div>
                      </div>
                    </div>

                    <p style={{ fontSize: 13, color: '#cbd5e1', marginBottom: 12, lineHeight: 1.5 }}>
                      {stall.context_snippet}
                    </p>

                    <div style={{
                      background: 'rgba(59, 130, 246, 0.08)',
                      border: '1px solid rgba(59, 130, 246, 0.25)',
                      borderRadius: 6,
                      padding: '8px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      fontSize: 12,
                      color: '#93c5fd'
                    }}>
                      <ArrowRight size={14} color="#60a5fa" />
                      <span><strong>Recommended Action:</strong> {stall.recommended_action}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Upcoming Resolved Deadlines */}
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 12,
            padding: 24
          }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: '#f8fafc', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Calendar size={18} color="#34d399" />
              Upcoming Resolved Deadlines ({radarData.upcoming_deadlines.length})
            </h3>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '10px 12px' }}>Matter Title</th>
                    <th style={{ padding: '10px 12px' }}>Action Item</th>
                    <th style={{ padding: '10px 12px' }}>Assigned Owner</th>
                    <th style={{ padding: '10px 12px' }}>Resolved Due Date</th>
                    <th style={{ padding: '10px 12px' }}>Countdown</th>
                  </tr>
                </thead>
                <tbody>
                  {radarData.upcoming_deadlines.map(ddl => (
                    <tr key={ddl.deadline_id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '12px 12px', maxWidth: 260 }}>
                        <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: 13, marginBottom: 2 }}>
                          {ddl.matter_title}
                        </div>
                        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                          {ddl.matter_id}
                        </span>
                      </td>

                      <td style={{ padding: '12px 12px', color: '#cbd5e1' }}>
                        {ddl.task_description}
                      </td>

                      <td style={{ padding: '12px 12px', color: '#94a3b8' }}>
                        {ddl.owner}
                      </td>

                      <td style={{ padding: '12px 12px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: '#34d399' }}>
                        {ddl.resolved_due_date}
                      </td>

                      <td style={{ padding: '12px 12px' }}>
                        <span style={{
                          fontSize: 11,
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 700,
                          padding: '3px 8px',
                          borderRadius: 4,
                          background: ddl.days_remaining <= 5 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                          color: ddl.days_remaining <= 5 ? '#f87171' : '#fbbf24'
                        }}>
                          {ddl.days_remaining} days left
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};
