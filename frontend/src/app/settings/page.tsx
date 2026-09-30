'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import AuthGuard from '@/components/AuthGuard';
import { api } from '@/lib/api';

function SettingsContent() {
  // Profile state
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [profileText, setProfileText] = useState('');
  const [defaultTargetRole, setDefaultTargetRole] = useState('Data Engineering');
  const [defaultFollowUpDays, setDefaultFollowUpDays] = useState(3);
  const [defaultMaxFollowUps, setDefaultMaxFollowUps] = useState(3);
  const [defaultAiModel, setDefaultAiModel] = useState('gemini-2.5-flash-lite');
  const [profileSaving, setProfileSaving] = useState(false);

  // Mail accounts
  const [mailAccounts, setMailAccounts] = useState<Array<{ id: number; email: string; is_active: boolean }>>([]);
  const [newAccountEmail, setNewAccountEmail] = useState('');
  const [addingAccount, setAddingAccount] = useState(false);

  // UI
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);
  const [connectingGmail, setConnectingGmail] = useState(false);
  const [aiHealth, setAiHealth] = useState<string | null>(null);
  const [aiHealthOk, setAiHealthOk] = useState(true);
  const [aiDiagnosis, setAiDiagnosis] = useState<string | null>(null);
  const [aiSteps, setAiSteps] = useState<string[]>([]);
  const [aiKeyKind, setAiKeyKind] = useState<string | null>(null);
  const searchParams = useSearchParams();

  useEffect(() => {
    loadProfile();
    loadMailAccounts();
    loadAiHealth();
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
      setDefaultTargetRole(profile.default_target_role || 'Data Engineering');
      setDefaultFollowUpDays(profile.default_follow_up_interval_days ?? 3);
      setDefaultMaxFollowUps(profile.default_max_follow_ups ?? 3);
      setDefaultAiModel(profile.default_ai_model || 'gemini-2.5-flash-lite');
    } catch {
      // No profile yet
    }
  }

  async function loadAiHealth() {
    try {
      const h = await api.getAiHealth();
      setAiHealth(h.message);
      setAiHealthOk(h.gemini_ok || h.openai_ok);
      setAiDiagnosis(h.diagnosis || null);
      setAiSteps(h.remediation_steps || []);
      setAiKeyKind(h.gemini_key_kind || null);
    } catch {
      setAiHealth(null);
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

  async function handleLoadDataEngineeringTemplate() {
    try {
      const { profile_text } = await api.getProfileTemplate('data-engineering');
      setProfileText(profile_text);
      if (!name.trim()) setName('Ankit Kumar Singh');
      if (!email.trim()) setEmail('ankitkumarsingh171819@gmail.com');
      showToast('success', 'Loaded Data Engineering resume template — click Save Profile');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load template';
      showToast('error', message);
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
        default_target_role: defaultTargetRole,
        default_follow_up_interval_days: defaultFollowUpDays,
        default_max_follow_ups: defaultMaxFollowUps,
        default_ai_model: defaultAiModel,
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
    <AuthGuard>
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header animate-in">
          <div>
            <span className="page-eyebrow">Account</span>
            <h1 className="page-title">Settings</h1>
            <p className="page-subtitle">Profile, resume text, outreach defaults, and Gmail connection.</p>
          </div>
        </div>

        {aiHealth && (
          <div
            className="card animate-in"
            style={{
              marginBottom: '20px',
              borderColor: aiHealthOk ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
              background: aiHealthOk ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            }}
          >
            <p style={{ fontSize: '14px', margin: 0, color: aiHealthOk ? 'var(--accent-success)' : 'var(--accent-danger)' }}>
              <strong>AI engine:</strong> {aiHealth}
              {aiKeyKind && (
                <span style={{ display: 'block', marginTop: '6px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
                  Key type detected: {aiKeyKind}
                </span>
              )}
              {aiDiagnosis && (
                <span style={{ display: 'block', marginTop: '8px', fontSize: '13px' }}>{aiDiagnosis}</span>
              )}
              {!aiHealthOk && aiSteps.length > 0 && (
                <ul style={{ margin: '12px 0 0', paddingLeft: '20px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {aiSteps.slice(0, 5).map((step) => (
                    <li key={step} style={{ marginBottom: '6px' }}>{step}</li>
                  ))}
                </ul>
              )}
            </p>
          </div>
        )}

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
              <label className="form-label">Default outreach settings</label>
              <div className="grid-2" style={{ gap: '12px', marginBottom: '16px' }}>
                <div>
                  <label className="form-label" style={{ fontSize: '12px' }}>Target role</label>
                  <select
                    className="form-select"
                    value={defaultTargetRole}
                    onChange={(e) => setDefaultTargetRole(e.target.value)}
                  >
                    <option value="Data Engineering">Data Engineering</option>
                    <option value="Backend/SDE">Product Backend</option>
                    <option value="Systems">Systems / Core Engineering</option>
                    <option value="Fintech">Fintech / Payments</option>
                  </select>
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: '12px' }}>AI model</label>
                  <select
                    className="form-select"
                    value={defaultAiModel}
                    onChange={(e) => setDefaultAiModel(e.target.value)}
                  >
                    <option value="gemini-2.5-flash-lite">Flash Lite</option>
                    <option value="gemini-flash-latest">Flash Stable</option>
                    <option value="gemini-2.5-flash">Flash Experimental</option>
                  </select>
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: '12px' }}>Follow-up interval (days)</label>
                  <select
                    className="form-select"
                    value={defaultFollowUpDays}
                    onChange={(e) => setDefaultFollowUpDays(Number(e.target.value))}
                  >
                    {[2, 3, 4, 5, 7].map((d) => (
                      <option key={d} value={d}>{d} days</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="form-label" style={{ fontSize: '12px' }}>Max follow-ups</label>
                  <select
                    className="form-select"
                    value={defaultMaxFollowUps}
                    onChange={(e) => setDefaultMaxFollowUps(Number(e.target.value))}
                  >
                    {[1, 2, 3].map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <div className="form-group">
              <div className="flex gap-12" style={{ alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <label className="form-label" style={{ marginBottom: 0 }}>Profile / Resume Text</label>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleLoadDataEngineeringTemplate}
                >
                  Load DE resume template
                </button>
              </div>
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
    </AuthGuard>
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
