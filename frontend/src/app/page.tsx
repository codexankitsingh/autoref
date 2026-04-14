'use client';

import { useState, useEffect, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import { api } from '@/lib/api';

interface ParsedJD {
  company: string | null;
  role: string | null;
  skills: string[];
  location: string | null;
}

export default function NewOutreachPage() {
  // Form state
  const [jdText, setJdText] = useState('');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [recipientName, setRecipientName] = useState('');
  const [senderAccountId, setSenderAccountId] = useState<number>(0);
  const [followUpDays, setFollowUpDays] = useState(3);
  const [maxFollowUps, setMaxFollowUps] = useState(3);
  const [aiModel, setAiModel] = useState('gemini-2.5-flash-lite');
  const [targetRole, setTargetRole] = useState('Backend/SDE');

  // Generated email state
  const [parsedJD, setParsedJD] = useState<ParsedJD | null>(null);
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [showPreview, setShowPreview] = useState(false);

  // Mail accounts
  const [mailAccounts, setMailAccounts] = useState<Array<{ id: number; email: string }>>([]);

  // UI state
  const [generating, setGenerating] = useState(false);
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<{ type: string; message: string } | null>(null);

  useEffect(() => {
    loadMailAccounts();
    // Hydrate form draft from localStorage
    try {
      const draft = localStorage.getItem('outreachDraft');
      if (draft) {
        const parsed = JSON.parse(draft);
        if (parsed.jdText) setJdText(parsed.jdText);
        if (parsed.recipientEmail) setRecipientEmail(parsed.recipientEmail);
        if (parsed.recipientName) setRecipientName(parsed.recipientName);
        if (parsed.aiModel) setAiModel(parsed.aiModel);
        if (parsed.targetRole) setTargetRole(parsed.targetRole);
        if (parsed.parsedJD) setParsedJD(parsed.parsedJD);
        if (parsed.emailSubject) setEmailSubject(parsed.emailSubject);
        if (parsed.emailBody) setEmailBody(parsed.emailBody);
        if (parsed.showPreview !== undefined) setShowPreview(parsed.showPreview);
      }
    } catch {
      // Ignored
    }
  }, []);

  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    const draft = {
      jdText, recipientEmail, recipientName, aiModel, targetRole, parsedJD, emailSubject, emailBody, showPreview
    };
    localStorage.setItem('outreachDraft', JSON.stringify(draft));
  }, [jdText, recipientEmail, recipientName, aiModel, targetRole, parsedJD, emailSubject, emailBody, showPreview]);

  async function loadMailAccounts() {
    try {
      const accounts = await api.getMailAccounts();
      setMailAccounts(accounts);
      if (accounts.length > 0) setSenderAccountId(accounts[0].id);
    } catch {
      // Will be empty until accounts are configured
    }
  }

  async function handleGenerate() {
    if (!jdText.trim()) {
      showToast('error', 'Please paste a job description');
      return;
    }
    if (!recipientEmail.trim()) {
      showToast('error', 'Please enter a recipient email');
      return;
    }

    setGenerating(true);
    try {
      const result = await api.generateEmail({
        jd_text: jdText,
        recipient_email: recipientEmail,
        recipient_name: recipientName || undefined,
        model: aiModel,
        target_role: targetRole,
      });

      setParsedJD(result.parsed_jd);
      setEmailSubject(result.subject);
      setEmailBody(result.email_body);
      setShowPreview(true);
      showToast('success', 'Email generated! Review and edit before sending.');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Generation failed';
      showToast('error', message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleSend() {
    if (!emailBody.trim() || !emailSubject.trim()) {
      showToast('error', 'Email subject and body are required');
      return;
    }

    // Inject recipient name into the greeting before sending
    const firstName = recipientName.trim().split(' ')[0] || 'there';
    const personalizedBody = emailBody.replace(
      /Hi Name,/i,
      `Hi ${firstName},`
    );

    setSending(true);
    try {
      await api.sendEmail({
        email_subject: emailSubject,
        email_body: personalizedBody,
        recipient_email: recipientEmail,
        recipient_name: recipientName || undefined,
        sender_account_id: senderAccountId,
        follow_up_interval_days: followUpDays,
        max_follow_ups: maxFollowUps,
        company: parsedJD?.company || undefined,
        role: parsedJD?.role || undefined,
        jd_text: jdText,
        skills: parsedJD?.skills?.join(', ') || undefined,
        location: parsedJD?.location || undefined,
      });

      showToast('success', `✅ Sent to ${recipientEmail}! Add next recipient to send again.`);
      // Only clear recipient fields — preserve JD/email so user can send to next HR
      setRecipientEmail('');
      setRecipientName('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to send';
      showToast('error', message);
    } finally {
      setSending(false);
    }
  }

  function showToast(type: string, message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 3000);
  }

  function clearDraftFields() {
    setJdText('');
    setRecipientEmail('');
    setRecipientName('');
    setEmailSubject('');
    setEmailBody('');
    setParsedJD(null);
    setShowPreview(false);
    localStorage.removeItem('outreachDraft');
  }

  function handleClearDraft() {
    if (window.confirm('Are you sure you want to clear your entire drafted email?')) {
      clearDraftFields();
    }
  }

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <div className="page-header animate-in">
          <h1 className="page-title">✨ New Outreach</h1>
          <p className="page-subtitle">Paste a job description to generate a tailored referral email</p>
        </div>

        <div className="grid-2 animate-in" style={{ animationDelay: '0.1s' }}>
          {/* Left Column: Input */}
          <div>
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <h3 className="card-title">📋 Job Description</h3>
              </div>
              <div className="form-group">
                <label className="form-label">Paste JD Here</label>
                <textarea
                  className="form-textarea"
                  id="jd-input"
                  placeholder="Paste the full job description here..."
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  style={{ minHeight: '200px' }}
                />
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <h3 className="card-title">📧 Outreach Details</h3>
              </div>

              <div className="form-group">
                <label className="form-label">Recipient Email *</label>
                <input
                  type="email"
                  className="form-input"
                  id="recipient-email"
                  placeholder="john@company.com"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Recipient Name (optional)</label>
                <input
                  type="text"
                  className="form-input"
                  id="recipient-name"
                  placeholder="John Doe"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                />
              </div>

              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Sender Account</label>
                  <select
                    className="form-select"
                    id="sender-account"
                    value={senderAccountId}
                    onChange={(e) => setSenderAccountId(Number(e.target.value))}
                  >
                    {mailAccounts.length === 0 ? (
                      <option value={0}>No accounts — add in Settings</option>
                    ) : (
                      mailAccounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>{acc.email}</option>
                      ))
                    )}
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Follow-up Interval</label>
                  <select
                    className="form-select"
                    id="followup-interval"
                    value={followUpDays}
                    onChange={(e) => setFollowUpDays(Number(e.target.value))}
                  >
                    <option value={2}>Every 2 days</option>
                    <option value={3}>Every 3 days</option>
                    <option value={4}>Every 4 days</option>
                    <option value={5}>Every 5 days</option>
                    <option value={7}>Every 7 days</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Max Follow-ups</label>
                <select
                  className="form-select"
                  id="max-followups"
                  value={maxFollowUps}
                  onChange={(e) => setMaxFollowUps(Number(e.target.value))}
                >
                  <option value={1}>1 follow-up</option>
                  <option value={2}>2 follow-ups</option>
                  <option value={3}>3 follow-ups</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">AI Engine</label>
                <select
                  className="form-select"
                  id="ai-model-select"
                  value={aiModel}
                  onChange={(e) => setAiModel(e.target.value)}
                >
                  <option value="gemini-2.5-flash-lite">Flash Lite (Default - 1000 Daily Quota)</option>
                  <option value="gemini-flash-latest">Flash Stable (Fast Endpoint)</option>
                  <option value="gemini-2.5-flash">Flash Experimental (20/day limit)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Target Role</label>
                <select
                  className="form-select"
                  id="target-role-select"
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value)}
                >
                  <option value="Backend/SDE">Backend Engineering / SDE</option>
                  <option value="Data Engineering">Data Engineering</option>
                </select>
              </div>

              <div className="flex gap-12 mt-16">
                <button
                  className="btn btn-primary btn-lg w-full"
                  id="generate-btn"
                  onClick={handleGenerate}
                  disabled={generating || !jdText.trim() || !recipientEmail.trim()}
                  style={{ flex: 1 }}
                >
                  {generating ? (
                    <>
                      <span className="spinner" /> Generating...
                    </>
                  ) : (
                    '⚡ Generate Email'
                  )}
                </button>
                <button
                  className="btn btn-secondary btn-lg"
                  onClick={handleClearDraft}
                  title="Clear Draft"
                >
                  🗑️ Clear
                </button>
              </div>
            </div>
          </div>

          {/* Right Column: Preview */}
          <div>
            {showPreview ? (
              <div className="animate-in">
                {/* Parsed JD Info */}
                {parsedJD && (
                  <div className="card" style={{ marginBottom: '20px' }}>
                    <div className="card-header">
                      <h3 className="card-title">🔍 Parsed Info</h3>
                    </div>
                    <div className="flex flex-col gap-8">
                      <div><strong>Company:</strong> {parsedJD.company || '—'}</div>
                      <div><strong>Role:</strong> {parsedJD.role || '—'}</div>
                      <div><strong>Location:</strong> {parsedJD.location || '—'}</div>
                      {parsedJD.skills.length > 0 && (
                        <div>
                          <strong>Skills:</strong>{' '}
                          <div className="flex gap-8" style={{ flexWrap: 'wrap', marginTop: '8px' }}>
                            {parsedJD.skills.map((skill, i) => (
                              <span key={i} className="badge badge-sent">{skill}</span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Email Preview */}
                <div className="card">
                  <div className="card-header">
                    <h3 className="card-title">✉️ Email Preview</h3>
                    <span className="badge badge-draft">Editable</span>
                  </div>

                  <div className="form-group">
                    <label className="form-label">Subject</label>
                    <input
                      type="text"
                      className="form-input"
                      id="email-subject"
                      value={emailSubject}
                      onChange={(e) => setEmailSubject(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Body</label>
                    <textarea
                      className="form-textarea"
                      id="email-body"
                      value={emailBody}
                      onChange={(e) => setEmailBody(e.target.value)}
                      style={{ minHeight: '250px' }}
                    />
                  </div>

                  <div className="flex gap-12">
                    <button
                      className="btn btn-primary btn-lg"
                      id="send-btn"
                      onClick={handleSend}
                      disabled={sending || senderAccountId === 0}
                      style={{ flex: 1 }}
                    >
                      {sending ? (
                        <>
                          <span className="spinner" /> Sending...
                        </>
                      ) : (
                        '🚀 Send Email'
                      )}
                    </button>
                    <button
                      className="btn btn-secondary btn-lg"
                      onClick={handleGenerate}
                      disabled={generating}
                    >
                      🔄 Regenerate
                    </button>
                    <button
                      className="btn btn-secondary btn-lg"
                      onClick={handleClearDraft}
                      title="Clear everything and start fresh"
                    >
                      🗑️ Clear All
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="card">
                <div className="empty-state">
                  <div className="empty-state-icon">📨</div>
                  <div className="empty-state-title">Email Preview</div>
                  <div className="empty-state-text">
                    Paste a job description and click &quot;Generate Email&quot; to see your AI-crafted referral email here.
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Toast */}
        {toast && (
          <div className={`toast toast-${toast.type}`}>
            {toast.type === 'success' ? '✅' : '❌'} {toast.message}
          </div>
        )}
      </main>
    </div>
  );
}
