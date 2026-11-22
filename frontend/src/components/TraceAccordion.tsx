// frontend/src/components/TraceAccordion.tsx
import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Activity, Cpu, CheckCircle, RefreshCw, Clock } from 'lucide-react';
import { type AgentTraceStep } from '../services/api';

interface TraceAccordionProps {
  trace: AgentTraceStep[];
  retriesUsed: number;
  faithfulnessScore: number;
  abstained: boolean;
}

export const TraceAccordion: React.FC<TraceAccordionProps> = ({
  trace,
  retriesUsed,
  faithfulnessScore,
  abstained
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const totalLatencyMs = trace.reduce((acc, step) => acc + step.step_latency_ms, 0);

  const getNodeIcon = (nodeName: string) => {
    switch (nodeName) {
      case 'route_query':
        return <Activity size={14} color="#60a5fa" />;
      case 'investigate':
        return <Cpu size={14} color="#a78bfa" />;
      case 'synthesize':
        return <Activity size={14} color="#34d399" />;
      case 'verify':
        return <CheckCircle size={14} color="#fbbf24" />;
      case 'recorrect':
        return <RefreshCw size={14} color="#f87171" />;
      default:
        return <CheckCircle size={14} color="#34d399" />;
    }
  };

  return (
    <div style={{
      marginTop: 20,
      background: 'var(--bg-tertiary)',
      border: '1px solid var(--border-accent)',
      borderRadius: 10,
      overflow: 'hidden'
    }}>
      {/* Header Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="btn-tactile"
        style={{
          width: '100%',
          padding: '14px 18px',
          background: 'transparent',
          border: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: 'var(--text-primary)',
          textAlign: 'left'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Activity size={16} color="#60a5fa" />
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.02em' }}>
            LangGraph Execution &amp; Self-Correction Trace
          </span>
          <span style={{
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            background: retriesUsed > 0 ? 'rgba(245, 158, 11, 0.15)' : 'rgba(16, 185, 129, 0.15)',
            color: retriesUsed > 0 ? '#fbbf24' : '#34d399',
            padding: '2px 8px',
            borderRadius: 12,
            fontWeight: 600
          }}>
            {retriesUsed > 0 ? `Self-Correction Retries: ${retriesUsed}` : 'Direct Pass'}
          </span>
          {abstained && (
            <span style={{
              fontSize: 11,
              fontFamily: 'var(--font-mono)',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#f87171',
              padding: '2px 8px',
              borderRadius: 12,
              fontWeight: 600
            }}>
              Abstained (RBAC Isolation)
            </span>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <Clock size={12} />
            {totalLatencyMs} ms total
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Faithfulness: <strong style={{ color: '#34d399' }}>{(faithfulnessScore * 100).toFixed(0)}%</strong>
          </span>
          {isOpen ? <ChevronDown size={18} color="var(--text-muted)" /> : <ChevronRight size={18} color="var(--text-muted)" />}
        </div>
      </button>

      {/* Accordion Body */}
      {isOpen && (
        <div style={{
          padding: '16px 20px 20px 20px',
          borderTop: '1px solid var(--border-subtle)',
          background: 'var(--bg-secondary)'
        }}>
          <div style={{ position: 'relative', paddingLeft: 24 }}>
            {/* Vertical timeline line */}
            <div style={{
              position: 'absolute',
              left: 7,
              top: 10,
              bottom: 10,
              width: 2,
              background: 'var(--border-subtle)'
            }} />

            {trace.map((step, idx) => (
              <div key={idx} style={{
                position: 'relative',
                marginBottom: idx === trace.length - 1 ? 0 : 16
              }}>
                {/* Timeline node icon */}
                <div style={{
                  position: 'absolute',
                  left: -24,
                  top: 2,
                  width: 16,
                  height: 16,
                  borderRadius: '50%',
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-accent)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  zIndex: 2
                }}>
                  {getNodeIcon(step.node_name)}
                </div>

                {/* Step Content */}
                <div style={{
                  background: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 8,
                  padding: '10px 14px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        fontSize: 11,
                        fontFamily: 'var(--font-mono)',
                        color: 'var(--text-muted)',
                        fontWeight: 600
                      }}>
                        STEP {step.step_index}
                      </span>
                      <span style={{
                        fontSize: 12,
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 700,
                        color: '#60a5fa'
                      }}>
                        {step.node_name.toUpperCase()}
                      </span>
                      {step.tool_calls.map((tc, tIdx) => (
                        <span key={tIdx} style={{
                          fontSize: 10,
                          fontFamily: 'var(--font-mono)',
                          background: 'rgba(167, 139, 250, 0.15)',
                          color: '#c4b5fd',
                          padding: '1px 6px',
                          borderRadius: 4,
                          border: '1px solid rgba(167, 139, 250, 0.3)'
                        }}>
                          fastmcp::{tc}
                        </span>
                      ))}
                    </div>

                    <span style={{
                      fontSize: 11,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-muted)'
                    }}>
                      {step.step_latency_ms} ms
                    </span>
                  </div>

                  <p style={{ fontSize: 12, color: '#cbd5e1', lineHeight: 1.5 }}>
                    {step.note}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
