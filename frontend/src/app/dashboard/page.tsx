'use client';

import { useState, useEffect, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import { api } from '@/lib/api';

interface OutreachRecord {
  id: number;
  company: string | null;
  role: string | null;
  recipient_email: string;
  recipient_name: string | null;
  sender_email: string;
  status: string;
  follow_up_count: number;
  last_activity_at: string | null;
  replied: boolean;
  interview_scheduled: boolean;
  created_at: string;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  sent: 'Sent',
  follow_up_1: 'Follow-up 1',
  follow_up_2: 'Follow-up 2',
  follow_up_3: 'Follow-up 3',
  replied: 'Replied',
  interview_scheduled: 'Interview',
  closed: 'Closed',
};

const STATUS_BADGE_CLASS: Record<string, string> = {
  draft: 'badge-draft',
  sent: 'badge-sent',
  follow_up_1: 'badge-followup',
  follow_up_2: 'badge-followup',
  follow_up_3: 'badge-followup',
  replied: 'badge-replied',
  interview_scheduled: 'badge-interview',
  closed: 'badge-closed',
};

export default function DashboardPage() {
  const [records, setRecords] = useState<OutreachRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [search, setSearch] = useState('');
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);
  const [stats, setStats] = useState({ total: 0, sent: 0, replied: 0, interviews: 0 });

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [data, statsData] = await Promise.all([
        api.getDashboard({
          status: filterStatus || undefined,
          search: search || undefined,
        }),
        api.getDashboardStats(),
      ]);
      setRecords(data.records);
      setTotal(data.total);
      setStats(statsData);
    } catch {
      // API not reachable
    } finally {
      setLoading(false);
    }
  }, [filterStatus, search]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  async function handleStatusChange(threadId: number, newStatus: string) {
    try {
      await api.updateStatus({
        thread_id: threadId,
        status: newStatus,
        replied: newStatus === 'replied',
        interview_scheduled: newStatus === 'interview_scheduled',
      });
      showToast('success', 'Status updated');
      loadDashboard();
    } catch {
      showToast('error', 'Failed to update status');
    }
  }

  const [syncing, setSyncing] = useState(false);
  
  async function handleDelete(threadId: number) {
    if (!window.confirm('Delete this outreach record?')) return;
    try {
      await api.deleteThread(threadId);
      showToast('success', 'Record deleted');
      loadDashboard();
    } catch {
      showToast('error', 'Failed to delete');
    }
  }

  async function handleSyncSheets() {
    setSyncing(true);
    try {
      const accounts = await api.getMailAccounts();
      if (!accounts || accounts.length === 0) {
        showToast('error', 'Connect a Gmail account in Settings first.');
        return;
      }
      const data = await api.syncToSheets({ account_id: accounts[0].id });
      showToast('success', 'Synced to Google Sheets!');
      window.open(data.url, '_blank');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to sync';
      showToast('error', message);
    } finally {
      setSyncing(false);
    }
  }

  function showToast(type: string, message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3000);
  }

  function formatDate(dateStr: string | null) {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    });
  }

  // Stats
  // ... rest

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header animate-in">
          <h1 className="page-title">📊 Dashboard</h1>
          <p className="page-subtitle">Track all your outreach in one place</p>
        </div>

        {/* Stats */}
        <div className="stats-grid animate-in" style={{ animationDelay: '0.1s' }}>
          <div className="stat-card">
            <div className="stat-card-label">Total Outreach</div>
            <div className="stat-card-value">{stats.total}</div>
          </div>
          <div className="stat-card">
            <div className="stat-card-label">Emails Sent</div>
            <div className="stat-card-value">{stats.sent}</div>
          </div>
          <div className="stat-card">
            <div className="stat-card-label">Replies</div>
            <div className="stat-card-value" style={{ color: 'var(--accent-success)' }}>{stats.replied}</div>
          </div>
          <div className="stat-card">
            <div className="stat-card-label">Interviews</div>
            <div className="stat-card-value" style={{ color: 'var(--accent-primary)' }}>{stats.interviews}</div>
          </div>
        </div>

        {/* Filters */}
        <div className="card animate-in" style={{ marginBottom: '24px', animationDelay: '0.2s' }}>
          <div className="flex items-center gap-16" style={{ flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <input
                type="text"
                className="form-input"
                id="search-input"
                placeholder="🔍 Search by company or role..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              className="form-select"
              id="filter-status"
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              style={{ width: '200px' }}
            >
              <option value="">All Statuses</option>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <button className="btn btn-secondary btn-sm" onClick={loadDashboard}>
              🔄 Refresh
            </button>
            <button 
              className="btn btn-primary btn-sm" 
              onClick={handleSyncSheets}
              disabled={syncing}
            >
              {syncing ? 'Syncing...' : '📄 Sync to Sheets'}
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="animate-in" style={{ animationDelay: '0.3s' }}>
          {loading ? (
            <div className="card">
              <div className="empty-state">
                <div className="spinner spinner-lg" />
                <div className="empty-state-title mt-16">Loading...</div>
              </div>
            </div>
          ) : records.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-state-icon">📭</div>
                <div className="empty-state-title">No outreach yet</div>
                <div className="empty-state-text">
                  Start by creating a new outreach from the sidebar.
                </div>
              </div>
            </div>
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Role</th>
                    <th>Recipient</th>
                    <th>Status</th>
                    <th>Follow-ups</th>
                    <th>Last Activity</th>
                    <th>Reply</th>
                    <th>Interview</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.id}>
                      <td><strong>{record.company || '—'}</strong></td>
                      <td>{record.role || '—'}</td>
                      <td>
                        <div>{record.recipient_name || ''}</div>
                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                          {record.recipient_email}
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${STATUS_BADGE_CLASS[record.status] || 'badge-draft'}`}>
                          {STATUS_LABELS[record.status] || record.status}
                        </span>
                      </td>
                      <td>{record.follow_up_count} / 3</td>
                      <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        {formatDate(record.last_activity_at)}
                      </td>
                      <td>{record.replied ? '✅' : '—'}</td>
                      <td>{record.interview_scheduled ? '🎯' : '—'}</td>
                      <td>
                        <div className="flex items-center gap-8">
                          <select
                            className="form-select"
                            style={{ width: '130px', padding: '6px 10px', fontSize: '12px' }}
                            value={record.status}
                            onChange={(e) => handleStatusChange(record.id, e.target.value)}
                          >
                            {Object.entries(STATUS_LABELS).map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                          <button
                            className="btn btn-sm"
                            style={{ padding: '4px 8px', fontSize: '12px', background: 'transparent', color: 'var(--text-tertiary)' }}
                            onClick={() => handleDelete(record.id)}
                            title="Delete"
                          >
                            🗑️
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
  );
}
