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
from services.de_email_builder import assemble_de_email, validate_de_email_facts
from services.email_quality import (
    finalize_generated_email,
    has_placeholder_tokens,
    normalize_jd_fields,
    recipient_greeting,
    validate_outbound_email,
)

HUMAN_OUTREACH_VOICE = """
Voice (critical — must sound like a sharp engineer wrote this in 8 minutes, not a marketing bot):
- Short sentences. One clear idea per sentence. No filler adjectives ("incredibly", "passionate", "excited").
- NEVER use: "Quick context on why I'd be a strong fit", "I'm reaching out regarding", "directly aligns with your focus on",
  "I would be incredibly grateful", "hop on a brief call", "Looking forward to hearing from you!"
- Opening paragraph: who you are + exact role at company + ONE sharp differentiator (pick the best JD fit): loyalty-scale distributed systems (100M+ tx/day), multi-cloud (GCP+AWS), real-time Kafka/CDC, cost/runtime optimization (~30%), peer-review research/Auto-RCA, or strong CS/algorithms (LeetCode Knight) — NOT a generic "I built an Airflow pipeline that ingests X GB".
- Do NOT open with only batch ELT volume; save pipeline mechanics for bullets.
- Use cloud/stack names from the profile (GCP, BigQuery, Dataproc, GCS, Kafka). Never invent S3/Redshift/Snowflake unless they appear in the JD AND you honestly map from equivalent GCP/AWS experience in the profile.
- Bullets: start with a 2–5 word bold hook (e.g. <b>Rakuten scale:</b>, <b>Airflow ELT:</b>) — NOT long template category names.
- Close for a hiring manager or recruiter: resume link + interest in a brief conversation or clear next step (screening call, application link). Do NOT ask for a "referral" or "intro to the hiring manager" — they ARE the hiring side.
- Use straight ASCII hyphens (-), not special dash characters.
- Copy the job title EXACTLY from "Exact Job Title" below (including location suffixes like "- India"). Never truncate.
- Company name must use proper capitalization (e.g. Philips, not philips).
"""

RESEARCH_PRESENTATION = """
Peer-review research (use when JD touches reliability, observability, on-call, ML on data platforms, or Airflow ops):
- Frame as production impact first, publication second — e.g. "I built and studied an LLM RCA system on 364 live Airflow failures (96% actionable per senior engineers); that work is under peer review."
- Good one-liner for opening OR bullet: "Alongside pipeline ownership, I shipped an Auto-RCA agent (peer-review research) that pulls Airflow on-call triage from ~25–30 minutes down to minutes on eligible reruns."
- Avoid: "industry grade paper", "published paper" (not published yet), long methodology, or listing co-authors in a cold email.
- Prefer one crisp clause in the opening when reliability/ML is in the JD; otherwise put the full research bullet in slot 3 with the 364 / 96% metrics.
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
        subject_examples = (
            f'   - "Rakuten DE — {role} at {company}"\n'
            f'   - "IIIT Gwalior \'26 | {role}, {company}"\n'
            f'   - "Airflow/Spark/BQ — {company} {role}"'
        )

        try:
            last_issues: list[str] = []
            for attempt in range(2):
                strict_block = ""
                if attempt == 1:
                    strict_block = f"""
STRICT RETRY — prior draft failed: {'; '.join(last_issues)}
Fix every issue. Do not mention Redshift/Snowflake. Do not say Hi Ankit. Include peer review + 364 failures + 100M+ tx/day.
"""
                prompt = f"""You draft a cold email from Ankit Kumar Singh (Associate Data Engineer, Rakuten India) to a hiring manager/recruiter at {company}.
Write one coherent story — confident, specific, human. No buzzword salad or contradictory clouds.

Job context:
- Exact title: {role}
- Company: {company}
- Skills in JD: {skills}
- Location: {location}

Profile (ONLY use facts from here):
{profile_context}

{HUMAN_OUTREACH_VOICE}

{RESEARCH_PRESENTATION}

Narrative rules:
1. You OWN production data systems at Rakuten — loyalty/points platform (100M+ transactions/day) plus 120-150 GB/day ELT on GCP. Never frame yourself as owning only one ingestion pipeline.
2. GCP bullet: Airflow, PySpark/Dataproc, BigQuery, GCS, ~30% cost optimization, Kafka CDC when relevant. Do NOT put AWS Redshift/Snowflake/Databricks in the GCP bullet.
3. AWS appears only if you mention the StreamLake side project separately — never "GCP Dataproc + AWS Redshift" in one breath.
4. Research bullet is mandatory: Auto-RCA RAG for Airflow, 364 production failures, 96% actionable, deployed in prod, work currently under peer review (not published). Use ~25-30 min to minutes for triage — never "70% MTTR".
5. opening_paragraph is plain text (no HTML, no greeting line — greeting is added separately as: {greeting_line!r}).

Subject line rules:
{subject_examples}

{strict_block}

Return ONLY JSON with these keys (no markdown):
{{
  "subject": "string",
  "opening_paragraph": "plain text, 2-3 sentences",
  "bullet_production": "HTML fragment: <b>Production at Rakuten:</b> ...",
  "bullet_gcp_platform": "HTML fragment: <b>GCP data platform:</b> ...",
  "bullet_research": "HTML fragment: <b>Peer-review research:</b> ... must say under peer review"
}}
"""
                text = self._call_gemini(prompt, model_name=model_name)
                result = self._parse_json_response(text)
                body = assemble_de_email(
                    greeting_line=greeting_line,
                    opening_paragraph=result.get("opening_paragraph", ""),
                    bullet_production=result.get("bullet_production", ""),
                    bullet_gcp_platform=result.get("bullet_gcp_platform", ""),
                    bullet_research=result.get("bullet_research", ""),
                    resume_link=resume_link,
                    job_context_html=job_context_html,
                )
                subject, body = finalize_generated_email(
                    result.get("subject", f"{role} at {company} — Rakuten DE"),
                    body,
                    recipient_name,
                    target_role=target_role,
                    company=company,
                )
                last_issues = validate_outbound_email(subject, body) + validate_de_email_facts(
                    body, recipient_name
                )
                if not last_issues:
                    return {"subject": subject, "body": body}
                print(f"Email attempt {attempt + 1} failed checks: {last_issues}")

            raise Exception(
                "Generated email failed quality checks: " + " ".join(last_issues)
            )
        except (LLMAccessDeniedError, LLMConfigurationError):
            raise
        except Exception as e:
            if str(e).startswith("Generated email failed quality checks"):
                raise
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
