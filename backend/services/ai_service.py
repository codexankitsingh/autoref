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
        """Parse JSON from Gemini response, handling markdown code blocks."""
        # Strip markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        text = text.strip()
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
            return {
                "company": None,
                "role": None,
                "skills": [],
                "location": None,
                "job_id": None,
                "job_link": None,
            }

    def generate_email(self, jd_data: dict, user_profile: str = "", model_name: str = "gemini-2.5-flash-lite") -> dict:
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

        prompt = f"""You are writing a highly targeted cold outreach email for a recruiter at {company}.
Your job is to analyze the job description and my profile to write an email that maximizes reply probability.

Context:
- Company: {company}
- Role: {role}
- Key Skills Required: {skills}
- Location: {location}
{job_context_html}

About Me (The Sender):
{profile_context}

Format to follow EXACTLY (Use HTML tags):
<p>Hi [Recruiter's Name],</p>

<p>I hope this finds you well. I'm Ankit Kumar Singh, a final-year Integrated M.Tech student at IIIT Gwalior (graduating May 2026), currently interning as a Backend Engineer at Rakuten India where I'm building LLM-powered agents and large-scale ELT pipelines processing 20–25 GB of daily transactional data on GCP/BigQuery.</p>

<p>I'm reaching out to express my strong interest in the <b>{role}</b> role at <b>{company}</b>.</p>

<p>A quick snapshot of my profile:</p>
<ul style="margin-top: 0; padding-left: 20px;">
  <li><b>LeetCode Knight (1950+)</b> — Global Rank 85 (top 0.01%)</li>
  <li><b>Backend:</b> [Extract 4-5 relevant backend tools from JD/Profile, e.g. FastAPI, Node.js, Redis, Kafka]</li>
  <li><b>Data:</b> [Extract 3-4 relevant data tools, e.g. PySpark, Airflow, BigQuery]</li>
  <li><b>Projects:</b> [Extract 2-3 highly relevant projects (short names only), e.g. Distributed Rate Limiter, AI-Powered SaaS]</li>
  <li><b>Achievements:</b> Flipkart GRiD National Semifinalist, Amazon ML Summer School (top 0.1%)</li>
</ul>

    <p>I've attached <a href="https://drive.google.com/file/d/1ngdvnyt74RyCzqIZ6aaHFD2ck2tqbLQR/view?usp=sharing">my resume</a> for your reference. I'd love to learn about any open opportunities at {company} and would be happy to connect for a quick 10-minute call at your convenience.</p>

<p>Thank you for your time — I genuinely appreciate it.</p>

<p>Best regards,<br>
Ankit Kumar Singh<br>
+91 9451184789<br>
LinkedIn: <a href="https://www.linkedin.com/in/ankit-kumar-singh-37450422a/">linkedin.com/in/ankit-kumar-singh-37450422a/</a><br>
GitHub: <a href="https://github.com/codexankitsingh">github.com/codexankitsingh</a><br>
Portfolio: <a href="https://ankitsingh.space">ankitsingh.space</a><br>
LeetCode: <a href="https://leetcode.com/u/_Ankitkumarsingh/">leetcode.com/u/_Ankitkumarsingh/</a></p>

Rules:
1. Preserve the EXACT HTML structure provided above. Do not deviate or add fluffy introductory sentences.
2. Adapt the "Backend", "Data", and "Projects" bullets intelligently by injecting the exact keywords requested in the {skills} JD context, mapping them to my profile. Keep them extremely short and punchy as shown in the example.
3. Keep the LeetCode and Achievements bullets static exactly as written.
4. Set the subject line strictly to: "[Target Role] | Rakuten Intern | IIIT Gwalior ’26 – Referral Request". Replace [Target Role] with a concise version of {role}.

Return ONLY a JSON object with exactly these keys, no markdown boundaries around the JSON:
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
            return {
                "subject": f"Referral Request - {role} at {company}",
                "body": f"Hi,\n\nI came across the {role} position at {company} and I'm very interested. My background in {skills} aligns well with the requirements. Would you be open to referring me for this role?\n\nThank you for your time!\n\nBest regards",
            }

    def generate_follow_up(self, original_email: str, follow_up_number: int, model_name: str = "gemini-2.5-flash-lite") -> str:
        """
        Generate a follow-up email based on the original.
        Returns: follow-up email body (<80 words)
        """
        prompt = f"""Write a polite follow-up email (follow-up #{follow_up_number}).

Original email that was sent:
{original_email}

Rules:
1. Maximum 80 words
2. Be polite and not pushy
3. Reference the original email briefly
4. Don't repeat the same content
5. If follow-up #1: gentle reminder
6. Output the email body in valid HTML utilizing <p> and <br> tags where necessary. Include an HTML sign-off matching the original sender. Do NOT use markdown.
7. NEVER output placeholders like [Date] or [Company]. Always write naturally or extract the exact values from the Original email provided above.

Return ONLY the HTML email body text, no JSON, no formatting wrappers.
"""
        try:
            return self._call_gemini(prompt, model_name=model_name)
        except Exception as e:
            print(f"Follow-up generation error: {e}")
            if follow_up_number == 1:
                return "Hi, I wanted to follow up on my previous email regarding the referral request. I'm still very interested in the role and would appreciate any help. Thank you!"
            elif follow_up_number == 2:
                return "Hi, I hope you're doing well. I wanted to check in once more about the referral request I sent earlier. I remain very interested in this opportunity. Please let me know if you'd be able to help. Thanks!"
            else:
                return "Hi, I understand you're busy, so this will be my last follow-up. If you're able to provide a referral, I'd be truly grateful. Either way, thank you for your time!"


# Singleton instance
ai_service = AIService()
