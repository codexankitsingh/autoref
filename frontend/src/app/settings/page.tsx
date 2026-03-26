'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { api } from '@/lib/api';

function SettingsContent() {
  // Profile state
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [profileText, setProfileText] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);

  // Mail accounts
  const [mailAccounts, setMailAccounts] = useState<Array<{ id: number; email: string; is_active: boolean }>>([]);
  const [newAccountEmail, setNewAccountEmail] = useState('');
  const [addingAccount, setAddingAccount] = useState(false);

  // UI
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);
  const [connectingGmail, setConnectingGmail] = useState(false);
  const searchParams = useSearchParams();

  useEffect(() => {
    loadProfile();
    loadMailAccounts();
    // Handle Gmail OAuth callback
    const gmailConnected = searchParams.get('gmail_connected');
    const gmailError = searchParams.get('gmail_error');
    if (gmailConnected) {
      showToast('success', `Gmail account ${gmailConnected} connected!`);
      loadMailAccounts();
    }
    if (gmailError) {
      showToast('error', `Gmail connection failed: ${gmailError}`);
    }
  }, [searchParams]);

  async function loadProfile() {
    try {
      const profile = await api.getProfile();
      setName(profile.name);
      setEmail(profile.email);
      setProfileText(profile.profile_text || '');
    } catch {
      // No profile yet
    }
  }

  async function loadMailAccounts() {
    try {
      const accounts = await api.getMailAccounts();
      setMailAccounts(accounts);
    } catch {
      // No accounts
    }
  }

  async function handleSaveProfile() {
    if (!name.trim() || !email.trim()) {
      showToast('error', 'Name and email are required');
      return;
    }

    setProfileSaving(true);
    try {
      await api.saveProfile({
        name,
        email,
        profile_text: profileText || undefined,
      });
      showToast('success', 'Profile saved!');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save';
      showToast('error', message);
    } finally {
      setProfileSaving(false);
    }
  }

  async function handleAddAccount() {
    if (!newAccountEmail.trim()) {
      showToast('error', 'Enter an email address');
      return;
    }

    setAddingAccount(true);
    try {
      await api.addMailAccount(newAccountEmail);
      showToast('success', 'Account added!');
      setNewAccountEmail('');
      loadMailAccounts();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to add';
      showToast('error', message);
    } finally {
      setAddingAccount(false);
    }
  }

  async function handleConnectGmail() {
    setConnectingGmail(true);
    try {
      const data = await api.getGmailAuthUrl();
      window.location.href = data.auth_url;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start Gmail auth';
      showToast('error', message);
    } finally {
      setConnectingGmail(false);
    }
  }

  function showToast(type: string, message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3000);
  }

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header animate-in">
          <h1 className="page-title">⚙️ Settings</h1>
          <p className="page-subtitle">Configure your profile and connected accounts</p>
        </div>

        <div className="grid-2 animate-in" style={{ animationDelay: '0.1s' }}>
          {/* Profile */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">👤 Your Profile</h3>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-tertiary)', marginBottom: '20px' }}>
              Your profile info is used by AI to personalize emails.
            </p>

            <div className="form-group">
              <label className="form-label">Full Name *</label>
              <input
                type="text"
                className="form-input"
                id="profile-name"
                placeholder="Your full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Email *</label>
              <input
                type="email"
                className="form-input"
                id="profile-email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Profile / Resume Text</label>
              <textarea
                className="form-textarea"
                id="profile-text"
                placeholder="Paste your resume summary or profile description here. The AI will use this to personalize your referral emails..."
                value={profileText}
                onChange={(e) => setProfileText(e.target.value)}
                style={{ minHeight: '180px' }}
              />
            </div>

            <button
              className="btn btn-primary w-full"
              id="save-profile-btn"
              onClick={handleSaveProfile}
              disabled={profileSaving}
            >
              {profileSaving ? (
                <>
                  <span className="spinner" /> Saving...
                </>
              ) : (
                '💾 Save Profile'
              )}
            </button>
          </div>

          {/* Mail Accounts */}
          <div>
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <h3 className="card-title">📬 Mail Accounts</h3>
              </div>
              <p style={{ fontSize: '13px', color: 'var(--text-tertiary)', marginBottom: '20px' }}>
                Connect your Gmail account via OAuth to send outreach emails securely.
              </p>

              {mailAccounts.length === 0 ? (
                <div className="empty-state" style={{ padding: '32px 16px' }}>
                  <div className="empty-state-icon">📭</div>
                  <div className="empty-state-title">No accounts connected</div>
                  <div className="empty-state-text">Connect a Gmail account to start sending emails.</div>
                </div>
              ) : (
                <div className="flex flex-col gap-8" style={{ marginBottom: '20px' }}>
                  {mailAccounts.map((acc) => (
                    <div
                      key={acc.id}
                      className="flex items-center justify-between"
                      style={{
                        padding: '12px 16px',
                        background: 'var(--bg-input)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid var(--border-subtle)',
                      }}
                    >
                      <div className="flex items-center gap-12">
                        <span>📧</span>
                        <span style={{ fontSize: '14px' }}>{acc.email}</span>
                      </div>
                      <span className="badge badge-replied">✅ Connected</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex gap-8">
                <button
                  className="btn btn-primary"
                  id="connect-gmail-btn"
                  onClick={handleConnectGmail}
                  disabled={connectingGmail}
                  style={{ flex: 1 }}
                >
                  {connectingGmail ? (
                    <><span className="spinner" /> Connecting...</>
                  ) : (
                    '🔗 Connect Gmail via OAuth'
                  )}
                </button>
              </div>

              <div style={{ marginTop: '12px', borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
                <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>Or add manually (for testing only):</p>
                <div className="flex gap-8">
                  <input
                    type="email"
                    className="form-input"
                    id="new-account-email"
                    placeholder="your-gmail@gmail.com"
                    value={newAccountEmail}
                    onChange={(e) => setNewAccountEmail(e.target.value)}
                    style={{ flex: 1, fontSize: '13px' }}
                  />
                  <button
                    className="btn btn-secondary btn-sm"
                    id="add-account-btn"
                    onClick={handleAddAccount}
                    disabled={addingAccount || !newAccountEmail.trim()}
                  >
                    {addingAccount ? <span className="spinner" /> : '+ Add'}
                  </button>
                </div>
              </div>
            </div>

            {/* API Status */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">🔌 API Status</h3>
              </div>
              <div className="flex flex-col gap-12">
                <div className="flex items-center justify-between">
                  <span style={{ fontSize: '14px' }}>Backend API</span>
                  <span className="badge badge-replied">Connected</span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ fontSize: '14px' }}>Gemini AI</span>
                  <span className="badge badge-replied">Connected</span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ fontSize: '14px' }}>Gmail API</span>
                  <span className={`badge ${mailAccounts.length > 0 ? 'badge-replied' : 'badge-followup'}`}>
                    {mailAccounts.length > 0 ? 'Connected' : 'Not Connected'}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span style={{ fontSize: '14px' }}>Google Sheets</span>
                  <span className="badge badge-draft">Coming Soon</span>
                </div>
              </div>
            </div>
          </div>
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

export default function SettingsPage() {
  return (
    <Suspense fallback={
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <div className="page-header">
            <h1 className="page-title">⚙️ Settings</h1>
            <p className="page-subtitle">Loading...</p>
          </div>
        </main>
      </div>
    }>
      <SettingsContent />
    </Suspense>
  );
}
