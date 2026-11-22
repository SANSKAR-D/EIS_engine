// frontend/src/App.tsx
import React, { useState, useEffect } from 'react';
import { Shield, UserCheck } from 'lucide-react';
import { type UserRole, ROLE_PROFILES, checkBackendHealth } from './services/api';
import { QueryWorkbench } from './components/QueryWorkbench';

export const App: React.FC = () => {
  const [activeRole, setActiveRole] = useState<UserRole>('HOD');
  const [backendStatus, setBackendStatus] = useState<string>('checking');

  useEffect(() => {
    checkBackendHealth().then(status => {
      setBackendStatus(status.status);
    });
  }, []);

  const currentProfile = ROLE_PROFILES[activeRole];

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Global Institutional Header */}
      <header style={{
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-accent)',
        padding: '14px 28px',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        backdropFilter: 'blur(8px)'
      }}>
        <div style={{
          maxWidth: 1300,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 16
        }}>
          {/* Logo & System Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #1e3a8a, #3b82f6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 15px rgba(59, 130, 246, 0.3)'
            }}>
              <Shield size={20} color="#ffffff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h1 style={{ fontSize: 16, fontWeight: 700, color: '#f8fafc', letterSpacing: '-0.01em' }}>
                  Institutional Email Intelligence System
                </h1>
                <span style={{
                  fontSize: 10,
                  fontFamily: 'var(--font-mono)',
                  background: 'rgba(59, 130, 246, 0.15)',
                  color: '#60a5fa',
                  padding: '1px 6px',
                  borderRadius: 4,
                  fontWeight: 700,
                  border: '1px solid rgba(59, 130, 246, 0.25)'
                }}>
                  COCKPIT v1.0
                </span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Verifiable Q&amp;A Workbench • FastMCP Boundary • Pre-Retrieval RBAC
              </p>
            </div>
          </div>

          {/* System Health Badge & Live Role Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Health Indicator */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: 'var(--bg-tertiary)',
              padding: '6px 12px',
              borderRadius: 8,
              border: '1px solid var(--border-subtle)',
              fontSize: 12,
              fontFamily: 'var(--font-mono)'
            }}>
              <div style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: backendStatus === 'healthy' ? '#10b981' : '#38bdf8',
                boxShadow: `0 0 8px ${backendStatus === 'healthy' ? '#10b981' : '#38bdf8'}`
              }} />
              <span style={{ color: 'var(--text-secondary)' }}>
                {backendStatus === 'healthy' ? 'L3 LangGraph Live' : 'Connected to Backend'}
              </span>
            </div>

            {/* Live Role Switcher Dropdown */}
            <div style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-accent)',
              borderRadius: 8,
              padding: '4px 10px',
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}>
              <UserCheck size={16} color="#60a5fa" />
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
                  Active Principal Role:
                </span>
                <select
                  value={activeRole}
                  onChange={e => setActiveRole(e.target.value as UserRole)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#f8fafc',
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: 'pointer',
                    outline: 'none',
                    paddingRight: 10
                  }}
                >
                  <option value="HOD" style={{ background: '#10121a' }}>
                    HOD (Prof. A. K. Sharma • Full Clearance)
                  </option>
                  <option value="FACULTY" style={{ background: '#10121a' }}>
                    FACULTY (Dr. S. Verma • Internal / Lab Incharge)
                  </option>
                  <option value="ADMIN_CLERK" style={{ background: '#10121a' }}>
                    ADMIN CLERK (Shri M. Rawat • Purchase Operations)
                  </option>
                  <option value="STUDENT" style={{ background: '#10121a' }}>
                    STUDENT (Rohan Mehta • Public Notices Only)
                  </option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Role Clearance Banner */}
      <div style={{
        background: 'var(--bg-tertiary)',
        borderBottom: '1px solid var(--border-subtle)',
        padding: '8px 28px',
        fontSize: 12
      }}>
        <div style={{
          maxWidth: 1300,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: 'var(--text-secondary)'
        }}>
          <div>
            Logged in as: <strong style={{ color: '#f8fafc' }}>{currentProfile.name}</strong> ({currentProfile.title})
            <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>&lt;{currentProfile.email}&gt;</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: 'var(--text-muted)' }}>RBAC Security Clearance:</span>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 4,
              background: activeRole === 'STUDENT' ? 'rgba(59, 130, 246, 0.15)' : 'rgba(16, 185, 129, 0.15)',
              color: activeRole === 'STUDENT' ? '#60a5fa' : '#34d399',
              border: `1px solid ${activeRole === 'STUDENT' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`
            }}>
              {currentProfile.clearance}
            </span>
          </div>
        </div>
      </div>

      {/* Main Verifiable Q&A Workbench */}
      <main style={{ flex: 1, padding: '32px 28px' }}>
        <div style={{ maxWidth: 1300, margin: '0 auto' }}>
          <QueryWorkbench activeRole={activeRole} />
        </div>
      </main>

      {/* Institutional System Footer */}
      <footer style={{
        background: 'var(--bg-secondary)',
        borderTop: '1px solid var(--border-accent)',
        padding: '16px 28px',
        fontSize: 12,
        color: 'var(--text-muted)'
      }}>
        <div style={{
          maxWidth: 1300,
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12
        }}>
          <div>
            Built with <strong>FastMCP</strong>, <strong>LangGraph</strong>, and <strong>React</strong> • Strict RBAC Pre-Retrieval Enforcement
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span>Layer 1: Local Ingestion &amp; RapidOCR</span>
            <span>•</span>
            <span>Layer 2: FastMCP Boundary</span>
            <span>•</span>
            <span>Layer 3: Self-Correcting LangGraph QA</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;
