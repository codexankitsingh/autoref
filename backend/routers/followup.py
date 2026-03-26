"""Router: Follow-up Management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import ScheduleFollowupsRequest, StopFollowupsRequest
from models.email_thread import EmailThread
from models.follow_up_job import FollowUpJob
from services.scheduler_service import scheduler_service

router = APIRouter(prefix="/api", tags=["followup"])


@router.post("/schedule-followups")
def schedule_followups(request: ScheduleFollowupsRequest, db: Session = Depends(get_db)):
    """Schedule follow-up emails for a thread."""
    thread = db.query(EmailThread).filter(EmailThread.id == request.thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread.follow_up_interval_days = request.interval_days
    thread.max_follow_ups = request.max_follow_ups
    db.commit()

    # Schedule via scheduler service (stub in Phase 1)
    scheduler_service.schedule_follow_ups(
        thread_id=request.thread_id,
        interval_days=request.interval_days,
        max_follow_ups=request.max_follow_ups,
    )

    return {"message": "Follow-ups scheduled", "thread_id": request.thread_id}


@router.post("/stop-followups")
def stop_followups(request: StopFollowupsRequest, db: Session = Depends(get_db)):
    """Stop all pending follow-ups for a thread."""
    thread = db.query(EmailThread).filter(EmailThread.id == request.thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Cancel pending follow-up jobs
    db.query(FollowUpJob).filter(
        FollowUpJob.thread_id == request.thread_id,
        FollowUpJob.status == "pending",
    ).update({"status": "cancelled"})
    db.commit()

    scheduler_service.cancel_follow_ups(request.thread_id)

    return {"message": "Follow-ups stopped", "thread_id": request.thread_id}
