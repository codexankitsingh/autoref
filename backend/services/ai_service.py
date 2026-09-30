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
from services.email_quality import (
    finalize_generated_email,
    has_placeholder_tokens,
    recipient_greeting,
)

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
            f"<p>I wanted to gently follow up on my recent email about the {role} opportunity at {company}. "
            f"I'm still very interested and would appreciate any help with a referral or the right hiring contact.</p>"
        )
    elif follow_up_number == 2:
        body = (
            f"<p>{greeting}</p>"
            f"<p>Checking in once more regarding the {role} role at {company}. "
            f"I remain keen to contribute and would value any guidance when you have a moment.</p>"
        )
    else:
        body = (
            f"<p>{greeting}</p>"
            f"<p>I know you're busy — this will be my last note about the {role} opportunity at {company}. "
            f"If a referral is possible, I'd be grateful; otherwise, thank you for your time.</p>"
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
- For role, use the exact job title mentioned
- Return null (not "null") for missing fields

Job Description:
{jd_text}
"""
        try:
            text = self._call_gemini(prompt, model_name=model_name)
            parsed = self._parse_json_response(text)
            return {
                "company": parsed.get("company"),
                "role": parsed.get("role"),
                "skills": parsed.get("skills", []),
                "location": parsed.get("location"),
                "job_id": parsed.get("job_id"),
                "job_link": parsed.get("job_link"),
            }
        except (LLMAccessDeniedError, LLMConfigurationError) as e:
            print(f"LLM unavailable for JD parse ({e}); using heuristic fallback.")
            return parse_jd_heuristic(jd_text)
        except Exception as e:
            print(f"JD parsing error: {e}")
            print("Using heuristic JD parser fallback.")
            return parse_jd_heuristic(jd_text)

    def _resume_links(self) -> dict[str, str]:
        s = self.settings
        return {
            "Data Engineering": s.resume_link_data_engineering,
            "Fintech": s.resume_link_fintech,
            "Backend/SDE": s.resume_link_backend_sde,
            "Systems": s.resume_link_systems,
        }

    def generate_email(
        self,
        jd_data: dict,
        user_profile: str = "",
        model_name: str = "gemini-2.5-flash-lite",
        target_role: str = "Backend/SDE",
        recipient_name: str | None = None,
    ) -> dict:
        """
        Generate a tailored referral email based on JD and user profile.
        Returns: {"subject": str, "body": str}
        """
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
        elif target_role == "Data Engineering":
            profile_context = """
About the sender: Profile not configured. Use only generic Data Engineering framing; do not invent employers or metrics.
"""

        resume_links = self._resume_links()
        resume_link = resume_links.get(target_role, resume_links["Backend/SDE"])
        greeting_line = recipient_greeting(recipient_name)

        # ── Role-specific bullet category guidance & subject line examples ──
        role_configs = {
            "Backend/SDE": {
                "bullet_guidance": (
                    '  <li><b>[API Design / System Architecture]:</b> [Extract exactly 1 achievement from my profile related to backend API design, microservices, REST/gRPC, or system architecture. Include metrics like TPS, latency, or uptime if available.]</li>\n'
                    '  <li><b>[Performance & Scalability]:</b> [Extract exactly 1 achievement related to performance optimization, caching (Redis), database indexing, concurrency handling, or load testing. Include quantified improvements.]</li>\n'
                    '  <li><b>[Problem Solving & CS Fundamentals]:</b> [Extract exactly 1 achievement from my competitive programming stats (LeetCode Knight / Codeforces Specialist), DSA mastery, or relevant CS coursework that demonstrates strong analytical capability.]</li>'
                ),
                "subject_examples": (
                    f'   - "IIIT Gwalior \'26 — interested in {role} at {company}"\n'
                    f'   - "Rakuten SDE Intern | Referral Request for {role}, {company}"\n'
                    f'   - "Backend Eng with API & Systems Experience — {company} {role}"'
                ),
                "emphasis": "Prioritize highlighting backend systems work: API design, database design, caching strategies, auth systems (JWT/OAuth), and any measurable performance/reliability metrics.",
            },
            "Systems": {
                "bullet_guidance": (
                    '  <li><b>[Low-Latency & Performance Optimization]:</b> [Extract exactly 1 achievement related to reducing system latency, profiling code, optimizing memory footprint, high-throughput execution (e.g. TPS metrics), or caching (Redis/custom cache).]</li>\n'
                    '  <li><b>[Concurrency & Distributed Systems]:</b> [Extract exactly 1 achievement related to multi-threading, concurrency control, distributed locking, pub/sub architectures (GCP Pub/Sub/Kafka), or data consistency guarantees.]</li>\n'
                    '  <li><b>[Low-Level Systems Programming / CS Core]:</b> [Extract exactly 1 achievement demonstrating deep systems understanding, Linux internals, C/C++ or Go systems development, or custom socket/network programming.]</li>'
                ),
                "subject_examples": (
                    f'   - "IIIT Gwalior \'26 — interested in {role} at {company}"\n'
                    f'   - "Rakuten Intern | Concurrency \u0026 Systems Experience — {company}"\n'
                    f'   - "Systems/Infrastructure Engineer | Referral Request for {role}, {company}"'
                ),
                "emphasis": "Prioritize highlighting systems infrastructure: multi-threading, high-performance computing, memory management, Linux OS concepts, systems-level languages (C/C++, Go), low-latency networking, custom server setups, and high-concurrency architectures.",
            },
            "Fintech": {
                "bullet_guidance": (
                    '  <li><b>[Payment Systems / Ledger Design]:</b> [Extract exactly 1 achievement from my profile related to payment processing, double-entry ledgers, transaction handling, ACID guarantees, or idempotency keys. Include metrics like TPS or error rates if available.]</li>\n'
                    '  <li><b>[Security & Compliance]:</b> [Extract exactly 1 achievement related to OAuth2, HMAC verification, webhook design with retry/dedup, encryption, audit trails, or compliance-ready failure handling.]</li>\n'
                    '  <li><b>[Reliability & Observability]:</b> [Extract exactly 1 achievement related to fault tolerance, rate limiting, load testing (k6/JMeter), rollback mechanisms, monitoring, or data integrity guarantees.]</li>'
                ),
                "subject_examples": (
                    f'   - "IIIT Gwalior \'26 — interested in {role} at {company}"\n'
                    f'   - "Backend Eng with Payments & Transaction Systems Exp — {company}"\n'
                    f'   - "Referral Request for {role} | Fintech-focused Backend Developer"'
                ),
                "emphasis": "Prioritize highlighting fintech-relevant work: payment processing, ACID transactions, idempotency, webhook delivery, HMAC verification, double-entry accounting, fraud prevention, regulatory compliance, and any work with money-movement systems. Frame backend projects through a financial reliability lens.",
            },
            "Data Engineering": {
                "bullet_guidance": (
                    '  <li><b>[Production Scale & Pipeline Ownership]:</b> [Extract exactly 1 achievement about owning production data pipelines — e.g. Rakuten Points Transaction Platform (100M+ daily transactions), schema evolution, late data, partitioning, deduplication, or Spark shuffle/partition tuning. Use real metrics from the profile only.]</li>\n'
                    '  <li><b>[ELT / Orchestration & Cloud Migration]:</b> [Extract exactly 1 achievement about Airflow-orchestrated ELT (120–150 GB/day GCS→Dataproc PySpark→BigQuery), Hadoop→DpaaS/OneCloud migration (Spark, Iceberg, BigQuery, GCS), SPDB Airflow 3.2 migration, or automated DQ/dependency checks. Match the JD stack (Airflow, Spark, BQ, Iceberg) when possible.]</li>\n'
                    '  <li><b>[Streaming, Lakehouse, or Reliability Tooling]:</b> [Extract exactly 1 achievement best aligned with the JD: Kafka/Debezium CDC, StreamLake (Iceberg MERGE, exactly-once), SaleStream (dbt, star schema, SCD2), Dataproc cost cut (~30%), or Auto-RCA agent (Airflow failure RCA, MTTR 25–30 min → minutes). Prefer the project/skill the JD emphasizes most.]</li>'
                ),
                "subject_examples": (
                    f'   - "IIIT Gwalior \'26 — {role} at {company}"\n'
                    f'   - "Rakuten Associate DE | Referral for {role}, {company}"\n'
                    f'   - "Spark/Airflow/BQ pipelines — {company} {role}"'
                ),
                "emphasis": (
                    "Sender is Associate Data Engineer at Rakuten India (promoted from intern), NOT an SDE intern. "
                    "Lead with production ownership, batch + streaming ELT, and GCP (BigQuery, Dataproc, GCS). "
                    "Highlight migration/modernization (Hadoop→DpaaS, Iceberg), Airflow operations, Kafka CDC when relevant, "
                    "and reliability (DQ, idempotent upserts, SCD2, on-call/Auto-RCA) — not generic 'interested in data' fluff. "
                    "For junior/new-grad DE roles, mention IIIT Gwalior '26 and hands-on Rakuten production experience."
                ),
            },
        }

        config = role_configs.get(target_role, role_configs["Backend/SDE"])

        dynamic_format = f"""
Format to follow EXACTLY (Use HTML tags):
<p>{greeting_line}</p>

<p>I'm Ankit, a [Current Role from profile] at <b>[Current Company]</b> (IIIT Gwalior'26). I'm reaching out regarding the {role} opportunity at {company}, as my experience with [Specific capability from your profile] directly aligns with your focus on [Specific technical challenge or goal from the JD].</p>

<p>Quick context on why I'd be a strong fit:</p>
<ul style="margin-top: 0; padding-left: 20px;">
{config["bullet_guidance"]}
</ul>

{job_context_html}
<p>I've included my <a href="{resume_link}">resume here</a> for your reference. I would be incredibly grateful if you'd be open to referring me for a relevant position, or connecting me with the appropriate hiring team. I would welcome the opportunity to hop on a brief call to discuss further. Looking forward to hearing from you!</p>

<p>Best regards,<br>
Ankit Kumar Singh<br>
+91 9451184789<br>
<a href="https://www.linkedin.com/in/ankit-kumar-singh-37450422a/" style="color: #2563eb; text-decoration: none;">LinkedIn</a> | <a href="https://github.com/codexankitsingh" style="color: #2563eb; text-decoration: none;">GitHub</a></p>
"""

        prompt = f"""You are writing a highly targeted cold outreach email for a recruiter at {company}.
Your job is to analyze the job description and my profile to write an email that maximizes reply probability.

Context:
- Company: {company}
- Target Role Category: {target_role}
- Exact Job Title: {role}
- Key Skills Required: {skills}
- Location: {location}

About Me (The Sender):
{profile_context}

{dynamic_format}

Role-specific emphasis:
{config["emphasis"]}

Rules:
1. Preserve the EXACT HTML structure above — including the opening greeting line exactly as shown. Do NOT add extra paragraphs, greetings, or filler.
2. The 1-sentence personalization MUST bridge a specific need in the JD with a specific capability in my profile.
3. The 3 bullet points MUST be factually extracted from my profile text. DO NOT hallucinate projects, metrics, or experiences I do not have! If the JD asks for C++, explicitly highlight my C++ skills. If it asks for PySpark, highlight PySpark. Select the projects from my profile that are the BEST fit for this specific job.
4. Replace bracketed placeholders like [Category 1] with an actionable, bolded category name related to the bullet point (e.g. <b>At Rakuten (Systems):</b> or <b>DSA & Algorithms:</b>).
5. Subject line rules:
   - Must feel like a human wrote it. Professional but not corporate-generic.
   - Ideal format: "[Credential/Who I Am] — [What I want] at [Company]" or "[Credential] | Referral Request for [Role], [Company]"
   - DO NOT dump raw metrics (e.g. "800+ TPS") or random JD keywords in the subject.
   - DO NOT use clickbait, ALL CAPS, or exclamation marks.
   - DO NOT write generic subjects like "Referral Request" or "Application for SDE Role".
   - Keep it under 60 characters if possible.
   Example forms:
{config["subject_examples"]}

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
                result.get("subject", f"Referral Request - {role} at {company}"),
                result.get("body", ""),
                recipient_name,
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
