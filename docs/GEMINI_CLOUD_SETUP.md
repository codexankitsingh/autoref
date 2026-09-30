# Gemini API (AQ. keys) — Cloud & Render checklist

AutoRef uses the **native** Gemini API (`generativelanguage.googleapis.com`) via `google-genai` and `GEMINI_API_KEY`.

## AQ. vs AIza

New keys from [Google AI Studio](https://aistudio.google.com/apikey) start with **`AQ.`** — this is correct. Old **`AIzaSy`** keys are being phased out.

## Error: `403 PERMISSION_DENIED — Your project has been denied access`

This comes **from Google**, not from missing Render env vars. A new `AQ.` key in the **same blocked Cloud project** will still fail.

### Fix (in order)

1. **New Cloud project**
   - AI Studio → **Create API key** → choose **Create project** (new name), not an existing project.

2. **Enable the API**
   - Open [Generative Language API](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com) for that project → **Enable**.

3. **Billing**
   - [Cloud Billing](https://console.cloud.google.com/billing) → link a billing account to the project (many accounts require this even for free Gemini quota).

4. **Key restrictions**
   - [Credentials](https://console.cloud.google.com/apis/credentials) → your API key → **API restrictions** → **Restrict key** → select **Generative Language API**.

5. **Render (backend only)**
   - Service: **autoref-api** (Python), not the Vercel frontend.
   - Environment → `GEMINI_API_KEY` = paste full key (no quotes, no spaces).
   - Optional: `OPENAI_API_KEY` for fallback.
   - **Save** → **Manual Deploy** → clear build cache if the old key was cached in logs only (env is read at runtime).

6. **Verify**
   - Log in to the app → **Settings** → **AI engine** banner should show green when Gemini works.
   - Or call `GET /api/ai-health` with your JWT.

### Gmail OAuth is separate

`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` are for **Gmail send**. They do **not** replace `GEMINI_API_KEY` for email generation.

### Still blocked?

- Try a **different Google account** and new project.
- [Google AI Developers Forum](https://discuss.ai.google.dev/) — search “project has been denied access”.
- Use **OpenAI fallback**: `OPENAI_API_KEY` on Render + **OpenAI GPT-4o mini** on the compose page.
