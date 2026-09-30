"""
AI Service — JD Parsing & Email Generation using Google Gemini.
Uses the new google-genai SDK with retry logic for free-tier rate limits.
"""
import json
import re
from html import unescape
from config import get_settings
from services.llm_client import LLMAccessDeniedError, LLMConfigurationError, generate_text
from services.jd_heuristics import parse_jd_heuristic
from services.profile_defaults import resolve_profile_text
from services.outreach_constants import TARGET_ROLE, normalize_target_role
from services.email_quality import (
    finalize_generated_email,
    has_placeholder_tokens,
    normalize_jd_fields,
    recipient_greeting,
)

HUMAN_OUTREACH_VOICE = """
Voice (critical — must sound like a sharp engineer wrote this in 8 minutes, not a marketing bot):
- Short sentences. One clear idea per sentence. No filler adjectives ("incredibly", "passionate", "excited").
- NEVER use: "Quick context on why I'd be a strong fit", "I'm reaching out regarding", "directly aligns with your focus on",
  "I would be incredibly grateful", "hop on a brief call", "Looking forward to hearing from you!"
- Open with who you are + the exact job title at the company + ONE concrete overlap (stack, scale, or domain from the JD).
- Bullets: start with a 2–5 word bold hook (e.g. <b>Rakuten scale:</b>, <b>Airflow ELT:</b>) — NOT long template category names.
- Close for a hiring manager or recruiter: resume link + interest in a brief conversation or clear next step (screening call, application link). Do NOT ask for a "referral" or "intro to the hiring manager" — they ARE the hiring side.
- Use straight ASCII hyphens (-), not special dash characters.
- Copy the job title EXACTLY from "Exact Job Title" below (including location suffixes like "- India"). Never truncate.
- Company name must use proper capitalization (e.g. Philips, not philips).
"""

_DEFAULT_SIGNOFF_HTML = (
    '<p>Best regards,<br>\n'
    'Ankit Kumar Singh<br>\n'
    '+91 9451184789<br>\n'
    '<a href="https://www.linkedin.com/in/ankit-kumar-singh-37450422a/" style="color: #2563eb; text-decoration: none;">LinkedIn</a> | '
    '<a href="https://github.com/codexankitsingh" style="color: #2563eb; text-decoration: none;">GitHub</a></p>'
)

_PLACEHOLDER_GREETING_RE = re.compile(r"\bHi\s+Name\s*,", re.IGNORECASE)
_BRACKET_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
_CURLY_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")
_ANGLE_PLACEHOLDER_RE = re.compile(
    r"<\s*(?:insert|placeholder|company name|your name|recruiter name|hiring manager|date here)[^>]*>",
    re.IGNORECASE,
)


def _strip_html_to_text(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.DOTALL)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _extract_signoff_html(original_email: str) -> str:
    match = re.search(
        r"(<p>\s*Best regards,.*?</p>)",
        original_email,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else _DEFAULT_SIGNOFF_HTML


def _first_name(full_name: str) -> str:
    name = (full_name or "").strip()
    if not name or name.lower() in {"name", "recruiter", "hiring manager"}:
        return ""
    return name.split()[0]


def _extract_follow_up_context(
    original_email: str,
    original_subject: str = "",
    recipient_name: str = "",
    company: str = "",
    role: str = "",
) -> dict:
    plain = _strip_html_to_text(original_email)
    ctx = {
        "company": (company or "").strip(),
        "role": (role or "").strip(),
        "recipient_name": (recipient_name or "").strip(),
        "greeting": "Hi,",
    }

    first = _first_name(ctx["recipient_name"])
    if first:
        ctx["greeting"] = f"Hi {first},"

    role_company = re.search(
        r"regarding the (.+?) opportunity at (.+?)(?:,|\.|\s+as|\s+and|\s+—|\s+-)",
        plain,
        flags=re.IGNORECASE,
    )
    if role_company:
        ctx["role"] = role_company.group(1).strip()
        if not ctx["company"]:
            ctx["company"] = role_company.group(2).strip()

    if not ctx["company"]:
        bold_company = re.search(r"at <b>([^<]+)</b>", original_email, flags=re.IGNORECASE)
        if bold_company:
            ctx["company"] = bold_company.group(1).strip()

    if not ctx["role"] and original_subject:
        subj = original_subject.replace("Re:", "").strip()
        at_match = re.search(r"\bat\s+(.+?)(?:\s*[|—-]|$)", subj, flags=re.IGNORECASE)
        if at_match and not ctx["company"]:
            ctx["company"] = at_match.group(1).strip()
        for_match = re.search(
            r"(?:for|interested in)\s+(.+?)\s+at\s+",
            subj,
            flags=re.IGNORECASE,
        )
        if for_match and not ctx["role"]:
            ctx["role"] = for_match.group(1).strip()

    return ctx


def _sanitize_follow_up_body(text: str, context: dict) -> str:
    greeting = context.get("greeting") or "Hi,"
    text = _PLACEHOLDER_GREETING_RE.sub(greeting, text)
    text = _BRACKET_PLACEHOLDER_RE.sub("", text)
    text = _CURLY_PLACEHOLDER_RE.sub("", text)
    text = _ANGLE_PLACEHOLDER_RE.sub("", text)

    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"  +", " ", text)
    text = re.sub(r' titled ""', "", text)
    text = re.sub(r"sent on\s*\.", "sent previously.", text)
    text = re.sub(r"from\s+regarding", "regarding", text)
    text = re.sub(r"email from\s+regarding", "email regarding", text)
    text = re.sub(r"my email\s+regarding", "my previous email regarding", text)
    text = re.sub(r"regarding the\s+,", "regarding the role,", text)
    text = re.sub(r"at\s+,", "at your organization,", text)
    text = re.sub(r"<p>\s*</p>", "", text, flags=re.IGNORECASE)
    return text.strip()


def _deterministic_follow_up_html(follow_up_number: int, context: dict, signoff_html: str) -> str:
    greeting = context.get("greeting") or "Hi,"
    company = context.get("company") or "your organization"
    role = context.get("role") or "the position I mentioned"

    if follow_up_number == 1:
        body = (
            f"<p>{greeting}</p>"
            f"<p>Bumping my note on the {role} role at {company} — still very interested. "
            f"If it's easier to review async, I can send a short summary of my Rakuten pipeline work — otherwise happy to find time for a quick call.</p>"
        )
    elif follow_up_number == 2:
        body = (
            f"<p>{greeting}</p>"
            f"<p>Quick follow-up on {role} at {company}. Happy to send a one-pager on my Rakuten pipeline work if useful.</p>"
        )
    else:
        body = (
            f"<p>{greeting}</p>"
            f"<p>Last note from me on {role} at {company}. If timing isn't right, no worries — thanks for reading.</p>"
        )
    return f"{body}\n{signoff_html}"


class AIService:
    """Handles all AI-powered operations using Google Gemini."""

    def __init__(self):
        self.settings = get_settings()

    def _call_gemini(self, prompt: str, model_name: str = "gemini-2.5-flash-lite", max_retries: int = 3) -> str:
        """Route to unified LLM client (Gemini + OpenAI fallback)."""
        return generate_text(prompt, model_name=model_name, max_retries=max_retries)

    def _parse_json_response(self, text: str) -> dict:
        """Parse JSON from Gemini response, handling markdown code blocks and conversational text."""
        text = text.strip()
        
        # Try finding the first { and the last }
        start = text.find("{")
        end = text.rfind("}")
        
        if start != -1 and end != -1:
            try:
                # Extract the pure JSON substring
                json_str = text[start:end+1]
                return json.loads(json_str)
            except Exception as e:
                print(f"JSON regex extraction failed: {e}")
                
        # Ultimate fallback
        return json.loads(text)

    def parse_jd(self, jd_text: str, model_name: str = "gemini-2.5-flash-lite") -> dict:
        """
        Parse a job description to extract structured fields.
        Returns: {"company": str, "role": str, "skills": list[str], "location": str}
        """
        prompt = f"""Analyze this job description and extract the following information.
Return ONLY a valid JSON object with these exact keys, no markdown formatting, no code blocks:

{{
  "company": "company name or null if not found",
  "role": "job title/role or null if not found",
  "skills": ["skill1", "skill2", "skill3"],
  "location": "location or null if not found",
  "job_id": "Job ID or Requisition code or null if not found",
  "job_link": "HTTP URL to the job posting if found, else null"
}}

Rules:
- Extract the top 5-8 most important technical skills
- If company name is not explicitly mentioned, try to infer from context
- For role, use the FULL exact job title from the posting (include qualifiers like Senior, location suffix "- India", requisition text). Never shorten to a single letter.
- Company: use standard brand capitalization (Philips, Amazon, not lowercase)
- Return null (not "null") for missing fields

Job Description:
{jd_text}
"""
        try:
            text = self._call_gemini(prompt, model_name=model_name)
            parsed = self._parse_json_response(text)
            return normalize_jd_fields(
                {
                    "company": parsed.get("company"),
                    "role": parsed.get("role"),
                    "skills": parsed.get("skills", []),
                    "location": parsed.get("location"),
                    "job_id": parsed.get("job_id"),
                    "job_link": parsed.get("job_link"),
                }
            )
        except (LLMAccessDeniedError, LLMConfigurationError) as e:
            print(f"LLM unavailable for JD parse ({e}); using heuristic fallback.")
            return normalize_jd_fields(parse_jd_heuristic(jd_text))
        except Exception as e:
            print(f"JD parsing error: {e}")
            print("Using heuristic JD parser fallback.")
            return normalize_jd_fields(parse_jd_heuristic(jd_text))

    def generate_email(
        self,
        jd_data: dict,
        user_profile: str = "",
        model_name: str = "gemini-2.5-flash-lite",
        target_role: str = TARGET_ROLE,
        recipient_name: str | None = None,
    ) -> dict:
        """
        Generate a tailored referral email based on JD and user profile.
        Returns: {"subject": str, "body": str}
        """
        target_role = normalize_target_role(target_role)
        company = jd_data.get("company") or "the company"
        role = jd_data.get("role") or "the position"
        skills = ", ".join(jd_data.get("skills", []))
        location = jd_data.get("location", "")
        job_id = jd_data.get("job_id")
        job_link = jd_data.get("job_link")

        job_context_html = ""
        if job_id or job_link:
            job_context_html = "<p>For your reference, here is the job I am referring to:<br>\n"
            if job_id:
                job_context_html += f"Job ID: <b>{job_id}</b><br>\n"
            if job_link:
                job_context_html += f"Link: <a href=\"{job_link}\">Job Posting</a><br>\n"
            job_context_html += "</p>\n"

        user_profile = resolve_profile_text(user_profile, target_role)

        profile_context = ""
        if user_profile:
            profile_context = f"""
About the sender (use this to personalize the email — ONLY use facts from this text):
{user_profile}
"""
        else:
            profile_context = """
About the sender: Profile not configured. Use only generic Data Engineering framing; do not invent employers or metrics.
"""

        resume_link = self.settings.resume_link_data_engineering
        greeting_line = recipient_greeting(recipient_name)
        sender_title = "Associate Data Engineer at Rakuten India"
        bullet_guidance = (
            '  <li><b>[Short hook, e.g. Rakuten scale / Loyalty pipelines]:</b> [One production win: Points platform 100M+ tx/day, 120-150 GB/day ingestion, idempotent upserts, SCD2, schema evolution — only facts from profile.]</li>\n'
            '  <li><b>[Short hook, e.g. Airflow ELT / Cloud migration]:</b> [One win on Airflow-orchestrated GCS→PySpark→BigQuery, DpaaS migration, or ~30-40% runtime/cost improvements — match JD stack words.]</li>\n'
            '  <li><b>[Short hook, e.g. Kafka CDC / Reliability]:</b> [One win: Kafka/Debezium, Iceberg streaming, dbt lakehouse project, or Auto-RCA cutting on-call triage from 25-30 min — pick what the JD cares about most.]</li>'
        )
        subject_examples = (
            f'   - "Rakuten DE — {role} at {company}"\n'
            f'   - "IIIT Gwalior \'26 | {role}, {company}"\n'
            f'   - "Airflow/Spark/BQ — {company} {role}"'
        )
        role_emphasis = (
            "Sender is Associate Data Engineer at Rakuten India (full-time, promoted from intern). "
            "Lead with production ownership, batch + streaming ELT, and GCP (BigQuery, Dataproc, GCS). "
            "Highlight migration/modernization (Hadoop→DpaaS, Iceberg), Airflow operations, Kafka CDC when relevant, "
            "and reliability (DQ, idempotent upserts, SCD2, on-call/Auto-RCA). "
            "Mention IIIT Gwalior '26 when the JD is junior/new-grad friendly."
        )

        dynamic_format = f"""
Format to follow EXACTLY (Use HTML tags):
<p>{greeting_line}</p>

<p>I'm Ankit — {sender_title} (IIIT Gwalior '26). I'm writing about the <b>{role}</b> role at <b>{company}</b>. [One sentence: tie a specific JD requirement to a specific production or project outcome from my profile — no buzzwords.]</p>

<p>A few things that line up with the role:</p>
<ul style="margin-top: 0; padding-left: 20px;">
{bullet_guidance}
</ul>

{job_context_html}
<p>My resume is <a href="{resume_link}">here</a>. I'd welcome a brief conversation about fit for the role — happy to align on timing for a call or whatever the next step is on your side.</p>

<p>Best regards,<br>
Ankit Kumar Singh<br>
+91 9451184789<br>
<a href="https://www.linkedin.com/in/ankit-kumar-singh-37450422a/" style="color: #2563eb; text-decoration: none;">LinkedIn</a> | <a href="https://github.com/codexankitsingh" style="color: #2563eb; text-decoration: none;">GitHub</a></p>
"""

        prompt = f"""You are Ankit Kumar Singh drafting a cold outreach email to a hiring manager or recruiter at {company}.
Write like a strong new-grad engineer: confident, specific, respectful — never salesy or robotic.
Audience is usually the person who can schedule a screen or advance the candidacy — not an employee referral ask.

Context:
- Company: {company}
- Target Role Category: {target_role}
- Exact Job Title: {role}
- Key Skills Required: {skills}
- Location: {location}

About Me (The Sender):
{profile_context}

{dynamic_format}

Data Engineering emphasis:
{role_emphasis}

{HUMAN_OUTREACH_VOICE}

Rules:
1. Preserve the EXACT HTML structure above — including the opening greeting line exactly as shown. Do NOT add extra paragraphs, greetings, or filler.
2. The opening paragraph MUST name the exact job title "{role}" and company "{company}" (proper capitalization).
3. The 3 bullet points MUST be factually extracted from my profile text. DO NOT hallucinate projects, metrics, or experiences I do not have! Match JD keywords (Airflow, Spark, Kafka, BigQuery, etc.) when true.
4. Replace bracketed placeholders with a short bold hook (2-5 words) plus one crisp sentence with a metric where possible.
5. NEVER call me Backend Engineer or SDE Intern — I am Associate Data Engineer at Rakuten India.
6. Subject line rules:
   - Must feel like a human wrote it. Professional but not corporate-generic.
   - Ideal format: "[Credential/Who I Am] — [Role] at [Company]" or "[Stack hint] — [Company] [Role]"
   - DO NOT dump raw metrics or random JD keywords in the subject.
   - DO NOT use clickbait, ALL CAPS, or exclamation marks.
   - DO NOT write generic subjects like "Referral Request" or "Application for SDE Role".
   - Keep it under 60 characters if possible.
   Example forms:
{subject_examples}

Return ONLY a JSON object with exactly these keys:
{{
  "subject": "email subject line",
  "body": "full HTML email body"
}}
"""
        try:
            text = self._call_gemini(prompt, model_name=model_name)
            result = self._parse_json_response(text)
            subject, body = finalize_generated_email(
                result.get("subject", f"{role} at {company} — Rakuten DE"),
                result.get("body", ""),
                recipient_name,
                target_role=target_role,
                company=company,
            )
            return {"subject": subject, "body": body}
        except (LLMAccessDeniedError, LLMConfigurationError):
            raise
        except Exception as e:
            print(f"Email generation error: {e}")
            raise Exception(f"Failed to generate custom email body: {e}") from e

    def generate_follow_up(
        self,
        original_email: str,
        follow_up_number: int,
        model_name: str = "gemini-2.5-flash-lite",
        original_sent_date: str = "",
        open_count: int = 0,
        original_subject: str = "",
        recipient_name: str = "",
        company: str = "",
        role: str = "",
    ) -> str:
        """
        Generate a follow-up email based on the original.
        Returns: follow-up email body (<80 words)
        """
        context = _extract_follow_up_context(
            original_email,
            original_subject=original_subject,
            recipient_name=recipient_name,
            company=company,
            role=role,
        )
        signoff_html = _extract_signoff_html(original_email)
        company_line = context["company"] or "your organization"
        role_line = context["role"] or "the position I mentioned in my earlier note"
        greeting_line = context["greeting"]

        date_context = ""
        if original_sent_date:
            date_context = f"\nThe original email was sent on: {original_sent_date} (refer to it only as 'my recent email' or 'a few days ago').\n"

        open_context = ""
        if open_count > 0:
            open_context = (
                "The recruiter opened the previous email but did not reply. "
                "Use a short professional bump; do not mention that they opened it."
            )
        else:
            open_context = (
                "The recruiter may not have seen the previous email yet. "
                "Stay professional; do not use gimmicky language."
            )

        facts_block = f"""
Use these exact facts (copy wording; do NOT use placeholders or brackets):
- Opening greeting (use exactly): {greeting_line}
- Company: {company_line}
- Role / job title discussed: {role_line}
- Refer to timing only as: "my recent email" or "a few days ago"
"""

        def _build_prompt(strict: bool = False) -> str:
            strict_rules = ""
            if strict:
                strict_rules = """
STRICT MODE: If you cannot write a complete sentence with the facts above, output ONLY the word FALLBACK.
"""
            return f"""Write a polite follow-up email (follow-up #{follow_up_number}).

{facts_block}

Original email that was sent (for tone and sign-off only):
{original_email}
{date_context}

{open_context}

Rules:
1. Maximum 80 words in the body (excluding sign-off).
2. Start with the exact greeting given in facts — never "Hi Name" or generic placeholders.
3. Mention the company and role using the exact fact strings above.
4. Do not repeat the full original email or bullet list.
5. Output valid HTML with <p> tags. End by copying this sign-off block exactly:
{signoff_html}
6. FORBIDDEN: square brackets [], curly braces {{}}, angle placeholders, "TBD", "insert", "your name here", or any template tokens.
7. Do not use markdown.
8. Sound human: no "just circling back", "gentle reminder", "incredibly grateful", or "hope this finds you well". One polite bump + same ask (conversation / next step on the role).
{strict_rules}

Return ONLY the HTML email body text, no JSON, no code fences.
"""

        try:
            for attempt, strict in enumerate((False, True)):
                result = self._call_gemini(_build_prompt(strict=strict), model_name=model_name)
                if strict and result.strip().upper() == "FALLBACK":
                    break
                result = _sanitize_follow_up_body(result, context)
                if not has_placeholder_tokens(result):
                    if signoff_html.lower() not in result.lower():
                        result = f"{result.rstrip()}\n{signoff_html}"
                    return result.strip()
                print(f"Follow-up attempt {attempt + 1} contained placeholders; retrying...")
        except Exception as e:
            print(f"Follow-up generation error: {e}")

        safe = _deterministic_follow_up_html(follow_up_number, context, signoff_html)
        print("Follow-up: using deterministic template (AI output unsafe or failed).")
        return safe

    def categorize_reply(self, reply_text: str, model_name: str = "gemini-2.5-flash-lite") -> str:
        """
        Categorizes an incoming reply from a recruiter into actionable states.
        Returns one of: 'interview_requested', 'referral_provided', 'rejected', 'out_of_office', 'other'
        """
        prompt = f"""You are an AI assistant helping categorize email replies from recruiters.

Read the following email reply and categorize the intent into EXACTLY ONE of the following tags:
- interview_requested : (They want to schedule a call, chat, interview, or sent a calendly link)
- referral_provided : (They provided a referral, sent a unique application link, or passed the resume to a hiring manager)
- rejected : (They are not moving forward, no open roles, or polite decline)
- out_of_office : (Automated OOO, vacation, or no longer at company)
- other : (Any other response, e.g. "I'll look into it", "Apply online normally", or ambiguous)

Reply text:
"{reply_text}"

Return ONLY the exact tag string in lowercase. No other text.
"""
        try:
            result = self._call_gemini(prompt, model_name=model_name).strip().lower()
            valid_tags = ["interview_requested", "referral_provided", "rejected", "out_of_office", "other"]
            if result in valid_tags:
                return result
            # fallback fuzzy matching
            for tag in valid_tags:
                if tag in result:
                    return tag
            return "other"
        except Exception as e:
            print(f"Reply categorization error: {e}")
            return "other"


# Singleton instance
ai_service = AIService()
