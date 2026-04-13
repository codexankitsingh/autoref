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

        dynamic_format = f"""
Format to follow EXACTLY (Use HTML tags):
<p>Hi Name,</p>

<p>I'm Ankit—[Current Role from profile, e.g. Software Engineer Intern] at <b>[Current Company]</b>, graduating IIIT Gwalior in May 2026. I'm reaching out about {company}'s {role} role because <b>[Write 1 hyper-specific personalization sentence linking a single core technical challenge in the JD to my exact skills and experience]</b>.</p>

<p>Quick context on why I'd be a strong fit:</p>
<ul style="margin-top: 0; padding-left: 20px;">
  <li><b>[Category 1 matching JD keywords, e.g., Systems Engineering / Data Pipelines / Microservices]:</b> [Extract and rewrite exactly 1 achievement/project from my profile that perfectly matches this category. Include metrics if available.]</li>
  <li><b>[Category 2 matching JD keywords, e.g., Performance Optimization / Architecture]:</b> [Extract and rewrite exactly 1 achievement/project from my profile that perfectly matches this category.]</li>
  <li><b>[Category 3 matching JD keywords, e.g., Problem Solving / Core Tech Stack]:</b> [Extract and rewrite exactly 1 achievement from my profile, such as my LeetCode/Codeforces stats or specific tooling mastery, that proves my capability.]</li>
</ul>

{job_context_html}
<p>I've included my <a href="https://drive.google.com/file/d/1XBJO2rHhM90jUA0yV2Q-eyAsQxA3NgoN/view?usp=sharing">resume here</a> for your reference. I would be incredibly grateful if you'd be open to referring me for a relevant position, or connecting me with the appropriate hiring team. I would welcome the opportunity to hop on a brief call to discuss further. Looking forward to hearing from you!</p>

<p>Best regards,<br>
Ankit Kumar Singh<br>
+91 9451184789</p>
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

Rules:
1. Preserve the EXACT HTML structure above. Do NOT add extra paragraphs, greetings, or filler.
2. The 1-sentence personalization MUST bridge a specific need in the JD with a specific capability in my profile.
3. The 3 bullet points MUST be factually extracted from my profile text. DO NOT hallucinate projects, metrics, or experiences I do not have! If the JD asks for C++, explicitly highlight my C++ skills. If it asks for PySpark, highlight PySpark. Select the projects from my profile that are the BEST fit for this specific job.
4. Replace bracketed placeholders like [Category 1] with an actionable, bolded category name related to the bullet point (e.g. <b>At Rakuten (Systems):</b> or <b>DSA & Algorithms:</b>).
5. Set the subject line strictly to a short, punchy technical headline. Example forms:
   - "Codeforces Specialist & IIITG Grad | {role} at {company}"
   - "Built auto-healing pipelines at Rakuten | {company} SWE opportunity"
   - "Rakuten Intern | 40% cost reduction via Airflow | {company} DE opportunity"

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
