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

    def _call_gemini(self, prompt: str, max_retries: int = 3) -> str:
        """Make a Gemini API call with retry logic for rate limits."""
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
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

    def parse_jd(self, jd_text: str) -> dict:
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
  "location": "location or null if not found"
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
            text = self._call_gemini(prompt)
            parsed = self._parse_json_response(text)
            return {
                "company": parsed.get("company"),
                "role": parsed.get("role"),
                "skills": parsed.get("skills", []),
                "location": parsed.get("location"),
            }
        except Exception as e:
            print(f"JD parsing error: {e}")
            return {
                "company": None,
                "role": None,
                "skills": [],
                "location": None,
            }

    def generate_email(self, jd_data: dict, user_profile: str = "") -> dict:
        """
        Generate a tailored referral email based on JD and user profile.
        Returns: {"subject": str, "body": str}
        """
        company = jd_data.get("company") or "the company"
        role = jd_data.get("role") or "the position"
        skills = ", ".join(jd_data.get("skills", []))
        location = jd_data.get("location", "")

        profile_context = ""
        if user_profile:
            profile_context = f"""
About the sender (use this to personalize the email):
{user_profile}
"""

        prompt = f"""Write a professional referral request email for a job application.

Context:
- Company: {company}
- Role: {role}
- Key Skills Required: {skills}
- Location: {location}
{profile_context}

Rules:
1. Length: 120-180 words ONLY
2. Tone: Professional but warm, NOT robotic
3. Structure:
   - Brief self-introduction (1 sentence)
   - Express interest in the specific role
   - Mention 2-3 relevant skills/experiences that match
   - Politely request a referral
   - Thank them
4. Do NOT use generic phrases like "I hope this email finds you well"
5. Do NOT use overly formal language
6. Make it feel human-written
7. Be specific to the role and company

Return ONLY a JSON object with exactly these keys, no markdown, no code blocks:
{{
  "subject": "email subject line",
  "body": "full email body"
}}
"""
        try:
            text = self._call_gemini(prompt)
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

    def generate_follow_up(self, original_email: str, follow_up_number: int) -> str:
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
6. If follow-up #2: slightly more direct, mention continued interest
7. If follow-up #3: final follow-up, respect their time
8. Return ONLY the email body text, no subject line, no JSON, no formatting

Write the follow-up email body:
"""
        try:
            return self._call_gemini(prompt)
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
