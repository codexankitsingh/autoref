from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import datetime

from database import get_db
from models.scraped_job import ScrapedJob
from models.user import User
from dependencies import get_approved_user
from services.scraper_service import scraper_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    status: Optional[str] = None,
    min_score: int = Query(0, ge=0, le=100),
    source: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """List scraped jobs with filtering."""
    query = db.query(ScrapedJob).filter(ScrapedJob.user_id == current_user.id)
    
    if status:
        query = query.filter(ScrapedJob.status == status)
    else:
        # By default don't show rejected jobs unless explicitly asked
        query = query.filter(ScrapedJob.status != "rejected_low_score")
        
    if min_score > 0:
        query = query.filter(ScrapedJob.match_score >= min_score)
        
    if source:
        query = query.filter(ScrapedJob.source == source)
        
    jobs = query.order_by(desc(ScrapedJob.match_score), desc(ScrapedJob.scraped_at)).limit(limit).all()
    
    # Return as dicts
    return [{
        "id": j.id,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "source": j.source,
        "match_score": j.match_score,
        "status": j.status,
        "scraped_at": j.scraped_at,
        "job_url": j.job_url,
        "required_skills": j.required_skills,
    } for j in jobs]


@router.get("/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Get details for a specific job."""
    job = db.query(ScrapedJob).filter(
        ScrapedJob.id == job_id, 
        ScrapedJob.user_id == current_user.id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "source": job.source,
        "match_score": job.match_score,
        "match_reason": job.match_reason,
        "missing_skills": job.missing_skills,
        "required_skills": job.required_skills,
        "status": job.status,
        "job_url": job.job_url,
    }


@router.post("/{job_id}/pursue")
def pursue_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Mark a job as pursued. (Moves it to active pipeline)."""
    job = db.query(ScrapedJob).filter(
        ScrapedJob.id == job_id, 
        ScrapedJob.user_id == current_user.id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job.status = "pursued"
    job.updated_at = datetime.utcnow()
    db.commit()
    
    return {"status": "success", "message": "Job marked as pursued"}


@router.post("/trigger-scrape")
def trigger_scrape(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_approved_user),
):
    """Manually trigger the scraper job (Admin/Debug)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
        
    import threading
    # Run in background to not block the request
    threading.Thread(target=scraper_service.scrape_all_sources).start()
    
    return {"status": "success", "message": "Scrape job triggered in background"}
