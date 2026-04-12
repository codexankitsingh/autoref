const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
};

async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {} } = options;

  const config: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  };

  if (body) {
    config.body = JSON.stringify(body);
  }

  const res = await fetch(`${API_BASE}${path}`, config);

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ── API Methods ──

export const api = {
  // Health
  health: () => apiRequest<{ status: string }>('/health'),

  // Generate
  generateEmail: (data: { jd_text: string; recipient_email: string; recipient_name?: string; model?: string; target_role?: string }) =>
    apiRequest<{
      parsed_jd: { company: string | null; role: string | null; skills: string[]; location: string | null };
      subject: string;
      email_body: string;
    }>('/api/generate-email', { method: 'POST', body: data }),

  // Send
  sendEmail: (data: {
    email_subject: string;
    email_body: string;
    recipient_email: string;
    recipient_name?: string;
    sender_account_id: number;
    follow_up_interval_days?: number;
    max_follow_ups?: number;
    company?: string;
    role?: string;
    jd_text?: string;
    skills?: string;
    location?: string;
  }) =>
    apiRequest<{ thread_id: number; gmail_thread_id: string | null; status: string; message: string }>(
      '/api/send-email',
      { method: 'POST', body: data }
    ),

  // Dashboard
  getDashboard: (params?: { status?: string; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return apiRequest<{
      records: Array<{
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
      }>;
      total: number;
    }>(`/api/dashboard${qs ? `?${qs}` : ''}`);
  },

  // Stats
  getDashboardStats: () =>
    apiRequest<{ total: number; sent: number; replied: number; interviews: number }>('/api/dashboard/stats'),

  // Status
  updateStatus: (data: { thread_id: number; status: string; replied?: boolean; interview_scheduled?: boolean }) =>
    apiRequest('/api/update-status', { method: 'POST', body: data }),

  // Delete
  deleteThread: (threadId: number) =>
    apiRequest(`/api/thread/${threadId}`, { method: 'DELETE' }),

  // Google Sheets Sync
  syncToSheets: (data: { account_id: number; spreadsheet_id?: string }) =>
    apiRequest<{ message: string; spreadsheet_id: string; url: string }>('/api/dashboard/sync-sheets', { method: 'POST', body: data }),

  // Follow-ups
  scheduleFollowups: (data: { thread_id: number; interval_days: number; max_follow_ups?: number }) =>
    apiRequest('/api/schedule-followups', { method: 'POST', body: data }),

  stopFollowups: (data: { thread_id: number }) =>
    apiRequest('/api/stop-followups', { method: 'POST', body: data }),

  // Profile
  getProfile: () =>
    apiRequest<{ id: number; name: string; email: string; profile_text: string | null }>('/api/profile'),

  saveProfile: (data: { name: string; email: string; profile_text?: string }) =>
    apiRequest('/api/profile', { method: 'POST', body: data }),

  // Mail Accounts
  getMailAccounts: () =>
    apiRequest<Array<{ id: number; email: string; is_active: boolean }>>('/api/mail-accounts'),

  addMailAccount: (email: string) =>
    apiRequest(`/api/mail-accounts?email=${encodeURIComponent(email)}`, { method: 'POST' }),

  // Gmail OAuth
  getGmailAuthUrl: () =>
    apiRequest<{ auth_url: string }>('/api/auth/gmail'),
};
