import json
import os
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from jobspy import scrape_jobs
import pandas as pd

from database import SessionLocal
from models.scraped_job import ScrapedJob
from models.user import User
from services.scoring_service import scoring_service


class ScraperService:
    CONFIG_FILE = os.path.join(os.path.dirname(__file__), "../scraper_config.json")
    
    def __init__(self):
        # Default config if none exists
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
        print(f"[{datetime.now()}] Starting daily job scrape...")
        config = self.get_config()
        if not config.get("queries"):
            print("No scraper queries configured. Skipping.")
            return

        # Fetch admin user to associate jobs with
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
                
            # Deduplicate the dataframe
            all_jobs_df = all_jobs_df.drop_duplicates(subset=["job_url"])
            print(f"Found {len(all_jobs_df)} unique jobs.")
            
            # Save and score
            self._process_and_score_jobs(all_jobs_df, admin_user, db, config.get("min_score_threshold", 50))
            
        finally:
            db.close()
            print(f"[{datetime.now()}] Daily job scrape complete.")

    def _process_and_score_jobs(self, jobs_df: pd.DataFrame, user: User, db: Session, threshold: int):
        user_profile = user.profile_text or ""
        new_jobs = 0
        scored_jobs = 0

        for _, row in jobs_df.iterrows():
            job_url = str(row.get("job_url", ""))
            if not job_url or job_url == "nan":
                continue
                
            # Create a short hash for faster lookup
            url_hash = hashlib.sha256(job_url.encode()).hexdigest()
            
            # Check if job already exists
            existing = db.query(ScrapedJob).filter(ScrapedJob.job_url_hash == url_hash).first()
            if existing:
                continue
                
            # It's a new job
            new_jobs += 1
            title = str(row.get("title", ""))
            company = str(row.get("company", ""))
            location = str(row.get("location", ""))
            description = str(row.get("description", ""))
            if description == "nan": description = ""
            
            # Score it using Gemini
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
            
            # Auto-reject jobs that are too low score
            if job.match_score is not None and job.match_score < threshold:
                job.status = "rejected_low_score"
            else:
                job.status = "saved"
                
            db.add(job)
            scored_jobs += 1
            
            # Commit occasionally to avoid massive transactions
            if scored_jobs % 10 == 0:
                db.commit()
                
        # Final commit
        db.commit()
        print(f"Added {new_jobs} new jobs to DB.")


# Singleton
scraper_service = ScraperService()
