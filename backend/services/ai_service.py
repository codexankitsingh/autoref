"""
AI Service — JD Parsing & Email Generation using Google Gemini.
Uses the new google-genai SDK with retry logic for free-tier rate limits.
"""
import json
import time
from google import genai
from config import get_settings


class AIService:
    """Handles all AI-powered operations using Google Gemini."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    @property
    def client(self):
        """Lazy-load the Gemini client."""
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    def _call_gemini(self, prompt: str, model_name: str = "gemini-2.5-flash-lite", max_retries: int = 3) -> str:
        """Make a Gemini API call with retry logic for rate limits."""
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                return response.text.strip()
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait_time = 8 * (2 ** attempt)  # 8s, 16s, 32s
                    print(f"Rate limited (attempt {attempt + 1}/{max_retries}). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
        raise Exception("Max retries exceeded for Gemini API")

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
        except Exception as e:
            print(f"JD parsing error: {e}")
            raise Exception(f"Failed to extract JD information: {e}")

    def generate_email(self, jd_data: dict, user_profile: str = "", model_name: str = "gemini-2.5-flash-lite", target_role: str = "Backend/SDE") -> dict:
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

        profile_context = ""
        if user_profile:
            profile_context = f"""
About the sender (use this to personalize the email):
{user_profile}
"""

        resume_links = {
            "Data Engineering": "https://drive.google.com/file/d/1NimIic50phQlXbFKRggrmViKwoREgcdw/view?usp=sharing",
            "Fintech": "https://drive.google.com/file/d/1CXlPUQJgoJ_STt8eWmTpvj_FVbyv9ZhK/view?usp=sharing",
            "Backend/SDE": "https://drive.google.com/file/d/1rfnQ_-_5BtZdZg1dL8ylVrQDgG_B5RXS/view?usp=sharing",
        }
        resume_link = resume_links.get(target_role, resume_links["Backend/SDE"])

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
                    '  <li><b>[Data Pipeline Architecture]:</b> [Extract exactly 1 achievement from my profile related to ETL/ELT pipelines, Airflow DAGs, data ingestion at scale, or pipeline orchestration. Include volume metrics (GB/day) if available.]</li>\n'
                    '  <li><b>[Spark & Cloud Optimization]:</b> [Extract exactly 1 achievement related to PySpark optimization, Dataproc/Databricks, partitioning strategies, query optimization, or cloud cost reduction. Include quantified improvements.]</li>\n'
                    '  <li><b>[Data Modeling & Quality]:</b> [Extract exactly 1 achievement related to SCD Type 2, idempotent processing, BigQuery/data warehouse design, data quality guarantees, or historical consistency.]</li>'
                ),
                "subject_examples": (
                    f'   - "IIIT Gwalior \'26 — interested in {role} at {company}"\n'
                    f'   - "Rakuten DE Intern | Referral Request for {role}, {company}"\n'
                    f'   - "Data Eng with Pipeline & Spark Experience — {company} {role}"'
                ),
                "emphasis": "Prioritize highlighting data engineering work: large-scale data pipelines, Spark/PySpark, Airflow orchestration, data warehouse design, SCD strategies, idempotent processing, and cloud infrastructure optimization (GCP/AWS). Frame everything through a data reliability and scale lens.",
            },
        }

        config = role_configs.get(target_role, role_configs["Backend/SDE"])

        dynamic_format = f"""
Format to follow EXACTLY (Use HTML tags):
<p>Hi Name,</p>

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
<a href="https://www.linkedin.com/in/ankit-kumar-singh-37450422a/" style="color: #2563eb; text-decoration: none;">LinkedIn</a> | <a href="https://www.github.com/codexankitsingh" style="color: #2563eb; text-decoration: none;">GitHub</a></p>
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
1. Preserve the EXACT HTML structure above. Do NOT add extra paragraphs, greetings, or filler.
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
            return {
                "subject": result.get("subject", f"Referral Request - {role} at {company}"),
                "body": result.get("body", ""),
            }
        except Exception as e:
            print(f"Email generation error: {e}")
            raise Exception(f"Failed to generate custom email body: {e}")

    def generate_follow_up(self, original_email: str, follow_up_number: int, model_name: str = "gemini-2.5-flash-lite", original_sent_date: str = "", open_count: int = 0) -> str:
        """
        Generate a follow-up email based on the original.
        Returns: follow-up email body (<80 words)
        """
        # Provide the actual date so the LLM never needs to guess
        date_context = ""
        if original_sent_date:
            date_context = f"\nThe original email was sent on: {original_sent_date}\n"

        # Open-rate awareness context
        open_context = ""
        if open_count > 0:
            open_context = "CRITICAL INSIGHT: The recruiter opened the previous email but did not reply. They likely saw it on their phone while busy and forgot to respond when they got to their desk. Frame the follow-up as a quick bump to the top of their inbox in case they missed it earlier or were on the go."
        else:
            open_context = "CRITICAL INSIGHT: The recruiter has NOT opened the previous email yet. Try a slightly different, catchy angle to get their attention, while remaining highly professional."

        prompt = f"""Write a polite follow-up email (follow-up #{follow_up_number}).

Original email that was sent:
{original_email}
{date_context}

{open_context}

Rules:
1. Maximum 80 words
2. Be polite and not pushy
3. Reference the original email briefly
4. Don't repeat the same content
5. If follow-up #1: gentle reminder
6. Output the email body in valid HTML utilizing <p> and <br> tags where necessary. Include an HTML sign-off matching the original sender. Do NOT use markdown.
7. CRITICAL: You have ALL the information you need above. You MUST use the actual values provided. NEVER use square bracket placeholders like [Date], [Company], or ANY text wrapped in square brackets []. If you truly cannot find a value, omit that reference entirely.
8. When referring to when the original email was sent, use phrases like "my recent email" or "a few days ago" instead of trying to insert a specific date. Do not explicitly say "I saw you opened my email".

Return ONLY the HTML email body text, no JSON, no formatting wrappers.
"""
        try:
            result = self._call_gemini(prompt, model_name=model_name)
            # Post-process: strip ANY remaining [placeholder] artifacts the LLM may have left.
            # This is a catch-all safety net — matches anything inside square brackets.
            import re
            result = re.sub(r'\[.*?\]', '', result)
            # Clean up any double spaces or orphaned punctuation from removal
            result = re.sub(r'  +', ' ', result)
            result = re.sub(r' titled ""', '', result)
            result = re.sub(r'sent on\s*\.', 'sent previously.', result)
            result = re.sub(r'from\s*regarding', 'regarding', result)
            result = re.sub(r'email from\s*regarding', 'email regarding', result)
            result = re.sub(r'my email\s*regarding', 'my previous email regarding', result)
            return result.strip()
        except Exception as e:
            print(f"Follow-up generation error: {e}")
            if follow_up_number == 1:
                return "Hi, I wanted to follow up on my previous email regarding the referral request. I'm still very interested in the role and would appreciate any help. Thank you!"
            elif follow_up_number == 2:
                return "Hi, I hope you're doing well. I wanted to check in once more about the referral request I sent earlier. I remain very interested in this opportunity. Please let me know if you'd be able to help. Thanks!"
            else:
                return "Hi, I understand you're busy, so this will be my last follow-up. If you're able to provide a referral, I'd be truly grateful. Either way, thank you for your time!"

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
