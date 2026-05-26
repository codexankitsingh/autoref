"""
Scoring Service — LLM-based evaluation of job descriptions against a user's profile.
"""
from services.ai_service import ai_service


class ScoringService:
    def score_job(self, jd_text: str, user_profile: str, model_name: str = "gemini-2.5-flash-lite") -> dict:
        """
        Score a job description against the user's profile.
        Returns a dict with: match_score (0-100), match_reason, missing_skills, required_skills
        """
        if not jd_text:
            return self._default_empty_score()

        # Handle empty user profile gracefully
        profile_context = user_profile if user_profile else "No profile provided. Evaluate the job based purely on standard technical requirements."

        prompt = f"""You are an expert technical recruiter and career coach.
I want you to evaluate this Job Description against my Profile.

My Profile:
{profile_context}

Job Description:
{jd_text}

Analyze the match and return a JSON object with exactly these keys:
{{
  "match_score": integer (0 to 100),
  "match_reason": "string (1-2 sentences explaining the score, brutally honest)",
  "missing_skills": ["skill1", "skill2"] (skills required in JD that are missing from my profile. Empty list if none.),
  "required_skills": ["skill1", "skill2"] (top 5-8 essential skills required by this job)
}}

Scoring guidelines:
- 90-100: Perfect match, I have all required skills and experience level.
- 70-89: Good match, I meet the core requirements but might be missing nice-to-haves.
- 50-69: Stretch role, I meet some requirements but am missing key skills or experience.
- 0-49: Poor match, fundamentally different role or requires completely different seniority/stack.

CRITICAL SENIORITY RULE:
- I am targeting 0-2 years of experience roles (entry-level / junior / new grad / SDE-1).
- If the JD explicitly requires 3+ years of experience, OR the title contains "Senior", "SDE-2", "SDE-3", "Staff", "Lead", "Principal", "Architect", immediately cap the score at 25 or below regardless of skill match.
- A perfect skill match with wrong seniority (3+ years required) should score 15-25, NOT 70+.

Return ONLY the raw JSON object, no markdown wrappers, no code blocks.
"""
        try:
            response_text = ai_service._call_gemini(prompt, model_name=model_name)
            parsed = ai_service._parse_json_response(response_text)
            
            return {
                "match_score": int(parsed.get("match_score", 0)),
                "match_reason": str(parsed.get("match_reason", "")),
                "missing_skills": parsed.get("missing_skills", []),
                "required_skills": parsed.get("required_skills", [])
            }
        except Exception as e:
            print(f"Failed to score job: {e}")
            return self._default_empty_score(reason=f"Scoring failed: {str(e)}")

    def _default_empty_score(self, reason: str = "Job description is empty or scoring failed") -> dict:
        return {
            "match_score": 0,
            "match_reason": reason,
            "missing_skills": [],
            "required_skills": []
        }

# Singleton
scoring_service = ScoringService()
