# AutoRef — Technical Documentation

## 1. Project Overview

**AutoRef** is a full-stack SaaS platform that automates cold outreach for job seekers. It uses LLM-powered email generation (Google Gemini) to semantically match resumes against job descriptions, generates personalized referral emails, sends them via Gmail OAuth, and orchestrates automated follow-up sequences — all from a single dashboard.

**Key Metrics:**
- Reduces cold email drafting from ~15 minutes to ~45 seconds (95% reduction)
- Supports 3 target role categories with dedicated resume matching
- Automated 3-stage follow-up pipeline with reply detection
- Multi-tenant architecture with admin approval flow

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│              Next.js 16 (Vercel Edge)                       │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  Login   │ │ Register │ │ Outreach │ │Dashboard │       │
│  │  /login  │ │/register │ │    /     │ │/dashboard│       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
│       │             │            │             │             │
│       └─────────────┴─────┬──────┴─────────────┘             │
│                     AuthContext                              │
│              (JWT in localStorage)                           │
│                     api.ts                                   │
│            (Bearer token injection)                          │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS (JSON)
                      │ Authorization: Bearer <JWT>
┌─────────────────────┴───────────────────────────────────────┐
│                        BACKEND                              │
│              FastAPI 0.115 (Render)                          │
│                                                             │
│  ┌─────────────┐   ┌──────────────────────────────┐         │
│  │ Auth Router │   │     Protected Routers        │         │
│  │ /api/auth/* │   │ generate, send, dashboard,   │         │
│  │ (no auth)   │   │ followup, settings           │         │
│  └──────┬──────┘   └──────────┬───────────────────┘         │
│         │                     │                             │
│  ┌──────┴─────────────────────┴──────────────┐              │
│  │           dependencies.py                  │              │
│  │  get_current_user → get_approved_user      │              │
│  │  JWT decode │ bcrypt verify │ DB lookup     │              │
│  └──────────────────┬────────────────────────┘              │
│                     │                                       │
│  ┌──────────────────┴────────────────────────┐              │
│  │              Services Layer               │              │
│  │  AIService    │ EmailService │ Scheduler   │              │
│  │  (Gemini API) │ (Gmail API)  │(APScheduler)│              │
│  └──────────────────┬────────────────────────┘              │
│                     │                                       │
│  ┌──────────────────┴────────────────────────┐              │
│  │         SQLAlchemy ORM + SQLite           │              │
│  │  users │ mail_accounts │ email_threads    │              │
│  │  job_applications │ messages │ follow_ups │              │
│  └───────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘

                    EXTERNAL SERVICES
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Google Gemini│  │  Gmail API   │  │Google Sheets │
│  (AI/LLM)   │  │  (OAuth2)    │  │  (Export)    │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## 3. Authentication & Authorization

### 3.1 Architecture — Three-Tier Dependency Chain

```
Request with Bearer token
         │
         ▼
┌─────────────────────┐
│  get_current_user   │ ← Decodes JWT, validates, returns User
│  (401 if invalid)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  get_approved_user  │ ← Checks user.is_approved == 1
│  (403 if pending)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   get_admin_user    │ ← Checks user.is_admin == 1
│  (403 if not admin) │
└─────────────────────┘
```

**Every protected endpoint** uses `get_approved_user` as a FastAPI `Depends()`.
Admin-only endpoints (approve/reject users) use `get_admin_user`.

### 3.2 JWT Token Flow

| Token | Lifetime | Purpose |
|-------|----------|---------|
| Access Token | 24 hours | API authentication via `Authorization: Bearer <token>` |
| Refresh Token | 7 days | Obtain new access token without re-login |

**Token payload:**
```json
{
  "sub": "42",        // user_id as string
  "exp": 1716000000,  // expiry timestamp
  "type": "access"    // or "refresh"
}
```

**Why HS256 (symmetric) over RS256 (asymmetric)?**
- Single backend server — no need for public key distribution
- Simpler config (one secret vs key pair)
- Lower computational overhead per request

### 3.3 Password Security

- **Algorithm:** bcrypt via `passlib`
- **Why bcrypt over argon2?** Wider library support, battle-tested, sufficient for this scale
- Passwords are **never stored in plaintext** — only the bcrypt hash
- `password_hash` is nullable to support Google OAuth-only accounts

### 3.4 Google Sign-In Flow

```
Frontend                    Google                     Backend
   │                          │                          │
   │  1. Render GSI button    │                          │
   │ ─────────────────────►   │                          │
   │                          │                          │
   │  2. User clicks,        │                          │
   │     Google popup         │                          │
   │ ◄─────────────────────   │                          │
   │                          │                          │
   │  3. Google returns       │                          │
   │     ID token (JWT)       │                          │
   │ ◄─────────────────────   │                          │
   │                          │                          │
   │  4. POST /api/auth/google {credential: id_token}   │
   │ ──────────────────────────────────────────────────► │
   │                          │                          │
   │                          │  5. Verify ID token      │
   │                          │ ◄────────────────────────│
   │                          │  6. Return user info     │
   │                          │ ────────────────────────►│
   │                          │                          │
   │  7. Return {access_token, refresh_token, user}      │
   │ ◄──────────────────────────────────────────────────│
   │                          │                          │
   │  8. Store in localStorage│                          │
   │  9. Redirect to /        │                          │
```

**Key:** The Google ID token is verified server-side using `google.oauth2.id_token.verify_oauth2_token()`. We never trust the client.

### 3.5 Admin Approval Flow

```
New User Registers
        │
        ▼
┌─────────────────┐     ┌─────────────────────────┐
│ is_approved = 0 │────►│ Sees "Pending Approval"  │
│ is_admin = 0    │     │ screen (AuthGuard)       │
└─────────────────┘     └─────────────────────────┘
                              │
              Admin visits /admin panel
                              │
                              ▼
                   ┌──────────────────┐
                   │ POST /approve    │
                   │ is_approved = 1  │
                   └──────────────────┘
                              │
                              ▼
                   User can now access app
```

**First-user bootstrap:** The very first registered user OR the user matching `ADMIN_EMAIL` env var is auto-approved as admin.

### 3.6 Gmail OAuth (Mail Connection) — State Parameter Fix

**Problem:** Gmail OAuth callback is a redirect from Google — no Bearer token attached.

**Solution:** We pass `user_id` in the OAuth `state` parameter:
1. `GET /api/auth/gmail` → passes `state=current_user.id` to Google
2. Google redirects back to `/api/auth/gmail/callback?code=xxx&state=42`
3. Callback reads `state` → looks up user by ID → links Gmail account

**Scope relaxation:** We set `OAUTHLIB_RELAX_TOKEN_SCOPE=1` because Google sometimes returns scope strings in a different order than requested, causing the library to throw "Scope has changed" errors.

---

## 4. Multi-Tenant Data Isolation

Every data-bearing table includes `user_id` FK:

```
users (1) ──────┬──── (*) mail_accounts
                │
                ├──── (*) job_applications ──── (*) email_threads
                │                                      │
                └──── (*) email_threads ───────────────┘
                                │
                                ├──── (*) messages
                                ├──── (*) follow_up_jobs
                                └──── (*) replies
```

**Every query is scoped:**
```python
# Dashboard — only shows current user's threads
db.query(EmailThread).filter(EmailThread.user_id == current_user.id)

# Status update — verifies ownership before mutation
thread = db.query(EmailThread).filter(
    EmailThread.id == thread_id,
    EmailThread.user_id == current_user.id,
).first()
```

**Trade-off: Row-level filtering vs separate databases per user**
- Row-level filtering (our approach): simpler, works with SQLite, sufficient for current scale
- Separate DBs: better isolation but complex operationally; overkill for <1000 users

---

## 5. AI Email Generation Pipeline

### 5.1 Two-Stage Pipeline

```
JD Text ──► Stage 1: parse_jd() ──► Structured JSON
                                         │
                                         ▼
                                    Stage 2: generate_email()
                                         │
User Profile ─────────────────────────────┘
Resume Link (role-specific) ──────────────┘
                                         │
                                         ▼
                                  {subject, body} HTML
```

### 5.2 Role-Specific Prompt Engineering

| Role | Bullet Categories | Subject Style | Resume Link |
|------|-------------------|---------------|-------------|
| Backend/SDE | API Design, Performance, DSA | "800+ TPS API at p99 <50ms" | SDE resume |
| Fintech | Payment Systems, Security, Reliability | "ACID Transactions & Idempotent APIs" | Fintech resume |
| Data Engineering | Pipeline Architecture, Spark, Data Modeling | "150 GB/day ingestion pipeline" | DE resume |

Each role gets a tailored `role_configs` dict with:
- `bullet_guidance`: Specific achievement categories to extract from the user's profile
- `subject_examples`: Domain-appropriate subject line templates
- `emphasis`: Directive telling the LLM which angle to frame the profile through

### 5.3 Retry & Rate Limiting

```python
def _call_gemini(self, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(...)
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

**Trade-off:** Synchronous calls with retry vs async queue
- Current: Synchronous with exponential backoff — simpler, user sees result immediately
- Alternative: Celery/RQ queue — better for high concurrency, adds infrastructure complexity

---

## 6. Follow-Up Automation Engine

### 6.1 Architecture

```
APScheduler (Background)
    │
    │  Every 1 minute
    ▼
┌──────────────────────────┐
│ _process_pending_followups│
│                          │
│ 1. Query due jobs        │
│ 2. Pick exactly ONE      │  ← Steady drip (1/min)
│ 3. Execute follow-up     │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  _execute_follow_up      │
│                          │
│ 1. Check stop conditions │  ← replied? closed?
│ 2. Get original email    │
│ 3. AI generates follow-up│  ← With actual sent date
│ 4. Send via Gmail API    │
│ 5. Update thread status  │
└──────────────────────────┘
```

### 6.2 Key Design Decisions

**Why process only 1 per minute?**
- Gmail rate limits: sending too many emails quickly triggers spam flags
- Natural throttling without complex threading/semaphore logic
- 1/min = 60/hour = more than enough for individual job seekers

**Why APScheduler over Celery?**
- No external broker needed (Redis/RabbitMQ)
- Runs in-process — zero infrastructure overhead
- Sufficient for single-server deployment on Render free tier

**Idempotency guarantees:**
- Each `FollowUpJob` has a unique `(thread_id, follow_up_number)` pair
- Jobs transition: `pending → sent | failed | cancelled` (terminal states)
- Failed jobs are NOT retried (prevents spam loops from permanent failures)

### 6.3 Placeholder Hallucination Prevention

Follow-up emails had LLM-generated `[Date of original email]` placeholders.

**Three-layer defense:**
1. **Data injection:** Pass `original_sent_date` (e.g., "May 14, 2026") into the prompt
2. **Prompt engineering:** Rule 8 instructs the LLM to use vague phrasing ("my recent email")
3. **Catch-all regex:** `re.sub(r'\[.*?\]', '', result)` strips ANY bracket-wrapped placeholder

---

## 7. Database Schema

```
┌──────────────────┐     ┌──────────────────┐
│      users       │     │  mail_accounts   │
├──────────────────┤     ├──────────────────┤
│ id (PK)          │◄───┤ user_id (FK)     │
│ name             │     │ email            │
│ email (unique)   │     │ oauth_token      │
│ password_hash    │     │ refresh_token    │
│ google_id        │     │ is_active        │
│ is_approved      │     └──────────────────┘
│ is_admin         │
│ profile_text     │     ┌──────────────────┐
└──────────────────┘     │ job_applications │
                         ├──────────────────┤
                         │ id (PK)          │
                    ┌───►│ user_id (FK)     │
                    │    │ company, role    │
                    │    │ jd_text, skills  │
                    │    └──────────────────┘
                    │
┌──────────────────┐│    ┌──────────────────┐
│  email_threads   ││    │    messages      │
├──────────────────┤│    ├──────────────────┤
│ id (PK)          │┘    │ thread_id (FK)   │
│ user_id (FK)     │◄───┤ message_type     │
│ application_id   │     │ subject, content │
│ recipient_id     │     │ sent_at          │
│ sender_account_id│     └──────────────────┘
│ gmail_thread_id  │
│ status           │     ┌──────────────────┐
│ follow_up_count  │     │  follow_up_jobs  │
│ replied          │     ├──────────────────┤
└──────────────────┘◄───┤ thread_id (FK)   │
                         │ follow_up_number │
                         │ scheduled_time   │
                         │ status           │
                         └──────────────────┘
```

**Why SQLite over PostgreSQL?**
- Zero operational cost (no managed DB service)
- File-based — works on Render free tier without add-ons
- Sufficient for single-user/small-team usage (<10K rows)
- Trade-off: No concurrent write scaling — acceptable for this workload

---

## 8. API Endpoints

### Auth (No auth required)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/auth/register` | Email/password registration |
| POST | `/api/auth/login` | Email/password login |
| POST | `/api/auth/google` | Google ID token login |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Get current user profile |

### Protected (Requires `get_approved_user`)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/generate-email` | Parse JD + generate email |
| POST | `/api/send-email` | Send email via Gmail |
| GET | `/api/dashboard` | List user's outreach records |
| GET | `/api/dashboard/stats` | Aggregate statistics |
| POST | `/api/update-status` | Update thread status |
| DELETE | `/api/thread/{id}` | Delete a thread |
| POST | `/api/schedule-followups` | Schedule follow-ups |
| POST | `/api/stop-followups` | Cancel pending follow-ups |
| GET | `/api/profile` | Get user profile |
| POST | `/api/profile` | Update user profile |
| GET | `/api/mail-accounts` | List Gmail accounts |
| GET | `/api/auth/gmail` | Initiate Gmail OAuth |

### Admin (Requires `get_admin_user`)
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/auth/pending-users` | List unapproved users |
| POST | `/api/auth/approve-user` | Approve/reject a user |

---

## 9. Frontend Architecture

### Route Protection

```
layout.tsx
  └── AuthProvider (Context)
        │
        ├── /login      ← Public (redirects to / if logged in)
        ├── /register   ← Public (redirects to / if logged in)
        │
        ├── /           ← AuthGuard → Outreach page
        ├── /dashboard  ← AuthGuard → Dashboard
        ├── /settings   ← AuthGuard → Settings
        └── /admin      ← AuthGuard + is_admin check → Admin panel
```

### AuthGuard States
1. **Loading** → Spinner (validating token via `/api/auth/me`)
2. **Not authenticated** → Redirect to `/login`
3. **Authenticated but not approved** → "Pending Approval" screen
4. **Authenticated and approved** → Render children

### Token Management
- Stored in `localStorage`: `autoref_token`, `autoref_refresh_token`, `autoref_user`
- Injected via `api.ts` on every request: `Authorization: Bearer <token>`
- **401 interceptor:** Auto-clears auth and redirects to `/login`

---

## 10. Deployment Architecture

```
┌─────────────┐         ┌──────────────┐
│   Vercel    │ HTTPS   │    Render    │
│  (Frontend) │────────►│  (Backend)   │
│  Next.js    │         │  FastAPI     │
│  Edge CDN   │         │  SQLite DB   │
└─────────────┘         │  APScheduler │
                        └──────┬───────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        Google Gemini    Gmail API      Google Sheets
```

**Keep-alive ping:** Render free tier spins down after 15 min inactivity. APScheduler pings `/health` every 14 minutes to prevent this.

---

## 11. Design Trade-offs & Interview Defense

### Q: "Why SQLite instead of PostgreSQL?"
**A:** Operational simplicity. SQLite is zero-config, file-based, and free. For a single-tenant SaaS with <10K rows and no concurrent write pressure (one user at a time), SQLite outperforms managed Postgres on cost ($0 vs $7+/month) and latency (no network hop). Migration path to Postgres is trivial — SQLAlchemy abstracts the dialect.

### Q: "Why not use Celery for background jobs?"
**A:** APScheduler runs in-process with no external broker dependency. For a single-server deployment sending ~60 emails/hour max, the overhead of Redis + Celery worker processes is unjustified. APScheduler's `BackgroundScheduler` gives us cron-like scheduling with 5 lines of code.

### Q: "Why JWT over session cookies?"
**A:** Decoupled frontend (Vercel) and backend (Render) — different domains. Session cookies require `SameSite=None` + complex CORS. JWTs in `Authorization` headers work cleanly across origins. Trade-off: JWTs can't be server-side revoked without a blacklist; we accept this since tokens expire in 24h.

### Q: "Why localStorage for tokens?"
**A:** Simpler than httpOnly cookies for a cross-origin SPA. XSS risk is mitigated by: (1) Next.js auto-escapes JSX, (2) no `dangerouslySetInnerHTML` on user input, (3) CSP headers on Vercel. For a portfolio project, this is an acceptable trade-off over the complexity of a BFF (Backend-For-Frontend) cookie proxy.

### Q: "How do you prevent abuse?"
**A:** Three layers:
1. **Admin approval:** New users can't access the app until manually approved
2. **Rate throttling:** Follow-ups limited to 1/minute via APScheduler's steady drip
3. **Scope isolation:** Users only see/modify their own data (row-level filtering on `user_id`)

### Q: "Why prompt engineering over fine-tuning for email generation?"
**A:** Fine-tuning requires curated training data (hundreds of labeled email pairs) and ongoing model management. Prompt engineering with `gemini-2.5-flash-lite` gives us 90% of the quality at 0% of the training cost. The role-specific `role_configs` dict acts as a lightweight "soft fine-tune" — it injects domain vocabulary and category guidance without model modification.

### Q: "What happens if the LLM hallucinates?"
**A:** Three-layer defense:
1. **Prompt rules:** "DO NOT hallucinate projects, metrics, or experiences I do not have"
2. **Factual grounding:** User's `profile_text` is injected as the only source of truth
3. **Post-processing regex:** Catch-all `\[.*?\]` strips any remaining placeholder artifacts

---

## 12. Environment Variables Reference

### Backend (Render)
| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | SQLite/Postgres connection | `sqlite:///./autoref.db` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIza...` |
| `GOOGLE_CLIENT_ID` | OAuth Client ID | `123...apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | OAuth Client Secret | `GOCSPX-...` |
| `GOOGLE_REDIRECT_URI` | Gmail OAuth callback URL | `https://api.example.com/api/auth/gmail/callback` |
| `JWT_SECRET_KEY` | JWT signing secret | Random 64-char string |
| `ADMIN_EMAIL` | Auto-approved admin email | `you@gmail.com` |
| `FRONTEND_URL` | Frontend origin for CORS | `https://app.vercel.app` |

### Frontend (Vercel)
| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google Sign-In button |

---

*Document generated: May 18, 2026 | AutoRef v1.0.0*
