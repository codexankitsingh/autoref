import json
import os
import re
import hashlib
from datetime import datetime
from typing import Any, Optional, Tuple
from sqlalchemy.orm import Session

from database import SessionLocal
from models.scraped_job import ScrapedJob
from models.user import User
from services.scoring_service import scoring_service
from services.profile_defaults import resolve_profile_text
from config import get_settings

# Regex patterns that indicate a role is too senior (SDE-2/3, Senior, Staff, etc.)
SENIOR_TITLE_PATTERNS = re.compile(
    r'\b('
    r'sde[\s\-]?[2-9]|sde[\s\-]?ii|sde[\s\-]?iii|'
    r'data[\s\-]?engineer[\s\-]?(?:ii|iii|2|3|4|5)|'
    r'senior|sr\.?\s|staff|principal|lead|'
    r'manager|director|architect|head\sof|vp\s|'
    r'[5-9]\+?\s*(?:years?|yrs?)|'
    r'\b[5-9]\-\d+\s*(?:years?|yrs?)'
    r')\b',
    re.IGNORECASE
)

_scrape_jobs_fn = None
_pandas_module = None
_scraper_import_error: Optional[str] = None


def scraper_dependencies_available() -> bool:
    """True if python-jobspy + pandas are installed (optional on Render)."""
    global _scrape_jobs_fn, _pandas_module, _scraper_import_error
    if _scrape_jobs_fn is not None and _pandas_module is not None:
        return True
    if _scraper_import_error is not None:
        return False
    try:
        from jobspy import scrape_jobs
        import pandas as pd

        _scrape_jobs_fn = scrape_jobs
        _pandas_module = pd
        return True
    except ImportError as e:
        _scraper_import_error = str(e)
        return False


def scraper_unavailable_reason() -> str:
    if scraper_dependencies_available():
        return ""
    return (
        _scraper_import_error
        or "Install optional deps: pip install -r requirements-scraper.txt"
    )


class ScraperService:
    CONFIG_FILE = os.path.join(os.path.dirname(__file__), "../scraper_config.json")

    def __init__(self):
        if not os.path.exists(self.CONFIG_FILE):
            self.save_config({
                "queries": [
                    {"search_term": "Software Engineer", "location": "India"},
                    {"search_term": "Backend Engineer", "location": "Bangalore"}
                ],
                "results_wanted": 20,
                "hours_old": 24,
                "min_score_threshold": 50
            })

    def is_enabled(self) -> bool:
        settings = get_settings()
        return bool(settings.enable_job_scraper) and scraper_dependencies_available()

    def get_config(self) -> dict:
        try:
            with open(self.CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load scraper config: {e}")
            return {"queries": [], "results_wanted": 10, "hours_old": 24, "min_score_threshold": 50}

    def save_config(self, config: dict):
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)

    def scrape_all_sources(self):
        """Main scraping job. Triggered daily by APScheduler."""
        if not get_settings().enable_job_scraper:
            print("Job scraper disabled (ENABLE_JOB_SCRAPER=false). Skipping.")
            return
        if not scraper_dependencies_available():
            print(f"Job scraper deps missing: {scraper_unavailable_reason()}")
            return

        scrape_jobs = _scrape_jobs_fn
        pd = _pandas_module

        print(f"[{datetime.now()}] Starting daily job scrape...")
        config = self.get_config()
        if not config.get("queries"):
            print("No scraper queries configured. Skipping.")
            return

        db = SessionLocal()
        try:
            admin_user = db.query(User).filter(User.is_active == 1).first()
            if not admin_user:
                print("No active user found. Cannot scrape.")
                return

            all_jobs_df = pd.DataFrame()

            for query in config["queries"]:
                term = query.get("search_term", "")
                loc = query.get("location", "")
                print(f"Scraping for '{term}' in '{loc}'...")

                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed", "glassdoor"],
                        search_term=term,
                        location=loc,
                        results_wanted=config.get("results_wanted", 20),
                        hours_old=config.get("hours_old", 24),
                        country_ece='in',
                        linkedin_fetch_description=True
                    )

                    if not jobs.empty:
                        all_jobs_df = pd.concat([all_jobs_df, jobs], ignore_index=True)
                except Exception as e:
                    print(f"Failed to scrape query '{term}': {e}")

            if all_jobs_df.empty:
                print("No jobs found across all queries.")
                return

            all_jobs_df = all_jobs_df.drop_duplicates(subset=["job_url"])
            print(f"Found {len(all_jobs_df)} unique jobs.")

            self._process_and_score_jobs(all_jobs_df, admin_user, db, config.get("min_score_threshold", 50))

        finally:
            db.close()
            print(f"[{datetime.now()}] Daily job scrape complete.")

    def _process_and_score_jobs(self, jobs_df: Any, user: User, db: Session, threshold: int):
        scoring_role = getattr(user, "default_target_role", None) or "Data Engineering"
        user_profile = resolve_profile_text(user.profile_text, scoring_role)
        new_jobs = 0
        scored_jobs = 0

        for _, row in jobs_df.iterrows():
            job_url = str(row.get("job_url", ""))
            if not job_url or job_url == "nan":
                continue

            url_hash = hashlib.sha256(job_url.encode()).hexdigest()

            existing = db.query(ScrapedJob).filter(ScrapedJob.job_url_hash == url_hash).first()
            if existing:
                continue

            new_jobs += 1
            title = str(row.get("title", ""))
            company = str(row.get("company", ""))
            location = str(row.get("location", ""))
            description = str(row.get("description", ""))
            if description == "nan":
                description = ""

            if SENIOR_TITLE_PATTERNS.search(title):
                print(f"  ⏭️ Skipped (senior title): {title} @ {company}")
                job = ScrapedJob(
                    user_id=user.id,
                    job_url=job_url,
                    job_url_hash=url_hash,
                    title=title,
                    company=company,
                    location=location,
                    description=description,
                    source="scraper",
                    match_score=0,
                    match_reason="Auto-rejected: title indicates senior-level role (SDE-2/3, Senior, Staff, etc.)",
                    missing_skills="[]",
                    required_skills="[]",
                    status="rejected_low_score",
                    scored_at=datetime.utcnow()
                )
                db.add(job)
                new_jobs += 1
                continue

            print(f"Scoring: {title} @ {company}")
            score_data = scoring_service.score_job(description, user_profile)

            job = ScrapedJob(
                user_id=user.id,
                job_url=job_url,
                job_url_hash=url_hash,
                title=title,
                company=company,
                location=location,
                description=description,
                source="scraper",
                match_score=score_data.get("match_score"),
                match_reason=score_data.get("match_reason"),
                missing_skills=json.dumps(score_data.get("missing_skills", [])),
                required_skills=json.dumps(score_data.get("required_skills", [])),
                scored_at=datetime.utcnow()
            )

            if job.match_score is not None and job.match_score < threshold:
                job.status = "rejected_low_score"
            else:
                job.status = "saved"

            db.add(job)
            scored_jobs += 1

            if scored_jobs % 10 == 0:
                db.commit()

        db.commit()
        print(f"Added {new_jobs} new jobs to DB.")


scraper_service = ScraperService()
