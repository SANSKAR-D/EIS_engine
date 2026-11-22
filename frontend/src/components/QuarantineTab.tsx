// frontend/src/components/QuarantineTab.tsx
import React, { useState, useEffect } from 'react';
import { ShieldAlert, CheckCircle, RefreshCw, FileText, ShieldX, Database } from 'lucide-react';
import { type QuarantineItem, type QuarantineMetrics, type UserRole, fetchQuarantineQueue, restoreQuarantinedItem } from '../services/api';

interface QuarantineTabProps {
  activeRole: UserRole;
}

export const QuarantineTab: React.FC<QuarantineTabProps> = ({ activeRole }) => {
  const [items, setItems] = useState<QuarantineItem[]>([]);
  const [metrics, setMetrics] = useState<QuarantineMetrics | null>(null);
  const [forbiddenMessage, setForbiddenMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    setForbiddenMessage(null);
    fetchQuarantineQueue(activeRole)
      .then(res => {
        if ('error' in res) {
          setForbiddenMessage(res.error);
          setItems([]);
          setMetrics(null);
        } else {
          setItems(res.items);
          setMetrics(res.metrics);
        }
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    loadData();
  }, [activeRole]);

  const handleRestore = async (id: string) => {
    try {
      const res = await restoreQuarantinedItem(id, activeRole);
      setActionMessage(res.message);
      // Update local item status
      setItems(prev => prev.map(item => {
        if (item.quarantine_id === id || item.email_id === id) {
          return { ...item, status: 'RESTORED' };
        }
        return item;
      }));
      setTimeout(() => setActionMessage(null), 4000);
    } catch {
      // Error handled
    }
  };

  if (forbiddenMessage) {
    return (
      <div style={{ maxWidth: 800, margin: '40px auto', textAlign: 'center' }}>
        <div style={{
          background: 'rgba(239, 68, 68, 0.08)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 12,
          padding: 32
        }}>
          <ShieldX size={44} color="#f87171" style={{ marginBottom: 16 }} />
          <h3 style={{ fontSize: 18, fontWeight: 700, color: '#f8fafc', marginBottom: 8 }}>
            Administrative Quarantine Review Restricted
          </h3>
          <p style={{ fontSize: 14, color: '#94a3b8', lineHeight: 1.6, maxWidth: 540, margin: '0 auto 16px auto' }}>
            Under institutional pre-retrieval RBAC policy, access to the Gate A Quarantine Review Queue is restricted to administrative principals (<strong>HOD</strong> or <strong>ADMIN_CLERK</strong>).
          </p>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Switch active role to <strong>HOD</strong> or <strong>ADMIN_CLERK</strong> using the top-right role switcher to test administrative override.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* Top Banner / Metrics */}
      {metrics && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 16,
          marginBottom: 24
        }}>
          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 10,
            padding: 16
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>
              Auto-Quarantined
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#f87171' }}>
              {metrics.total_quarantined}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              P(spam) &ge; 0.90 cutoff
            </div>
          </div>

          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 10,
            padding: 16
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>
              Review Needed
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#fbbf24' }}>
              {metrics.review_needed}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              0.50 &le; P(spam) &lt; 0.90
            </div>
          </div>

          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 10,
            padding: 16
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>
              Skip-OCR Pages Saved
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#34d399', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Database size={20} />
              {metrics.estimated_ocr_pages_saved}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              Zero Vision/OCR spend on spam
            </div>
          </div>

          <div style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-accent)',
            borderRadius: 10,
            padding: 16
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>
              Cost Savings
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: '#60a5fa', display: 'flex', alignItems: 'center', gap: 4 }}>
              ${metrics.estimated_cost_saved_usd.toFixed(2)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              Estimated token &amp; compute delta
            </div>
          </div>
        </div>
      )}

      {/* Action Notification */}
      {actionMessage && (
        <div style={{
          background: 'rgba(16, 185, 129, 0.15)',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          color: '#34d399',
          borderRadius: 8,
          padding: '12px 16px',
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 13,
          fontWeight: 600
        }}>
          <CheckCircle size={16} />
          {actionMessage}
        </div>
      )}

      {/* Quarantine Table */}
      <div style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-accent)',
        borderRadius: 12,
        padding: 24
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <ShieldAlert size={20} color="#f87171" />
            <h2 style={{ fontSize: 18, fontWeight: 700, color: '#f8fafc' }}>
              Quarantine &amp; Human Review Queue
            </h2>
          </div>
          <button
            onClick={loadData}
            className="btn-tactile"
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              borderRadius: 6,
              padding: '6px 12px',
              fontSize: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <RefreshCw size={12} />
            Refresh Queue
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            Inspecting Gate A quarantine audit logs...
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                  <th style={{ padding: '10px 12px' }}>Email ID</th>
                  <th style={{ padding: '10px 12px' }}>Sender &amp; Subject</th>
                  <th style={{ padding: '10px 12px' }}>P(Spam)</th>
                  <th style={{ padding: '10px 12px' }}>Tier &amp; Policy</th>
                  <th style={{ padding: '10px 12px' }}>Attachments</th>
                  <th style={{ padding: '10px 12px' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => {
                  const isRestored = item.status === 'RESTORED';
                  return (
                    <tr key={item.quarantine_id} style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      background: isRestored ? 'rgba(16, 185, 129, 0.05)' : 'transparent'
                    }}>
                      <td style={{ padding: '12px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                        {item.email_id}
                      </td>

                      <td style={{ padding: '12px 12px' }}>
                        <div style={{ fontWeight: 600, color: '#f8fafc', marginBottom: 2 }}>
                          {item.subject}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                          {item.sender} • {new Date(item.received_at).toLocaleDateString()}
                        </div>
                      </td>

                      <td style={{ padding: '12px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{
                            width: 60,
                            height: 6,
                            background: 'var(--bg-primary)',
                            borderRadius: 3,
                            overflow: 'hidden'
                          }}>
                            <div style={{
                              width: `${item.spam_probability * 100}%`,
                              height: '100%',
                              background: item.spam_probability >= 0.9 ? '#ef4444' : '#f59e0b'
                            }} />
                          </div>
                          <span style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: 12,
                            fontWeight: 700,
                            color: item.spam_probability >= 0.9 ? '#f87171' : '#fbbf24'
                          }}>
                            {(item.spam_probability * 100).toFixed(0)}%
                          </span>
                        </div>
                      </td>

                      <td style={{ padding: '12px 12px' }}>
                        <div style={{ marginBottom: 4 }}>
                          <span style={{
                            fontSize: 11,
                            fontFamily: 'var(--font-mono)',
                            fontWeight: 700,
                            padding: '2px 8px',
                            borderRadius: 4,
                            background: isRestored ? 'rgba(16, 185, 129, 0.15)' : item.quarantine_tier === 'AUTO_QUARANTINED' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: isRestored ? '#34d399' : item.quarantine_tier === 'AUTO_QUARANTINED' ? '#f87171' : '#fbbf24'
                          }}>
                            {isRestored ? 'RESTORED TO INBOX' : item.quarantine_tier}
                          </span>
                        </div>
                        <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                          {item.skip_ocr_reason}
                        </span>
                      </td>

                      <td style={{ padding: '12px 12px' }}>
                        {item.has_attachments ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#93c5fd' }}>
                            <FileText size={13} />
                            <span>{item.attachment_names.join(', ')}</span>
                          </div>
                        ) : (
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>None</span>
                        )}
                      </td>

                      <td style={{ padding: '12px 12px' }}>
                        {isRestored ? (
                          <span style={{ fontSize: 12, color: '#34d399', display: 'flex', alignItems: 'center', gap: 4, fontWeight: 600 }}>
                            <CheckCircle size={14} />
                            Restored
                          </span>
                        ) : (
                          <button
                            onClick={() => handleRestore(item.quarantine_id)}
                            className="btn-tactile"
                            style={{
                              background: '#2563eb',
                              color: '#ffffff',
                              border: 'none',
                              borderRadius: 6,
                              padding: '6px 12px',
                              fontSize: 12,
                              fontWeight: 600
                            }}
                          >
                            Restore to Inbox
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
