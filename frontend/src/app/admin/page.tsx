'use client';

import { useState, useEffect, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import AuthGuard from '@/components/AuthGuard';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';

interface PendingUser {
  id: number;
  name: string;
  email: string;
  avatar_url: string | null;
  created_at: string;
}

export default function AdminPage() {
  const { user } = useAuth();
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);

  const loadPending = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getPendingUsers();
      setPendingUsers(data);
    } catch {
      // Not admin or API error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  async function handleApprove(userId: number, approved: boolean) {
    try {
      await api.approveUser({ user_id: userId, approved });
      showToast('success', approved ? 'User approved!' : 'User rejected');
      loadPending();
    } catch {
      showToast('error', 'Failed to update user');
    }
  }

  function showToast(type: string, message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3000);
  }

  if (!user?.is_admin) {
    return (
      <AuthGuard>
        <div className="auth-page">
          <div className="auth-card" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '64px', marginBottom: '20px' }}>🔒</div>
            <h2 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '12px' }}>
              Admin Access Required
            </h2>
            <p style={{ color: 'var(--text-secondary)' }}>
              You don&apos;t have permission to access this page.
            </p>
          </div>
        </div>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <div className="page-header animate-in">
            <h1 className="page-title">🛡️ Admin Panel</h1>
            <p className="page-subtitle">Manage user approvals and access control</p>
          </div>

          <div className="card animate-in" style={{ animationDelay: '0.1s' }}>
            <div className="card-header">
              <h2 className="card-title">Pending Approvals</h2>
              <button className="btn btn-secondary btn-sm" onClick={loadPending}>
                🔄 Refresh
              </button>
            </div>

            {loading ? (
              <div className="empty-state">
                <div className="spinner spinner-lg" />
                <div className="empty-state-title mt-16">Loading...</div>
              </div>
            ) : pendingUsers.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">✅</div>
                <div className="empty-state-title">All caught up!</div>
                <div className="empty-state-text">
                  No pending user approvals at this time.
                </div>
              </div>
            ) : (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Email</th>
                      <th>Registered</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingUsers.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div className="flex items-center gap-12">
                            {u.avatar_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={u.avatar_url}
                                alt={u.name}
                                style={{ width: 32, height: 32, borderRadius: '50%' }}
                              />
                            ) : (
                              <div style={{
                                width: 32, height: 32, borderRadius: '50%',
                                background: 'var(--accent-primary-glow)',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: '14px', fontWeight: 600, color: 'var(--accent-primary)',
                              }}>
                                {u.name.charAt(0).toUpperCase()}
                              </div>
                            )}
                            <strong>{u.name}</strong>
                          </div>
                        </td>
                        <td style={{ color: 'var(--text-secondary)' }}>{u.email}</td>
                        <td style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td>
                          <div className="flex items-center gap-8">
                            <button
                              className="btn btn-sm"
                              style={{
                                background: 'var(--accent-success-bg)',
                                color: 'var(--accent-success)',
                                border: '1px solid rgba(16, 185, 129, 0.2)',
                              }}
                              onClick={() => handleApprove(u.id, true)}
                            >
                              ✅ Approve
                            </button>
                            <button
                              className="btn btn-danger btn-sm"
                              onClick={() => handleApprove(u.id, false)}
                            >
                              ❌ Reject
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {toast && (
            <div className={`toast toast-${toast.type}`}>
              {toast.type === 'success' ? '✅' : '❌'} {toast.message}
            </div>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
