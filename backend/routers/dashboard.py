"""Router: Dashboard & Status Management."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from database import get_db
from schemas import OutreachRecord, DashboardResponse, UpdateStatusRequest
from models.email_thread import EmailThread
from models.job_application import JobApplication
from models.recipient import Recipient
from models.mail_account import MailAccount

router = APIRouter(prefix="/api", tags=["dashboard"])

VALID_STATUSES = [
    "draft", "sent", "follow_up_1", "follow_up_2", "follow_up_3",
    "replied", "interview_scheduled", "closed",
]


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get all outreach records for the dashboard."""
    query = (
        db.query(EmailThread)
        .options(
            joinedload(EmailThread.application),
            joinedload(EmailThread.recipient),
            joinedload(EmailThread.sender_account),
        )
        .order_by(EmailThread.last_activity_at.desc())
    )

    if status:
        query = query.filter(EmailThread.status == status)

    if search:
        query = query.join(JobApplication).filter(
            (JobApplication.company.ilike(f"%{search}%")) |
            (JobApplication.role.ilike(f"%{search}%"))
        )

    threads = query.all()

    records = []
    for t in threads:
        records.append(OutreachRecord(
            id=t.id,
            company=t.application.company if t.application else None,
            role=t.application.role if t.application else None,
            recipient_email=t.recipient.email if t.recipient else "",
            recipient_name=t.recipient.name if t.recipient else None,
            sender_email=t.sender_account.email if t.sender_account else "",
            status=t.status,
            follow_up_count=t.follow_up_count,
            last_activity_at=t.last_activity_at,
            replied=bool(t.replied),
            interview_scheduled=bool(t.interview_scheduled),
            created_at=t.created_at,
        ))

    return DashboardResponse(records=records, total=len(records))


@router.post("/update-status")
def update_status(request: UpdateStatusRequest, db: Session = Depends(get_db)):
    """Manually update thread status."""
    thread = db.query(EmailThread).filter(EmailThread.id == request.thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if request.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {VALID_STATUSES}")

    thread.status = request.status

    if request.replied is not None:
        thread.replied = int(request.replied)
    if request.interview_scheduled is not None:
        thread.interview_scheduled = int(request.interview_scheduled)

    db.commit()
    return {"message": "Status updated", "thread_id": request.thread_id, "status": request.status}


@router.get("/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get summary statistics for the dashboard."""
    total = db.query(EmailThread).count()
    sent = db.query(EmailThread).filter(EmailThread.status != "draft").count()
    replied = db.query(EmailThread).filter(EmailThread.replied == 1).count()
    interviews = db.query(EmailThread).filter(EmailThread.interview_scheduled == 1).count()
    return {
        "total": total,
        "sent": sent,
        "replied": replied,
        "interviews": interviews,
    }


@router.delete("/thread/{thread_id}")
def delete_thread(thread_id: int, db: Session = Depends(get_db)):
    """Delete an outreach thread."""
    thread = db.query(EmailThread).filter(EmailThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db.delete(thread)
    db.commit()
    return {"message": "Thread deleted", "thread_id": thread_id}


from pydantic import BaseModel

class SyncSheetsRequest(BaseModel):
    account_id: int
    spreadsheet_id: Optional[str] = None

@router.post("/dashboard/sync-sheets")
def sync_to_sheets(request: SyncSheetsRequest, db: Session = Depends(get_db)):
    """Sync all outreach records to a Google Sheet."""
    from services.sheets_service import sheets_service
    try:
        new_sheet_id = sheets_service.export_dashboard(
            db=db,
            account_id=request.account_id,
            spreadsheet_id=request.spreadsheet_id
        )
        return {
            "message": "Synced to Google Sheets successfully",
            "spreadsheet_id": new_sheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{new_sheet_id}/edit"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync to sheets: {str(e)}")


@router.get("/debug/followups")
def debug_followups(db: Session = Depends(get_db)):
    """Debug: show pending/failed follow-up jobs."""
    from models.follow_up_job import FollowUpJob
    from datetime import datetime

    pending = db.query(FollowUpJob).filter(FollowUpJob.status == "pending").all()
    failed = db.query(FollowUpJob).filter(FollowUpJob.status == "failed").all()

    return {
        "now_utc": str(datetime.utcnow()),
        "pending_count": len(pending),
        "failed_count": len(failed),
        "pending_jobs": [
            {
                "id": j.id,
                "thread_id": j.thread_id,
                "follow_up_number": j.follow_up_number,
                "scheduled_time": str(j.scheduled_time),
                "status": j.status,
            }
            for j in pending[:10]
        ],
        "failed_jobs": [
            {
                "id": j.id,
                "thread_id": j.thread_id,
                "follow_up_number": j.follow_up_number,
                "status": j.status,
            }
            for j in failed[:10]
        ],
    }

@router.get("/debug/trigger_scheduler")
def debug_trigger_scheduler(db: Session = Depends(get_db)):
    """Debug: manually run the follow-up logic to see what happens."""
    from services.scheduler_service import scheduler_service
    import traceback
    try:
        scheduler_service._process_pending_followups()
        return {"status": "success", "message": "Triggered successfully"}
    except Exception as e:
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
